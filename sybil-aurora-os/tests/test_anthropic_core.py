"""
Tests for anthropic-core — the shared LLM-calling layer.

Coverage:
  - Contract compliance (status/data/meta shape)
  - Degraded mode (no API key) for all 6 tasks
  - Unknown task returns error
  - Backward compat: "mode" key maps to task
  - invoke alias
  - _parse_json edge cases
  - Mocked API calls for each task type
  - chain multi-step history threading
  - Error propagation from the API
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.skills.anthropic_core.main import (
    _degraded,
    _parse_json,
    invoke,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(text: str, model: str = "claude-opus-4-7", input_tokens: int = 100, output_tokens: int = 50, cache_read: int = 0):
    """Build a minimal mock of the Anthropic messages.create response."""
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
    )
    content = [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(content=content, model=model, usage=usage)


def _patched_client(response_text: str, **kwargs):
    """Context manager: patches _get_client so messages.create returns response_text."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response(response_text, **kwargs)
    return patch("core.skills.anthropic_core.main._get_client", return_value=mock_client)


# ---------------------------------------------------------------------------
# Degraded mode — no API key
# ---------------------------------------------------------------------------

class TestDegradedMode:
    """All tasks must return status:success with meta.degraded:True when no key is set."""

    def _call_degraded(self, task: str, extra: dict | None = None) -> dict:
        inp = {"task": task, **(extra or {})}
        with patch.dict("os.environ", {}, clear=True):
            with patch("core.skills.anthropic_core.main._ANTHROPIC_AVAILABLE", True):
                return run(inp)

    def test_chat_degraded_shape(self):
        result = self._call_degraded("chat", {"prompt": "hello"})
        assert result["status"] == "success"
        assert result["meta"]["degraded"] is True
        assert "response" in result["data"]

    def test_chain_degraded_shape(self):
        result = self._call_degraded("chain", {"steps": [{"prompt": "step1"}]})
        assert result["status"] == "success"
        assert result["meta"]["degraded"] is True
        assert "steps" in result["data"]
        assert "final_output" in result["data"]

    def test_reason_degraded_shape(self):
        result = self._call_degraded("reason", {"prompt": "why?"})
        assert result["status"] == "success"
        assert result["meta"]["degraded"] is True
        assert "reasoning" in result["data"]
        assert "conclusion" in result["data"]

    def test_summarize_degraded_shape(self):
        result = self._call_degraded("summarize", {"content": "some text"})
        assert result["status"] == "success"
        assert result["meta"]["degraded"] is True
        assert "summary" in result["data"]
        assert "key_points" in result["data"]

    def test_extract_degraded_shape(self):
        result = self._call_degraded("extract", {"content": "some text"})
        assert result["status"] == "success"
        assert result["meta"]["degraded"] is True
        assert "extracted" in result["data"]
        assert "raw" in result["data"]

    def test_classify_degraded_shape(self):
        result = self._call_degraded("classify", {"content": "some text"})
        assert result["status"] == "success"
        assert result["meta"]["degraded"] is True
        assert "classification" in result["data"]
        clf = result["data"]["classification"]
        assert "category" in clf
        assert "confidence" in clf

    def test_degraded_reason_is_present(self):
        result = self._call_degraded("chat")
        assert result["meta"].get("reason")

    def test_all_tasks_degraded(self):
        tasks = ["chat", "chain", "reason", "summarize", "extract", "classify"]
        for task in tasks:
            result = self._call_degraded(task)
            assert result["status"] == "success", f"task {task} returned non-success in degraded mode"
            assert result["meta"]["degraded"] is True, f"task {task} missing degraded flag"


# ---------------------------------------------------------------------------
# Unknown task
# ---------------------------------------------------------------------------

class TestUnknownTask:
    def test_unknown_task_returns_error(self):
        result = run({"task": "fly_to_moon"})
        assert result["status"] == "error"
        assert "Unknown task" in result["data"]["message"]

    def test_unknown_task_lists_valid_tasks(self):
        result = run({"task": "???"})
        assert "valid_tasks" in result["meta"]
        assert "chat" in result["meta"]["valid_tasks"]

    def test_unknown_task_includes_skill_name(self):
        result = run({"task": "bad"})
        assert result["meta"]["skill"] == "anthropic-core"


