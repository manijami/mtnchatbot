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


# -- guards: images, Office requests, deadlines ------------------------------------------------

import asyncio  # noqa: E402

from router_lens import guards  # noqa: E402

IMAGE_PART = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


def _content(response):
    text = ""
    for line in response.text.split("\n\n"):
        if line.startswith("data: {"):
            for choice in json.loads(line[6:]).get("choices", []):
                text += (choice.get("delta") or {}).get("content") or ""
    return text


VISION_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"


def image_turn(client, stream=True):
    return client.post("/v1/chat/completions", json={"model": "mtn-smart", "stream": stream, "messages": [
        {"role": "user", "content": [{"type": "text", "text": "What colour is this?"}, IMAGE_PART]}]})


def test_image_turns_go_to_the_vision_tier_without_a_judge(fake):
    fake.set("mtn-smart-vision", headers={"x-model-router-selected-model": VISION_MODEL},
             body=sse(chunk("Yellow."), chunk(finish="stop"), chunk(usage={"prompt_tokens": 900, "completion_tokens": 5})))
    client, ledger = make(fake, show_footer=True, model_tiers={**TIERS, VISION_MODEL: "vision"})
    r = image_turn(client)
    assert [q["model"] for q in fake.requests] == ["mtn-smart-vision"]
    assert fake.requests[0]["messages"][0]["content"][1]["type"] == "image_url"
    text = _content(r)
    assert text.startswith("Yellow.") and f"Routed to {VISION_MODEL} · vision tier · image attached" in text
    d = ledger.recent[0]
    assert (d.tier, d.judge_route, d.status) == ("vision", "none", "ok")
    summary = ledger.summary()
    assert summary["turns"]["vision"] == 1 and summary["capable_share"] is None and summary["cost_index"] is None


def test_vision_failure_is_a_friendly_message_not_a_raw_error(fake):
    fake.set("mtn-smart-vision", status=400, body={"error": {"message": "image too large"}})
    client, ledger = make(fake)
    r = image_turn(client)
    assert r.status_code == 200
    assert "couldn't read your image" in _content(r) and "too large" not in r.text
    assert [q["model"] for q in fake.requests] == ["mtn-smart-vision"]  # no retry on text tiers
    assert ledger.summary()["errors"] == 1


def test_image_turn_without_a_vision_tier_gets_a_polite_refusal(fake):
    client, ledger = make(fake, vision_route=None)
    r = image_turn(client, stream=False)
    assert "can't read images" in r.json()["choices"][0]["message"]["content"]
    assert fake.requests == []
    assert ledger.recent[0].status == "handled"


def test_images_in_earlier_turns_become_a_text_note(fake):
    fake.set("mtn-smart", headers={"x-model-router-selected-model": "openai/gpt-oss-20b",
                                   "x-switchyard-route-evidence": FAST_EVIDENCE},
             body=sse(chunk("Sure."), chunk(finish="stop")))
    client, _ = make(fake)
    history = [{"role": "user", "content": [{"type": "text", "text": "Look"}, IMAGE_PART]},
               {"role": "assistant", "content": "I can't read images."}]
    r = ask(client, "OK, tell me a joke", history=history)
    assert r.status_code == 200
    sent = fake.requests[0]["messages"][0]["content"]
    assert isinstance(sent, str) and guards.IMAGE_NOTE in sent and "Look" in sent


@pytest.mark.parametrize("text,kind", [
    ("Can u make a powerpoint on saturn?", "PowerPoint presentation"),
    ("Please create a Word document about our leave policy", "Word document"),
    ("build me an excel spreadsheet of Q3 sales", "Excel workbook"),
    ("Generate a 5-slide deck on onboarding", "PowerPoint presentation"),
])
def test_office_requests_are_detected(text, kind):
    assert guards.office_request(text) == kind


@pytest.mark.parametrize("text", [
    "What is an Excel pivot table?",
    "How do I add slide numbers in PowerPoint?",
    "Summarise this paragraph for me",
])
def test_questions_about_office_products_are_not_office_requests(text):
    assert guards.office_request(text) is None


def test_office_request_points_to_the_document_assistant(fake):
    client, ledger = make(fake)
    r = ask(client, "Can u make a powerpoint on saturn?")
    assert "MTN Document Assistant" in _content(r)
    assert fake.requests == []
    assert ledger.recent[0].reason == "PowerPoint presentation request"


