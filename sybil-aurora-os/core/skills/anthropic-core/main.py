"""
anthropic-core — Prompt chaining, reasoning patterns, Claude API primitives.
"""

from __future__ import annotations

import os
from typing import Any

import anthropic

SKILL_NAME = "anthropic-core"

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def invoke(params: dict[str, Any]) -> dict[str, Any]:
    """Entry point — called by orchestrator or other agents."""
    mode = params["mode"]
    prompt = params["prompt"]
    context = params.get("context", [])
    model = params.get("model", "claude-opus-4-7")
    max_tokens = params.get("max_tokens", 4096)

    messages = _build_messages(mode, prompt, context)

    response = _get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )

    return {
        "result": response.content[0].text,
        "reasoning_trace": _extract_trace(response),
        "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
        "skill": SKILL_NAME,
    }


def _build_messages(mode: str, prompt: str, context: list[dict]) -> list[dict]:
    system_prompts = {
        "chain": "You are a reasoning engine. Process the input through a structured chain of thought and return a conclusive answer.",
        "reason": "You are an analytical reasoner. Break down the problem step by step before arriving at your conclusion.",
        "summarize": "You are a precise summarizer. Condense the input into structured, actionable key points.",
        "extract": "You are a data extractor. Pull structured information from the input and return it as JSON.",
    }

    messages: list[dict] = []
    for ctx in context:
        messages.append({"role": ctx.get("role", "user"), "content": ctx.get("content", "")})

    messages.append({"role": "user", "content": prompt})

    return [{"role": "system", "content": system_prompts.get(mode, system_prompts["reason"])}] + messages


def _extract_trace(response: Any) -> list[dict]:
    return [{"stop_reason": response.stop_reason, "model": response.model}]