# ---------------------------------------------------------------------------
# Backward compatibility: "mode" key
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_mode_key_degrades_to_chat(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("core.skills.anthropic_core.main._ANTHROPIC_AVAILABLE", True):
                result = run({"mode": "chat", "prompt": "test"})
        assert result["status"] == "success"
        assert "response" in result["data"]

    def test_task_key_takes_precedence_over_mode(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("core.skills.anthropic_core.main._ANTHROPIC_AVAILABLE", True):
                result = run({"task": "summarize", "mode": "chat", "content": "text"})
        assert result["meta"]["task"] == "summarize"

    def test_neither_key_defaults_to_chat(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("core.skills.anthropic_core.main._ANTHROPIC_AVAILABLE", True):
                result = run({"prompt": "hi"})
        assert result["meta"]["task"] == "chat"


# ---------------------------------------------------------------------------
# invoke alias
# ---------------------------------------------------------------------------

def test_invoke_alias():
    assert invoke is run


# ---------------------------------------------------------------------------
# _parse_json helpers
# ---------------------------------------------------------------------------

class TestParseJson:
    def test_plain_json(self):
        assert _parse_json('{"a": 1}') == {"a": 1}

    def test_json_fenced(self):
        text = "```json\n{\"x\": 2}\n```"
        assert _parse_json(text) == {"x": 2}

    def test_json_fenced_no_language(self):
        text = "```\n{\"y\": 3}\n```"
        assert _parse_json(text) == {"y": 3}

    def test_embedded_json_in_prose(self):
        text = 'Here is the result: {"category": "buy", "confidence": 0.9, "reasoning": "good"} done.'
        result = _parse_json(text)
        assert result["category"] == "buy"

    def test_invalid_returns_empty_dict(self):
        assert _parse_json("this is not json at all") == {}

    def test_empty_string_returns_empty_dict(self):
        assert _parse_json("") == {}

    def test_whitespace_only_returns_empty_dict(self):
        assert _parse_json("   \n  ") == {}

    def test_nested_structure(self):
        assert _parse_json('{"a": {"b": 1}}') == {"a": {"b": 1}}

    def test_strips_leading_trailing_whitespace(self):
        assert _parse_json('  {"k": "v"}  ') == {"k": "v"}


# ---------------------------------------------------------------------------
# Mocked API — chat task
# ---------------------------------------------------------------------------

class TestChatTask:
    def test_chat_returns_response(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client("Hello, world!") as mock_get:
                result = run({"task": "chat", "prompt": "hi"})
        assert result["status"] == "success"
        assert result["data"]["response"] == "Hello, world!"

    def test_chat_meta_fields(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client("response", model="claude-opus-4-7", input_tokens=10, output_tokens=5):
                result = run({"task": "chat", "prompt": "test"})
        meta = result["meta"]
        assert meta["skill"] == "anthropic-core"
        assert meta["task"] == "chat"
        assert meta["model"] == "claude-opus-4-7"
        assert meta["tokens_used"] == 15
        assert meta["cache_read_tokens"] == 0

    def test_chat_with_cache_read(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client("ok", cache_read=200):
                result = run({"task": "chat", "prompt": "cached"})
        assert result["meta"]["cache_read_tokens"] == 200

    def test_chat_custom_system_prompt(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_response("reply")
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "chat", "prompt": "hi", "system": "Custom system"})
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["system"][0]["text"] == "Custom system"

    def test_chat_passes_context_as_prior_messages(self):
        context = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "ok"}]
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_response("reply")
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "chat", "prompt": "next", "context": context})
        messages = mock_client.messages.create.call_args[1]["messages"]
        assert messages[0]["content"] == "earlier"
        assert messages[-1]["content"] == "next"

    def test_chat_api_error_returns_error_status(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = RuntimeError("API down")
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                result = run({"task": "chat", "prompt": "hi"})
        assert result["status"] == "error"
        assert "API down" in result["data"]["message"]


# ---------------------------------------------------------------------------
# Mocked API — reason task
# ---------------------------------------------------------------------------

class TestReasonTask:
    def test_reason_returns_reasoning_and_conclusion(self):
        text = "First I think...\nThen I consider...\nTherefore: buy the asset."
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client(text):
                result = run({"task": "reason", "prompt": "Should I buy?"})
        assert result["status"] == "success"
        assert result["data"]["reasoning"] == text
        assert result["data"]["conclusion"] == "Therefore: buy the asset."

    def test_reason_uses_thinking(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_response("conclusion")
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "reason", "prompt": "analyse this"})
        call_kwargs = mock_client.messages.create.call_args[1]
        assert "thinking" in call_kwargs
        assert call_kwargs["thinking"]["type"] == "adaptive"

    def test_reason_empty_response_conclusion(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client(""):
                result = run({"task": "reason", "prompt": "?"})
        assert result["data"]["conclusion"] == ""


# ---------------------------------------------------------------------------
# Mocked API — summarize task
# ---------------------------------------------------------------------------

class TestSummarizeTask:
    def test_summarize_returns_summary_and_key_points(self):
        text = "- Point one\n- Point two\n- Point three"
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client(text):
                result = run({"task": "summarize", "content": "long text here"})
        assert result["status"] == "success"
        assert result["data"]["summary"] == text
        assert len(result["data"]["key_points"]) == 3

    def test_summarize_uses_content_key(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_response("summary")
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "summarize", "content": "my text"})
        messages = mock_client.messages.create.call_args[1]["messages"]
        assert "my text" in messages[-1]["content"]

    def test_summarize_falls_back_to_prompt_key(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_response("s")
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "summarize", "prompt": "fallback text"})
        messages = mock_client.messages.create.call_args[1]["messages"]
        assert "fallback text" in messages[-1]["content"]

    def test_summarize_key_points_capped_at_ten(self):
        text = "\n".join(f"- Point {i}" for i in range(20))
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client(text):
                result = run({"task": "summarize", "content": "x"})
        assert len(result["data"]["key_points"]) <= 10


