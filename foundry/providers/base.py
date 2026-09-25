"""Provider-neutral contract for UCF intelligence backends.

The historical implementation uses Claude, but orchestration should depend on
capabilities rather than a concrete model vendor.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IntelligenceProvider(Protocol):
    """Minimal capability contract required by AgentRunner."""

    async def run(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        tools: list[str] | None = None,
        working_directory: str | None = None,
    ) -> dict:
        """Execute an unstructured reasoning/action request."""
        ...

    async def run_with_structured_output(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        output_schema: type,
        tools: list[str] | None = None,
        working_directory: str | None = None,
    ) -> dict:
        """Execute a request whose response must validate against a schema."""
        ...