def test_office_reply_non_streaming(fake):
    client, _ = make(fake)
    r = ask(client, "create an excel workbook of team birthdays", stream=False)
    assert "Document Assistant" in r.json()["choices"][0]["message"]["content"]


class SlowSwitchyard(FakeSwitchyard):
    """Delays the response headers (first_delay) or the body after the first chunk (stall)."""

    def __init__(self, first_delay=0.0, stall=0.0):
        super().__init__()
        self.first_delay, self.stall = first_delay, stall

    def app(self):
        outer = self

        async def chat(request: Request):
            await request.json()
            await asyncio.sleep(outer.first_delay)

            async def body():
                yield f"data: {json.dumps(chunk('Partial answer'))}\n\n".encode()
                await asyncio.sleep(outer.stall)
                yield f"data: {json.dumps(chunk(finish='stop'))}\n\ndata: [DONE]\n\n".encode()

            from starlette.responses import StreamingResponse
            return StreamingResponse(body(), media_type="text/event-stream",
                                     headers={"x-model-router-selected-model": "openai/gpt-oss-20b",
                                              "x-switchyard-route-evidence": FAST_EVIDENCE})

        return Starlette(routes=[Route("/v1/chat/completions", chat, methods=["POST"])])


def test_slow_first_response_returns_a_clear_message(fake):
    client, ledger = make(SlowSwitchyard(first_delay=1.0), first_byte_timeout=0.2)
    r = ask(client, "Tell me about Saturn")
    assert r.status_code == 200
    assert "taking much longer than usual" in _content(r)
    assert ledger.recent[0].status == "timeout" and ledger.summary()["timeouts"] == 1


class StallingTransport(httpx.AsyncBaseTransport):
    """Streams one chunk, then goes silent (httpx's ASGI transport buffers, so it cannot stall)."""

    async def handle_async_request(self, request):
        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield f"data: {json.dumps(chunk('Partial answer'))}\n\n".encode()
                await asyncio.sleep(5)
                yield b"data: [DONE]\n\n"

        return httpx.Response(200, headers={"content-type": "text/event-stream",
                                            "x-model-router-selected-model": "openai/gpt-oss-20b",
                                            "x-switchyard-route-evidence": FAST_EVIDENCE}, stream=Body())


def test_stalled_stream_is_closed_with_a_note():
    settings = replace(Settings(prices=PRICES, model_tiers=TIERS, stats_poll_seconds=3600),
                       idle_timeout=0.2, show_footer=False)
    ledger = Ledger(PRICES, TIERS)
    http = httpx.AsyncClient(transport=StallingTransport(), base_url="http://switchyard:4000")
    client = TestClient(build_app(settings, ledger, http))
    r = ask(client, "Tell me about Saturn")
    text = _content(r)
    assert text.startswith("Partial answer") and "cut short" in text
    assert r.text.rstrip().endswith("data: [DONE]")
    assert ledger.recent[0].status == "stalled"
    assert ledger.summary()["turns"]["fast"] == 1


# -- documents tier (MTN Office tools) ---------------------------------------------------------

OFFICE_TOOLS = [{"type": "function", "function": {"name": "create_powerpoint_presentation_mcp_mtn-office",
                                                  "parameters": {"type": "object"}}},
                {"type": "function", "function": {"name": "revise_office_file_mcp_mtn-office",
                                                  "parameters": {"type": "object"}}}]
DOCS_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


def tool_call_chunk():
    return {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": DOCS_MODEL,
            "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                         "function": {"name": "create_powerpoint_presentation_mcp_mtn-office", "arguments": "{}"}}]},
                         "finish_reason": None}]}


