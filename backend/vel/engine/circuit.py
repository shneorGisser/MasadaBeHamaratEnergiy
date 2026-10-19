"""Canonical circuit document (CircuitModel).

This is the single source of truth for topology and component values. The 2D schematic
edits it, the 3D bench renders it, and the solver consumes it. Electrical connectivity
exists only through wires between named terminals; geometric proximity means nothing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TerminalRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    component: str = Field(min_length=1, max_length=64)
    terminal: str = Field(min_length=1, max_length=16)

    def key(self) -> str:
        return f"{self.component}.{self.terminal}"


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    type: str
    label: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    a: TerminalRef
    b: TerminalRef


class Placement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = 0.0
    y: float = 0.0
    rot: Literal[0, 90, 180, 270] = 0


class CircuitModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    components: list[Component] = Field(default_factory=list, max_length=500)
    wires: list[Wire] = Field(default_factory=list, max_length=2000)
    layout: dict[str, Placement] = Field(default_factory=dict)

    def component(self, cid: str) -> Component:
        for c in self.components:
            if c.id == cid:
                return c
        raise KeyError(cid)
