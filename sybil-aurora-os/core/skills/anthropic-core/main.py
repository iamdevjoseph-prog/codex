"""
anthropic-core — Shared LLM-calling layer.

The single place in Sybil-Aurora OS where Claude API calls are made.
All skills and agents that need an LLM call route through here to get:
  - Prompt caching on stable system prompts (saves tokens on repeated calls)
  - Centralised model config (change default model in one place)
  - Structured {status, data, meta} output for every task
  - Graceful degradation when ANTHROPIC_API_KEY is absent

Supported tasks:
  chat       — single-turn conversational call
  chain      — multi-step: each step's output feeds the next as context
  reason     — extended analytical reasoning with adaptive thinking
  summarize  — condense input into structured key points
  extract    — pull structured JSON from unstructured text
  classify   — route/label input with confidence score
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    import anthropic as _anthropic_module
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _anthropic_module = None  # type: ignore[assignment]
    _ANTHROPIC_AVAILABLE = False

SKILL_NAME = "anthropic-core"

# Default model: most capable generally available model.
# Override per-call via input["model"].
_DEFAULT_MODEL = "claude-opus-4-7"

# Stable system prompts — cached at the API level on each call.
_SYSTEM_PROMPTS: dict[str, str] = {
    "chat": (
        "You are a helpful, precise assistant. "
        "Respond directly and concisely without preamble."
    ),
    "chain": (
        "You are a multi-step reasoning engine. "
        "Process each step carefully and build on prior steps. "
        "Return a conclusive, actionable answer."
    ),
    "reason": (
        "You are an analytical reasoner. "
        "Break down the problem, identify key factors and trade-offs, "
        "and arrive at a well-supported conclusion. "
        "Show your work."
    ),
    "summarize": (
        "You are a precise summarizer. "
        "Condense the input into structured, actionable key points. "
        "Prioritize the most important information. Be concise."
    ),
    "extract": (
        "You are a structured data extractor. "
        "Extract information from the input and return it as valid JSON only. "
        "No commentary. No markdown fences. Raw JSON only."
    ),
    "classify": (
        "You are a classification and routing engine. "
        "Analyze the input and return a JSON object with your classification. "
        "Valid JSON only — no commentary, no markdown fences."
    ),
}

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        if not _ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic package not installed — run: pip install anthropic")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
        _client = _anthropic_module.Anthropic(api_key=api_key)
    return _client


def run(input: dict[str, Any]) -> dict[str, Any]:
    # Backward-compat: old callers used "mode" key
    task = input.get("task") or input.get("mode", "chat")

    _TASKS = {
        "chat": _task_chat,
        "chain": _task_chain,
        "reason": _task_reason,
        "summarize": _task_summarize,
        "extract": _task_extract,
        "classify": _task_classify,
    }

    handler = _TASKS.get(task)
    if not handler:
        return {
            "status": "error",
            "data": {"message": f"Unknown task: {task}"},
            "meta": {"skill": SKILL_NAME, "valid_tasks": list(_TASKS)},
        }

    # Degrade gracefully when no API key — still return a valid output shape
    if not _ANTHROPIC_AVAILABLE or not os.environ.get("ANTHROPIC_API_KEY"):
        return _degraded(task, input)

    try:
        data = handler(input)
        model = data.pop("_model", _DEFAULT_MODEL)
        tokens = data.pop("_tokens", 0)
        cache_read = data.pop("_cache_read", 0)
        return {
            "status": "success",
            "data": data,
            "meta": {
                "skill": SKILL_NAME,
                "task": task,
                "model": model,
                "tokens_used": tokens,
                "cache_read_tokens": cache_read,
            },
        }
    except Exception as exc:
        return {
            "status": "error",
            "data": {"message": str(exc)},
            "meta": {"skill": SKILL_NAME, "task": task},
        }


def _call(
    prompt: str,
    system: str,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 4096,
    use_thinking: bool = False,
    prior_messages: list[dict] | None = None,
) -> tuple[str, str, int, int]:
    """
    Core single API call.
    Returns (response_text, model_used, total_tokens, cache_read_tokens).

    System prompt is always sent with cache_control so repeated calls with the
    same prompt hit the cache (~0.1x token cost vs full price).
    """
    client = _get_client()

    system_block = [
        {
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    messages = list(prior_messages or []) + [{"role": "user", "content": prompt}]

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_block,
        "messages": messages,
    }

    # Adaptive thinking for models that support it; helps on reasoning/chain tasks.
    # Not supported on models outside the 4.6/4.7 family.
    if use_thinking and model in ("claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6"):
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": "high"}

    response = client.messages.create(**kwargs)

    text = "".join(b.text for b in response.content if b.type == "text")
    total_tokens = response.usage.input_tokens + response.usage.output_tokens
    cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    return text, response.model, total_tokens, cache_read


# ---------------------------------------------------------------------------
# Task handlers — each returns a flat dict; _model/_tokens/_cache_read are
# stripped by run() and moved into meta before returning to the caller.
# ---------------------------------------------------------------------------

def _task_chat(input: dict) -> dict:
    prompt = input.get("prompt", "")
    model = input.get("model", _DEFAULT_MODEL)
    max_tokens = input.get("max_tokens", 4096)
    system = input.get("system", _SYSTEM_PROMPTS["chat"])
    context = input.get("context", [])  # list of {role, content}

    text, model_used, tokens, cache_read = _call(
        prompt=prompt,
        system=system,
        model=model,
        max_tokens=max_tokens,
        prior_messages=context,
    )
    return {"response": text, "_model": model_used, "_tokens": tokens, "_cache_read": cache_read}


def _task_chain(input: dict) -> dict:
    """
    Multi-step chaining. Input can provide:
      steps: [{prompt, system?}, ...]   — explicit steps list
      prompt: str                        — single-step fallback (same as chat)
    """
    steps: list[dict] = input.get("steps", [])
    model = input.get("model", _DEFAULT_MODEL)
    max_tokens = input.get("max_tokens", 4096)

    if not steps:
        # Single-prompt fallback
        result = _task_chat(input)
        result["steps"] = [{"step": 1, "prompt": input.get("prompt", ""), "response": result["response"]}]
        result["final_output"] = result["response"]
        return result

    history: list[dict] = []
    step_results = []
    total_tokens = 0
    total_cache = 0
    last_model = model

    for i, step in enumerate(steps):
        step_prompt = step.get("prompt", "")
        step_system = step.get("system", _SYSTEM_PROMPTS["chain"])
        is_last = i == len(steps) - 1

        text, last_model, tokens, cache_read = _call(
            prompt=step_prompt,
            system=step_system,
            model=model,
            max_tokens=max_tokens,
            use_thinking=is_last,
            prior_messages=history,
        )
        total_tokens += tokens
        total_cache += cache_read
        step_results.append({"step": i + 1, "prompt": step_prompt, "response": text})
        history += [
            {"role": "user", "content": step_prompt},
            {"role": "assistant", "content": text},
        ]

    return {
        "steps": step_results,
        "final_output": step_results[-1]["response"] if step_results else "",
        "_model": last_model,
        "_tokens": total_tokens,
        "_cache_read": total_cache,
    }


def _task_reason(input: dict) -> dict:
    prompt = input.get("prompt", "")
    model = input.get("model", _DEFAULT_MODEL)
    max_tokens = input.get("max_tokens", 8192)
    system = input.get("system", _SYSTEM_PROMPTS["reason"])

    text, model_used, tokens, cache_read = _call(
        prompt=prompt,
        system=system,
        model=model,
        max_tokens=max_tokens,
        use_thinking=True,
    )
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return {
        "reasoning": text,
        "conclusion": lines[-1] if lines else "",
        "_model": model_used,
        "_tokens": tokens,
        "_cache_read": cache_read,
    }


def _task_summarize(input: dict) -> dict:
    content = input.get("content") or input.get("prompt", "")
    model = input.get("model", _DEFAULT_MODEL)
    max_tokens = input.get("max_tokens", 2048)
    system = input.get("system", _SYSTEM_PROMPTS["summarize"])

    prompt = f"Summarize the following:\n\n{content}"
    text, model_used, tokens, cache_read = _call(
        prompt=prompt,
        system=system,
        model=model,
        max_tokens=max_tokens,
    )
    key_points = [l.strip("•-– ").strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("#")]
    return {
        "summary": text,
        "key_points": key_points[:10],
        "_model": model_used,
        "_tokens": tokens,
        "_cache_read": cache_read,
    }


def _task_extract(input: dict) -> dict:
    content = input.get("content") or input.get("prompt", "")
    schema = input.get("schema", {})
    model = input.get("model", _DEFAULT_MODEL)
    max_tokens = input.get("max_tokens", 2048)
    system = input.get("system", _SYSTEM_PROMPTS["extract"])

    prompt = "Extract structured data from the input."
    if schema:
        prompt += f"\n\nRequired JSON schema:\n{json.dumps(schema, indent=2)}"
    prompt += f"\n\nInput:\n{content}\n\nReturn ONLY valid JSON."

    text, model_used, tokens, cache_read = _call(
        prompt=prompt,
        system=system,
        model=model,
        max_tokens=max_tokens,
    )
    extracted = _parse_json(text)
    return {
        "extracted": extracted,
        "raw": text,
        "_model": model_used,
        "_tokens": tokens,
        "_cache_read": cache_read,
    }


def _task_classify(input: dict) -> dict:
    content = input.get("content") or input.get("prompt", "")
    categories = input.get("categories", [])
    model = input.get("model", _DEFAULT_MODEL)
    max_tokens = input.get("max_tokens", 512)
    system = input.get("system", _SYSTEM_PROMPTS["classify"])

    prompt = "Classify the following input."
    if categories:
        prompt += f"\n\nValid categories: {json.dumps(categories)}"
    prompt += (
        f"\n\nInput: {content}"
        '\n\nReturn JSON: {"category": "...", "confidence": 0.0-1.0, "reasoning": "..."}'
    )

    text, model_used, tokens, cache_read = _call(
        prompt=prompt,
        system=system,
        model=model,
        max_tokens=max_tokens,
    )
    result = _parse_json(text)
    if not result:
        result = {"category": "unknown", "confidence": 0.0, "reasoning": text}

    return {
        "classification": result,
        "raw": text,
        "_model": model_used,
        "_tokens": tokens,
        "_cache_read": cache_read,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict:
    """Strip markdown fences and parse JSON, returning {} on failure."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Try to extract a JSON object from within the text
        match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass
    return {}


def _degraded(task: str, input: dict) -> dict:
    """
    Return a well-shaped success response even when no API key is set.
    Callers that need real output can check meta.degraded.
    """
    placeholder: dict[str, Any] = {
        "chat": {"response": "[anthropic-core: no API key]"},
        "chain": {"steps": [], "final_output": "[anthropic-core: no API key]"},
        "reason": {"reasoning": "[anthropic-core: no API key]", "conclusion": ""},
        "summarize": {"summary": "[anthropic-core: no API key]", "key_points": []},
        "extract": {"extracted": {}, "raw": ""},
        "classify": {"classification": {"category": "unknown", "confidence": 0.0, "reasoning": ""}, "raw": ""},
    }.get(task, {"response": "[anthropic-core: no API key]"})

    return {
        "status": "success",
        "data": placeholder,
        "meta": {
            "skill": SKILL_NAME,
            "task": task,
            "degraded": True,
            "reason": "ANTHROPIC_API_KEY not set",
        },
    }


invoke = run