def tool_finish_chunk():
    return {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": DOCS_MODEL,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}


def docs_request(client, messages, stream=True):
    return client.post("/v1/chat/completions", json={"model": "mtn-smart", "stream": stream,
                                                     "messages": messages, "tools": OFFICE_TOOLS})


def make_docs(fake, **overrides):
    return make(fake, docs_instructions="You are the MTN Document Assistant.", show_footer=True, **overrides)


def test_office_request_with_office_tools_goes_to_the_documents_tier(fake):
    fake.set("mtn-smart-docs", headers={"x-model-router-selected-model": DOCS_MODEL},
             body=sse(tool_call_chunk(), tool_finish_chunk()))
    client, ledger = make_docs(fake)
    r = docs_request(client, [{"role": "user", "content": "Can u make a powerpoint on saturn?"}])
    assert r.status_code == 200
    sent = fake.requests[0]
    assert sent["model"] == "mtn-smart-docs"
    assert [t["function"]["name"] for t in sent["tools"]][0].startswith("create_powerpoint_presentation")
    assert sent["messages"][0] == {"role": "system", "content": "You are the MTN Document Assistant."}
    assert '"tool_calls"' in r.text and "Routed to" not in r.text  # no footer on a tool-call turn
    d = ledger.recent[0]
    assert (d.tier, d.judge_route, d.reason) == ("documents", "none", "PowerPoint presentation request")


def test_the_answer_after_the_tool_result_stays_on_the_documents_tier_with_a_footer(fake):
    fake.set("mtn-smart-docs", headers={"x-model-router-selected-model": DOCS_MODEL},
             body=sse(chunk("Your deck is ready."), chunk(finish="stop")))
    client, ledger = make_docs(fake)
    messages = [{"role": "user", "content": "Make a 3-slide deck on Saturn"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {
                    "name": "create_powerpoint_presentation_mcp_mtn-office", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call_1", "name": "create_powerpoint_presentation_mcp_mtn-office",
                 "content": "Created Saturn.pptx (3 slides)."}]
    r = docs_request(client, messages)
    assert fake.requests[0]["model"] == "mtn-smart-docs"
    assert "documents tier · Office tool follow-up" in _content(r)
    assert ledger.recent[0].reason == "Office tool follow-up"


def test_a_revision_of_an_earlier_file_goes_to_the_documents_tier(fake):
    fake.set("mtn-smart-docs", headers={"x-model-router-selected-model": DOCS_MODEL},
             body=sse(tool_call_chunk(), tool_finish_chunk()))
    client, ledger = make_docs(fake)
    messages = [{"role": "user", "content": "Make a deck on Saturn"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {
                    "name": "create_powerpoint_presentation_mcp_mtn-office", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call_1", "content": "Created Saturn.pptx."},
                {"role": "assistant", "content": "Your deck is ready."},
                {"role": "user", "content": "Please make slide 2 shorter"}]
    docs_request(client, messages)
    assert fake.requests[0]["model"] == "mtn-smart-docs"
    assert ledger.recent[0].reason == "revision of an Office file"


def test_other_turns_get_no_tools_and_a_plain_text_history(fake):
    fake.set("mtn-smart", headers={"x-model-router-selected-model": "openai/gpt-oss-20b",
                                   "x-switchyard-route-evidence": FAST_EVIDENCE},
             body=sse(chunk("You're welcome!"), chunk(finish="stop")))
    client, ledger = make_docs(fake)
    messages = [{"role": "user", "content": "Make a deck on Saturn"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {
                    "name": "create_powerpoint_presentation_mcp_mtn-office", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call_1", "content": "Created Saturn.pptx."},
                {"role": "assistant", "content": "Your deck is ready."},
                {"role": "user", "content": "thanks!"}]
    docs_request(client, messages)
    sent = fake.requests[0]
    assert sent["model"] == "mtn-smart" and "tools" not in sent
    assert all(m["role"] != "tool" and "tool_calls" not in m for m in sent["messages"])
    assert "[Used tool: create_powerpoint_presentation_mcp_mtn-office]" in sent["messages"][1]["content"]
    assert sent["messages"][2] == {"role": "assistant", "content": "[Tool result] Created Saturn.pptx."}
    assert all(m.get("content") != "You are the MTN Document Assistant." for m in sent["messages"])
    assert ledger.recent[0].tier == "fast"


def test_documents_tier_falls_back_to_its_backup_route(fake):
    fake.set("mtn-smart-docs", status=503, body={"error": {"message": "busy"}})
    fake.set("mtn-smart-docs-backup", headers={"x-model-router-selected-model": "openai/gpt-oss-120b"},
             body=sse(tool_call_chunk(), tool_finish_chunk()))
    client, ledger = make_docs(fake)
    r = docs_request(client, [{"role": "user", "content": "Create an Excel workbook of team tasks"}])
    assert r.status_code == 200
    assert [q["model"] for q in fake.requests] == ["mtn-smart-docs", "mtn-smart-docs-backup"]
    assert (ledger.recent[0].tier, ledger.recent[0].judge_route) == ("documents", "backup")


def test_without_office_tools_an_office_request_still_gets_the_switch_reply(fake):
    client, _ = make_docs(fake)
    r = ask(client, "Can u make a powerpoint on saturn?")
    assert "MTN Document Assistant" in _content(r)
    assert fake.requests == []


@pytest.mark.parametrize("text,expected", [
    ("Please make slide 2 shorter", True),
    ("add a column for priority", True),
    ("rename the workbook to Q3 tracker", True),
    ("thanks!", False),
    ("what is Saturn made of?", False),
])
def test_revision_requests(text, expected):
    assert guards.revision_request(text) is expected


# -- skills (LibreChat `skill` / `read_file` tools) ---------------------------------------------

SKILL_TOOLS = [{"type": "function", "function": {"name": "skill", "parameters": {"type": "object"}}},
               {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}]


def test_skill_tools_stay_on_text_tier_turns_while_office_tools_are_removed(fake):
    fake.set("mtn-smart", headers={"x-model-router-selected-model": "openai/gpt-oss-20b",
                                   "x-switchyard-route-evidence": FAST_EVIDENCE},
             body=sse(chunk("Hi!"), chunk(finish="stop")))
    client, _ = make_docs(fake)
    client.post("/v1/chat/completions", json={"model": "mtn-smart", "stream": True,
                                              "messages": [{"role": "user", "content": "Minute this: steering call notes"}],
                                              "tools": OFFICE_TOOLS + SKILL_TOOLS})
    sent = fake.requests[0]
    assert sent["model"] == "mtn-smart"
    assert sorted(t["function"]["name"] for t in sent["tools"]) == ["read_file", "skill"]


def test_a_skill_tool_exchange_is_not_an_office_follow_up_and_is_kept_intact(fake):
    fake.set("mtn-smart-skill", headers={"x-model-router-selected-model": "openai/gpt-oss-120b"},
             body=sse(chunk("Meeting: Phoenix steering"), chunk(finish="stop")))
    client, ledger = make_docs(fake)
    messages = [{"role": "user", "content": "Minute this: Phoenix steering, decided to move go-live."},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "s1", "type": "function",
                 "function": {"name": "skill", "arguments": "{\"skillName\": \"meeting-minutes\"}"}}]},
                {"role": "tool", "tool_call_id": "s1", "content": "# Meeting minutes ..."}]
    client.post("/v1/chat/completions", json={"model": "mtn-smart", "stream": True, "messages": messages,
                                              "tools": OFFICE_TOOLS + SKILL_TOOLS})
    sent = fake.requests[0]
    assert sent["model"] == "mtn-smart-skill"  # a skill step: fixed tier, not the documents tier
    assert sent["messages"][1]["tool_calls"][0]["function"]["name"] == "skill"
    assert sent["messages"][2]["role"] == "tool"
    assert ledger.recent[0].tier == "balanced"


def test_mixed_history_flattens_only_the_office_exchange():
    messages = [{"role": "user", "content": "make a deck"},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "s1", "type": "function", "function": {"name": "skill", "arguments": "{}"}},
                    {"id": "o1", "type": "function", "function": {"name": "create_powerpoint_presentation_mcp_mtn-office", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "s1", "content": "skill body"},
                {"role": "tool", "tool_call_id": "o1", "content": "Created deck.pptx"}]
    assert guards.flatten_tool_history(messages) == 2
    assert [c["id"] for c in messages[1]["tool_calls"]] == ["s1"]
    assert "[Used tool: create_powerpoint_presentation_mcp_mtn-office]" in messages[1]["content"]
    assert messages[2]["role"] == "tool"
    assert messages[3] == {"role": "assistant", "content": "[Tool result] Created deck.pptx"}


def test_a_slow_documents_route_falls_back_to_its_backup_route():
    class Transport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.models = []

        async def handle_async_request(self, request):
            model = json.loads(request.content)["model"]
            self.models.append(model)
            if model == "mtn-smart-docs":
                await asyncio.sleep(5)  # the primary never starts answering
            return httpx.Response(200, headers={"content-type": "text/event-stream",
                                                "x-model-router-selected-model": "openai/gpt-oss-120b"},
                                  content=sse(tool_call_chunk(), tool_finish_chunk()).encode())

    transport = Transport()
    settings = replace(Settings(prices=PRICES, model_tiers=TIERS, stats_poll_seconds=3600), first_byte_timeout=0.2)
    ledger = Ledger(PRICES, TIERS)
    client = TestClient(build_app(settings, ledger, httpx.AsyncClient(transport=transport, base_url="http://switchyard:4000")))
    r = docs_request(client, [{"role": "user", "content": "Create an Excel workbook of team tasks"}])
    assert r.status_code == 200 and '"tool_calls"' in r.text
    assert transport.models == ["mtn-smart-docs", "mtn-smart-docs-backup"]
    assert (ledger.recent[0].tier, ledger.recent[0].judge_route) == ("documents", "backup")


SKILL_BODY_MSG = {"role": "user", "content": "---\nname: meeting-minutes\ndescription: Use when asked for minutes. Offer to create a Word file.\n---\n\n# Meeting minutes\nOffer to create a Word document with create_word_document."}


def test_a_loaded_skill_body_is_not_mistaken_for_the_users_request(fake):
    fake.set("mtn-smart-skill", headers={"x-model-router-selected-model": "openai/gpt-oss-120b"},
             body=sse(chunk("Meeting: Ops sync"), chunk(finish="stop")))
    client, ledger = make_docs(fake, redact_prompts=False)
    messages = [{"role": "user", "content": "Minute this: Ops sync, decided to freeze changes."},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "s1", "type": "function",
                 "function": {"name": "skill", "arguments": "{\"skillName\": \"meeting-minutes\"}"}}]},
                {"role": "tool", "tool_call_id": "s1", "content": "Skill loaded."},
                SKILL_BODY_MSG]
    client.post("/v1/chat/completions", json={"model": "mtn-smart", "stream": True, "messages": messages,
                                              "tools": OFFICE_TOOLS + SKILL_TOOLS})
    sent = fake.requests[0]
    assert sent["model"] == "mtn-smart-skill"  # skill step, not the documents tier
    assert "tools" in sent and all(t["function"]["name"] in ("skill", "read_file") for t in sent["tools"])
    d = ledger.recent[0]
    assert (d.tier, d.judge_route, d.reason) == ("balanced", "none", "skill step")
    assert d.prompt.startswith("Minute this")


