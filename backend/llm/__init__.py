"""LLM helpers — Anthropic Claude wrappers for screening-question
answering and cover-letter generation. Designed to gracefully degrade
when ANTHROPIC_API_KEY is not set (returns None; callers must handle).
"""

from .claude_client import ClaudeClient, get_client, is_enabled

__all__ = ["ClaudeClient", "get_client", "is_enabled"]
