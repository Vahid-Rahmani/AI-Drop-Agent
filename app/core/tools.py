"""Typed tool registry with explicit read/write permission metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.domain import PermissionLevel


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    permission_level: PermissionLevel
    mutating: bool
    handler: Callable[..., Any] | None = None
    timeout_seconds: float = 10.0
    max_retries: int = 0


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        return self._tools[name]

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def invoke(
        self,
        name: str,
        *args: Any,
        caller_permission: PermissionLevel = PermissionLevel.READ,
        **kwargs: Any,
    ) -> Any:
        tool = self.get(name)
        if tool.permission_level > caller_permission:
            raise PermissionError(
                f"tool {name} requires permission level {int(tool.permission_level)}"
            )
        if tool.handler is None:
            raise RuntimeError(f"tool has no handler: {name}")
        return tool.handler(*args, **kwargs)