# ---------------------------------------------------------------------------
# Mocked API — extract task
# ---------------------------------------------------------------------------

class TestExtractTask:
    def test_extract_parses_json_response(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client('{"name": "John", "age": 30}'):
                result = run({"task": "extract", "content": "John is 30 years old"})
        assert result["status"] == "success"
        assert result["data"]["extracted"] == {"name": "John", "age": 30}

    def test_extract_returns_raw_text(self):
        raw = '{"x": 1}'
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client(raw):
                result = run({"task": "extract", "content": "text"})
        assert result["data"]["raw"] == raw

    def test_extract_with_schema_sends_schema_in_prompt(self):
        schema = {"name": "string", "age": "integer"}
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_response('{"name": "x", "age": 1}')
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "extract", "content": "x", "schema": schema})
        prompt_content = mock_client.messages.create.call_args[1]["messages"][-1]["content"]
        assert "name" in prompt_content

    def test_extract_bad_json_returns_empty_extracted(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client("this is not json"):
                result = run({"task": "extract", "content": "x"})
        assert result["data"]["extracted"] == {}


# ---------------------------------------------------------------------------
# Mocked API — classify task
# ---------------------------------------------------------------------------

class TestClassifyTask:
    def test_classify_parses_classification(self):
        payload = '{"category": "buy", "confidence": 0.95, "reasoning": "strong fundamentals"}'
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client(payload):
                result = run({"task": "classify", "content": "great deal"})
        assert result["status"] == "success"
        clf = result["data"]["classification"]
        assert clf["category"] == "buy"
        assert clf["confidence"] == 0.95

    def test_classify_with_categories_in_prompt(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_response('{"category": "buy", "confidence": 1.0, "reasoning": "r"}')
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "classify", "content": "text", "categories": ["buy", "hold", "sell"]})
        prompt = mock_client.messages.create.call_args[1]["messages"][-1]["content"]
        assert "buy" in prompt

    def test_classify_bad_json_uses_fallback(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client("cannot parse this"):
                result = run({"task": "classify", "content": "text"})
        clf = result["data"]["classification"]
        assert clf["category"] == "unknown"
        assert clf["confidence"] == 0.0

    def test_classify_returns_raw(self):
        raw = '{"category": "hold", "confidence": 0.5, "reasoning": "meh"}'
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client(raw):
                result = run({"task": "classify", "content": "neutral text"})
        assert result["data"]["raw"] == raw


# ---------------------------------------------------------------------------
# Mocked API — chain task
# ---------------------------------------------------------------------------

class TestChainTask:
    def _two_step_client(self, responses: list[str]):
        """Returns a mock client that cycles through a list of response texts."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [_make_response(r) for r in responses]
        return mock_client

    def test_chain_returns_steps_and_final_output(self):
        steps = [{"prompt": "Step 1: gather data"}, {"prompt": "Step 2: analyse"}]
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = self._two_step_client(["data gathered", "analysis done"])
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                result = run({"task": "chain", "steps": steps})
        assert result["status"] == "success"
        assert len(result["data"]["steps"]) == 2
        assert result["data"]["final_output"] == "analysis done"

    def test_chain_threads_history(self):
        """Second call should include prior assistant turn in messages."""
        steps = [{"prompt": "A"}, {"prompt": "B"}]
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = self._two_step_client(["reply A", "reply B"])
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "chain", "steps": steps})
        second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
        roles = [m["role"] for m in second_call_messages]
        assert "assistant" in roles
        contents = [m["content"] for m in second_call_messages]
        assert "reply A" in contents

    def test_chain_single_prompt_fallback(self):
        """chain with no steps falls back to single chat call."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with _patched_client("single response"):
                result = run({"task": "chain", "prompt": "one shot"})
        assert result["status"] == "success"
        assert result["data"]["final_output"] == "single response"
        assert len(result["data"]["steps"]) == 1

    def test_chain_aggregates_tokens(self):
        steps = [{"prompt": "A"}, {"prompt": "B"}]
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = [
                _make_response("r1", input_tokens=100, output_tokens=50),
                _make_response("r2", input_tokens=200, output_tokens=75),
            ]
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                result = run({"task": "chain", "steps": steps})
        assert result["meta"]["tokens_used"] == 425

    def test_chain_uses_thinking_on_final_step_only(self):
        steps = [{"prompt": "A"}, {"prompt": "B"}, {"prompt": "C"}]
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = self._two_step_client(["r1", "r2", "r3"])
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "chain", "steps": steps})
        calls = mock_client.messages.create.call_args_list
        # First two calls should NOT have thinking
        assert "thinking" not in calls[0][1]
        assert "thinking" not in calls[1][1]
        # Last call should have thinking
        assert "thinking" in calls[2][1]