def test_skill_messages_are_recognised_by_their_front_matter():
    assert guards.is_skill_message(SKILL_BODY_MSG)
    assert not guards.is_skill_message({"role": "user", "content": "--- quick note ---\nplease summarise"})
    assert not guards.is_skill_message({"role": "assistant", "content": SKILL_BODY_MSG["content"]})
    msgs = [{"role": "user", "content": "make it a Word document"}, SKILL_BODY_MSG]
    assert guards.real_user_text(msgs) == "make it a Word document"


@pytest.mark.parametrize("text,expected", [
    ("Attached file(s): sales_2026.xlsx\nWhat are the trends?", True),
    ("Can you analyse this spreadsheet for me?", True),
    ("Build a dashboard from my Excel workbook", True),
    ("Give me insights from the data in team list.csv", True),
    ("What is a spreadsheet?", False),
    ("Summarise this policy for me", False),
])
def test_spreadsheet_analysis_requests(text, expected):
    assert guards.insights_request(text) is expected


def test_spreadsheet_analysis_goes_to_the_documents_tier(fake):
    fake.set("mtn-smart-docs", headers={"x-model-router-selected-model": DOCS_MODEL},
             body=sse(tool_call_chunk(), tool_finish_chunk()))
    client, ledger = make_docs(fake)
    tools = OFFICE_TOOLS + [{"type": "function", "function": {"name": "analyse_workbook_mcp_mtn-office", "parameters": {"type": "object"}}}]
    client.post("/v1/chat/completions", json={"model": "mtn-smart", "stream": True, "tools": tools, "messages": [
        {"role": "user", "content": "Attached file(s): sales.xlsx\nWhat are the main trends?"}]})
    assert fake.requests[0]["model"] == "mtn-smart-docs"
    assert ledger.recent[0].reason == "spreadsheet analysis"
