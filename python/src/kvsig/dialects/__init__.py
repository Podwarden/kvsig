"""Dialect adapters: one module per API request format."""

from __future__ import annotations

from typing import Literal

Dialect = Literal["openai.chat", "openai.responses", "anthropic.messages", "openai.completions"]

#: Dialects this release implements.
SUPPORTED: tuple[str, ...] = ("openai.chat", "openai.responses", "anthropic.messages")
