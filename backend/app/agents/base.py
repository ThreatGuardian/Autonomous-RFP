"""Agent contract and the shared pipeline context.

Agents never call each other. Each reads the typed messages it depends on from
the :class:`PipelineContext`, writes exactly one message of its own, and records
an ordered trace of what it observed and decided in its :class:`StageLog`.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


class StageLog:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()
        self.entries: list[dict[str, Any]] = []

    def _add(self, level: str, message: str, data: dict[str, Any] | None) -> None:
        self.entries.append(
            {"t_ms": int((time.perf_counter() - self._t0) * 1000), "level": level, "message": message, "data": data or {}}
        )

    def info(self, message: str, **data: Any) -> None:
        self._add("info", message, data)

    def decision(self, message: str, **data: Any) -> None:
        self._add("decision", message, data)

    def warn(self, message: str, **data: Any) -> None:
        self._add("warning", message, data)


@dataclass
class PipelineContext:
    rfp_id: int
    reference: str
    raw_text: str
    company: dict[str, Any]
    overrides: dict[str, Any] = field(default_factory=dict)
    messages: dict[str, BaseModel] = field(default_factory=dict)

    def require(self, key: str) -> Any:
        if key not in self.messages:
            raise RuntimeError(f"Pipeline message '{key}' is not available yet")
        return self.messages[key]


class Agent(ABC):
    #: Stage identifier used in persistence and the UI.
    stage: str = ""
    #: Human-readable agent name.
    name: str = ""
    #: Message key this agent produces.
    produces: str = ""
    #: Message keys this agent consumes.
    consumes: tuple[str, ...] = ()

    @abstractmethod
    def run(self, ctx: PipelineContext, log: StageLog) -> BaseModel:
        """Do the work and return the produced message."""

    def summarize(self, output: BaseModel) -> str:
        return ""
