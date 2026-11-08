import json
from dataclasses import replace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from router_lens.app import build_app, footer_text, parse_evidence, strip_footers
from router_lens.config import Settings
from router_lens.feed import build_feed_app
from router_lens.ledger import Ledger

PRICES = {
    "models": {
        "openai/gpt-oss-20b": {"input": 0.075, "output": 0.30},
        "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60},
        "nvidia/nemotron-3-ultra-550b-a55b": {"input": 0.60, "output": 2.40},
    },
    "capable_model": "nvidia/nemotron-3-ultra-550b-a55b",
}
TIERS = {"openai/gpt-oss-20b": "fast", "openai/gpt-oss-120b": "balanced", "nvidia/nemotron-3-ultra-550b-a55b": "capable"}
FAST_EVIDENCE = json.dumps({"source": "llm-classifier", "verdict": {"decision": {"target": "fast", "reason": "Greeting, small talk"}}})


def sse(*chunks):
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


def chunk(content=None, finish=None, usage=None):
    data = {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": "openai/gpt-oss-20b",
            "choices": [] if usage else [{"index": 0, "delta": {"content": content} if content else {}, "finish_reason": finish}]}
    if usage:
        data["usage"] = usage
    return data


class FakeSwitchyard:
    """Behaviour per route id: status, headers, body."""

    def __init__(self):
        self.routes = {}
        self.requests = []

    def set(self, route, status=200, headers=None, body=None):
        self.routes[route] = (status, headers or {}, body)

    def app(self):
        async def chat(request: Request):
            payload = await request.json()
            self.requests.append(payload)
            status, headers, body = self.routes[payload["model"]]
            media = "text/event-stream" if payload.get("stream") else "application/json"
            return Response(body if isinstance(body, str) else json.dumps(body), status_code=status, headers=headers, media_type=media)

        async def stats(_):
            return JSONResponse({"classifier": {"models": {"openai/gpt-oss-20b": {"prompt_tokens": 400, "completion_tokens": 60}}}})

        return Starlette(routes=[Route("/v1/chat/completions", chat, methods=["POST"]), Route("/v1/stats", stats)])


@pytest.fixture
def fake():
    return FakeSwitchyard()


def make(fake, **overrides):
    settings = replace(Settings(prices=PRICES, model_tiers=TIERS, stats_poll_seconds=3600), **overrides)
    ledger = Ledger(PRICES, TIERS)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=fake.app()), base_url="http://switchyard:4000")
    return TestClient(build_app(settings, ledger, client)), ledger


def ask(client, text="Hi there!", stream=True, history=None):
    messages = (history or []) + [{"role": "user", "content": text}]
    return client.post("/v1/chat/completions", json={"model": "mtn-smart", "stream": stream, "messages": messages})


STREAM = sse(chunk("Good "), chunk("morning!"), chunk(finish="stop"), chunk(usage={"prompt_tokens": 20, "completion_tokens": 5}))
FAST_HEADERS = {"x-model-router-selected-model": "openai/gpt-oss-20b", "x-switchyard-route-evidence": FAST_EVIDENCE}


def test_streaming_turn_is_recorded_with_judge_reason_and_usage(fake):
    fake.set("mtn-smart", headers=FAST_HEADERS, body=STREAM)
    client, ledger = make(fake)
    with client:
        response = ask(client)
    assert response.status_code == 200
    assert "Good " in response.text and "Routed to" not in response.text  # footer off by default
    assert response.headers["x-model-router-selected-model"] == "openai/gpt-oss-20b"
    assert fake.requests[0]["stream_options"] == {"include_usage": True}
    [decision] = ledger.recent
    assert (decision.tier, decision.reason, decision.reason_source, decision.judge_route) == ("fast", "Greeting, small talk", "judge", "primary")
    assert (decision.prompt_tokens, decision.completion_tokens) == (20, 5)
    assert decision.prompt.startswith("[redacted")


def test_footer_is_injected_before_the_finish_chunk_when_enabled(fake):
    fake.set("mtn-smart", headers=FAST_HEADERS, body=STREAM)
    client, _ = make(fake, show_footer=True)
    with client:
        text = ask(client).text
    events = [e for e in text.split("\n\n") if e.startswith("data: {")]
    contents = [json.loads(e[6:])["choices"][0]["delta"].get("content") for e in events if json.loads(e[6:])["choices"]]
    footer_index = next(i for i, c in enumerate(contents) if c and c.startswith("\n\n*Routed to"))
    assert contents[footer_index].startswith("\n\n*Routed to openai/gpt-oss-20b · fast · Greeting, small talk · ")
    finish_index = next(i for i, e in enumerate(events) if '"finish_reason": "stop"' in e)
    assert footer_index < finish_index


def test_footers_are_stripped_from_history_before_forwarding(fake):
    fake.set("mtn-smart", headers=FAST_HEADERS, body=STREAM)
    client, _ = make(fake)
    history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!" + footer_text("m", "fast", "r", 1200)}]
    with client:
        ask(client, "Thanks", history=history)
    assert fake.requests[0]["messages"][1]["content"] == "Hello!"


def test_missing_reason_falls_back_to_the_tier_rule(fake):
    fake.set("mtn-smart", headers={"x-model-router-selected-model": "openai/gpt-oss-120b"}, body=STREAM)
    client, ledger = make(fake)
    with client:
        ask(client)
    assert (ledger.recent[0].tier, ledger.recent[0].reason, ledger.recent[0].reason_source) == ("balanced", "everyday work question", "rule")