# ---------------------------------------------------------------------------
# _degraded helper directly
# ---------------------------------------------------------------------------

class TestDegradedHelper:
    def test_all_tasks_have_correct_shape(self):
        expected_keys = {
            "chat": {"response"},
            "chain": {"steps", "final_output"},
            "reason": {"reasoning", "conclusion"},
            "summarize": {"summary", "key_points"},
            "extract": {"extracted", "raw"},
            "classify": {"classification", "raw"},
        }
        for task, keys in expected_keys.items():
            result = _degraded(task, {})
            assert result["status"] == "success"
            for key in keys:
                assert key in result["data"], f"task={task} missing key={key}"

    def test_unknown_task_in_degraded_returns_response_key(self):
        result = _degraded("nonexistent", {})
        assert "response" in result["data"]

    def test_degraded_meta_contains_skill(self):
        result = _degraded("chat", {})
        assert result["meta"]["skill"] == "anthropic-core"

    def test_degraded_meta_contains_task(self):
        result = _degraded("reason", {})
        assert result["meta"]["task"] == "reason"


# ---------------------------------------------------------------------------
# Prompt caching wiring
# ---------------------------------------------------------------------------

class TestPromptCaching:
    def test_system_prompt_has_cache_control(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_response("ok")
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "chat", "prompt": "hi"})
        system_block = mock_client.messages.create.call_args[1]["system"]
        assert isinstance(system_block, list)
        assert system_block[0]["cache_control"] == {"type": "ephemeral"}

    def test_system_block_type_is_text(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_response("ok")
            with patch("core.skills.anthropic_core.main._get_client", return_value=mock_client):
                run({"task": "chat", "prompt": "hi"})
        system_block = mock_client.messages.create.call_args[1]["system"]
        assert system_block[0]["type"] == "text"
