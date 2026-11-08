"""In-memory routing ledger: recent decisions, running totals, cost index, Prometheus text.

Nothing is persisted. The cost index is relative: 100 means every routed turn (same tokens) had
been served by the capable tier; the judge's own tokens are added to the routed side.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import asdict, dataclass

TIERS = ("fast", "balanced", "capable")
LATENCY_BUCKETS = (1, 2, 5, 10, 20, 30, 45, 60, 90, 120)


@dataclass
class Decision:
    ts: float
    prompt: str
    tier: str
    verdict_tier: str | None
    model: str
    reason: str
    reason_source: str  # judge | rule | fail_open
    judge_route: str  # primary | backup
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    status: str = "ok"


class Ledger:
    def __init__(self, prices: dict, model_tiers: dict, capacity: int = 200):
        self.prices = prices.get("models", {})
        self.capable_model = prices.get("capable_model")
        self.model_tiers = model_tiers
        self.recent: deque[Decision] = deque(maxlen=capacity)
        self.turns = {tier: 0 for tier in TIERS}
        self.errors = 0
        self.backup_judge_turns = 0
        self.tokens: dict[tuple[str, str], int] = {}  # (model, kind) -> tokens
        self.latency_buckets = {tier: [0] * (len(LATENCY_BUCKETS) + 1) for tier in TIERS}
        self.latency_sum = {tier: 0.0 for tier in TIERS}
        self.routed_cost = 0.0  # answer calls at their own prices
        self.baseline_cost = 0.0  # the same answer tokens at capable-tier prices
        self.judge_cost = 0.0
        self.judge_tokens: dict[tuple[str, str], int] = {}
        self._subscribers: set[asyncio.Queue] = set()

    # -- pricing -------------------------------------------------------------------------------

    def _price(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        rate = self.prices.get(model)
        if not rate:
            return 0.0
        return (prompt_tokens * rate["input"] + completion_tokens * rate["output"]) / 1_000_000

    def cost_index(self) -> float | None:
        if self.baseline_cost <= 0:
            return None
        return round(100 * (self.routed_cost + self.judge_cost) / self.baseline_cost, 1)

    # -- recording -----------------------------------------------------------------------------

    def record(self, decision: Decision) -> None:
        self.recent.appendleft(decision)
        if decision.status != "ok":
            self.errors += 1
        else:
            tier = decision.tier if decision.tier in TIERS else "balanced"
            self.turns[tier] += 1
            if decision.judge_route == "backup":
                self.backup_judge_turns += 1
            for kind, count in (("prompt", decision.prompt_tokens), ("completion", decision.completion_tokens)):
                key = (decision.model, kind)
                self.tokens[key] = self.tokens.get(key, 0) + count
            seconds = decision.latency_ms / 1000
            buckets = self.latency_buckets[tier]
            for i, bound in enumerate(LATENCY_BUCKETS):
                if seconds <= bound:
                    buckets[i] += 1
            buckets[-1] += 1
            self.latency_sum[tier] += seconds
            self.routed_cost += self._price(decision.model, decision.prompt_tokens, decision.completion_tokens)
            if self.capable_model:
                self.baseline_cost += self._price(
                    self.capable_model, decision.prompt_tokens, decision.completion_tokens
                )
        payload = {"decision": self.public(decision), "summary": self.summary()}
        for queue in list(self._subscribers):
            if queue.qsize() < 100:
                queue.put_nowait(payload)

    def set_judge_usage(self, usage: dict[str, dict]) -> None:
        """Replaces judge totals from Switchyard's cumulative /v1/stats classifier counters."""
        cost = 0.0
        tokens = {}
        for model, stats in usage.items():
            prompt, completion = int(stats.get("prompt_tokens", 0)), int(stats.get("completion_tokens", 0))
            tokens[(model, "prompt")], tokens[(model, "completion")] = prompt, completion
            cost += self._price(model, prompt, completion)
        self.judge_tokens = tokens
        self.judge_cost = cost

    # -- views ---------------------------------------------------------------------------------

    def public(self, decision: Decision) -> dict:
        data = asdict(decision)
        data["time"] = time.strftime("%H:%M:%S", time.localtime(decision.ts))
        return data

    def summary(self) -> dict:
        total = sum(self.turns.values())
        return {
            "turns": dict(self.turns),
            "total": total,
            "capable_share": round(100 * self.turns["capable"] / total, 1) if total else None,
            "cost_index": self.cost_index(),
            "backup_judge_turns": self.backup_judge_turns,
            "errors": self.errors,
        }

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def prometheus(self) -> str:
        lines = [
            "# HELP mtn_router_turns_total Routed chat turns by served tier.",
            "# TYPE mtn_router_turns_total counter",
        ]
        lines += [f'mtn_router_turns_total{{tier="{t}"}} {n}' for t, n in self.turns.items()]
        lines += [
            "# HELP mtn_router_errors_total Turns that returned an error to LibreChat.",
            "# TYPE mtn_router_errors_total counter",
            f"mtn_router_errors_total {self.errors}",
            "# HELP mtn_router_backup_judge_turns_total Turns served via the backup-judge route.",
            "# TYPE mtn_router_backup_judge_turns_total counter",
            f"mtn_router_backup_judge_turns_total {self.backup_judge_turns}",
            "# HELP mtn_router_tokens_total Answer tokens by served model and kind.",
            "# TYPE mtn_router_tokens_total counter",
        ]
        lines += [
            f'mtn_router_tokens_total{{model="{m}",kind="{k}",tier="{self.model_tiers.get(m, "other")}"}} {n}'
            for (m, k), n in sorted(self.tokens.items())
        ]
        lines += ["# HELP mtn_router_judge_tokens_total Judge tokens (from Switchyard /v1/stats).",
                  "# TYPE mtn_router_judge_tokens_total counter"]
        lines += [f'mtn_router_judge_tokens_total{{model="{m}",kind="{k}"}} {n}' for (m, k), n in sorted(self.judge_tokens.items())]
        lines += [
            "# HELP mtn_router_turn_latency_seconds End-to-end turn latency seen by LibreChat.",
            "# TYPE mtn_router_turn_latency_seconds histogram",
        ]
        for tier in TIERS:
            buckets = self.latency_buckets[tier]
            for i, bound in enumerate(LATENCY_BUCKETS):
                lines.append(f'mtn_router_turn_latency_seconds_bucket{{tier="{tier}",le="{bound}"}} {buckets[i]}')
            lines.append(f'mtn_router_turn_latency_seconds_bucket{{tier="{tier}",le="+Inf"}} {buckets[-1]}')
            lines.append(f'mtn_router_turn_latency_seconds_sum{{tier="{tier}"}} {self.latency_sum[tier]:.3f}')
            lines.append(f'mtn_router_turn_latency_seconds_count{{tier="{tier}"}} {buckets[-1]}')
        lines += [
            "# HELP mtn_router_cost_units_total Relative cost units (list prices), routed vs always-capable.",
            "# TYPE mtn_router_cost_units_total counter",
            f'mtn_router_cost_units_total{{kind="routed_answers"}} {self.routed_cost:.9f}',
            f'mtn_router_cost_units_total{{kind="judge"}} {self.judge_cost:.9f}',
            f'mtn_router_cost_units_total{{kind="always_capable_baseline"}} {self.baseline_cost:.9f}',
        ]
        index = self.cost_index()
        lines += [
            "# HELP mtn_router_cost_index Routed + judge cost as % of always-capable (100 = no saving).",
            "# TYPE mtn_router_cost_index gauge",
            f"mtn_router_cost_index {index if index is not None else 'NaN'}",
        ]
        return "\n".join(lines) + "\n"