def test_fail_open_evidence_is_explained(fake):
    headers = {"x-model-router-selected-model": "openai/gpt-oss-120b",
               "x-switchyard-route-evidence": json.dumps({"source": "fail_open", "reason_code": "parse_error"})}
    fake.set("mtn-smart", headers=headers, body=STREAM)
    client, ledger = make(fake)
    with client:
        ask(client)
    assert ledger.recent[0].reason == "judge unavailable, default tier"


def test_primary_failure_retries_once_on_the_backup_judge_route(fake):
    fake.set("mtn-smart", status=504, body={"error": {"message": "judge timeout"}})
    fake.set("mtn-smart-backup-judge", headers=FAST_HEADERS, body=STREAM)
    client, ledger = make(fake)
    with client:
        response = ask(client)
    assert response.status_code == 200
    assert [r["model"] for r in fake.requests] == ["mtn-smart", "mtn-smart-backup-judge"]
    assert ledger.recent[0].judge_route == "backup" and ledger.backup_judge_turns == 1


def test_errors_pass_through_and_are_counted(fake):
    fake.set("mtn-smart", status=504, body={"error": {"message": "x"}})
    fake.set("mtn-smart-backup-judge", status=400, body={"error": {"message": "bad request"}})
    client, ledger = make(fake)
    with client:
        response = ask(client)
    assert response.status_code == 400 and ledger.errors == 1 and ledger.recent[0].status == "error"


def test_non_streaming_turn_gets_footer_and_usage(fake):
    body = {"id": "x", "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
    fake.set("mtn-smart", headers=FAST_HEADERS, body=body)
    client, ledger = make(fake, show_footer=True)
    with client:
        data = ask(client, stream=False).json()
    assert data["choices"][0]["message"]["content"].startswith("Hello\n\n*Routed to openai/gpt-oss-20b · fast · Greeting, small talk")
    assert ledger.recent[0].completion_tokens == 2


def test_prompts_are_shown_only_when_redaction_is_off(fake):
    fake.set("mtn-smart", headers=FAST_HEADERS, body=STREAM)
    client, ledger = make(fake, redact_prompts=False)
    with client:
        ask(client, "x" * 100)
    assert ledger.recent[0].prompt == "x" * 80 + "…"


def test_cost_index_and_metrics():
    ledger = Ledger(PRICES, TIERS)
    from router_lens.ledger import Decision

    ledger.record(Decision(0, "p", "fast", "fast", "openai/gpt-oss-20b", "r", "judge", "primary", 900, 1000, 200))
    ledger.record(Decision(0, "p", "capable", "capable", "nvidia/nemotron-3-ultra-550b-a55b", "r", "judge", "primary", 20000, 1000, 200))
    # routed: 20b (0.075+0.06=0.135e-3) + ultra (0.6+0.48=1.08e-3); baseline: 2 x 1.08e-3
    assert ledger.cost_index() == round(100 * (0.000135 + 0.00108) / 0.00216, 1)
    ledger.set_judge_usage({"openai/gpt-oss-20b": {"prompt_tokens": 1000, "completion_tokens": 100}})
    assert ledger.cost_index() > round(100 * (0.000135 + 0.00108) / 0.00216, 1)
    text = ledger.prometheus()
    assert 'mtn_router_turns_total{tier="capable"} 1' in text
    assert 'mtn_router_turn_latency_seconds_bucket{tier="fast",le="1"} 1' in text
    assert 'mtn_router_judge_tokens_total{model="openai/gpt-oss-20b",kind="prompt"} 1000' in text
    assert ledger.summary()["capable_share"] == 50.0


def test_parse_evidence_handles_bad_input():
    assert parse_evidence(None) == (None, None, "rule")
    assert parse_evidence("not json") == (None, None, "rule")
    long = json.dumps({"verdict": {"decision": {"target": "fast", "reason": " ".join(["word"] * 30)}}})
    assert len(parse_evidence(long)[1].split()) == 14


def test_feed_state_has_summary_and_recent(fake):
    ledger = Ledger(PRICES, TIERS)
    from router_lens.ledger import Decision

    ledger.record(Decision(0, "Hi", "fast", "fast", "openai/gpt-oss-20b", "Greeting", "judge", "primary", 800, 10, 5))
    with TestClient(build_feed_app(ledger)) as feed:
        state = feed.get("/state").json()
        assert state["summary"]["turns"]["fast"] == 1 and state["recent"][0]["reason"] == "Greeting"
        assert "MTN Smart Router" in feed.get("/").text


def test_strip_footers_leaves_other_text():
    messages = [{"role": "assistant", "content": "Use *bold* text"}]
    assert strip_footers(messages)[0]["content"] == "Use *bold* text"


def test_footer_comes_after_text_carried_by_the_finishing_chunk(fake):
    """NVIDIA puts the answer's last characters in the same chunk as finish_reason."""
    body = sse(chunk("*Closing line"), chunk(".*", finish="stop"), chunk(usage={"prompt_tokens": 3, "completion_tokens": 2}))
    fake.set("mtn-smart", headers=FAST_HEADERS, body=body)
    client, _ = make(fake, show_footer=True)
    with client:
        text = ask(client).text
    events = [json.loads(e[6:]) for e in text.split("\n\n") if e.startswith("data: {")]
    pieces = [(c["choices"][0]["delta"].get("content"), c["choices"][0].get("finish_reason")) for c in events if c.get("choices")]
    assert [p[0] for p in pieces[:3]] == ["*Closing line", ".*", pieces[2][0]]
    assert pieces[2][0].startswith("\n\n*Routed to")
    assert pieces[3] == (None, "stop")
    assert "".join(p[0] or "" for p in pieces).endswith("s*")
