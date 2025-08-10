from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class GuardRef(BaseModel):
    fn: str
    args: dict[str, object] = Field(default_factory=dict)


class Edge(BaseModel):
    source: str
    target: str
    guard: GuardRef | None = None
    priority: int = 0


class BaseNode(BaseModel):
    id: str
    kind: Literal["Question", "Decision", "Terminal"]
    label: str | None = None
    meta: dict[str, object] = Field(default_factory=dict)


class QuestionNode(BaseNode):
    kind: Literal["Question"] = "Question"
    key: str
    prompt: str
    validator: str | None = None


class DecisionNode(BaseNode):
    kind: Literal["Decision"] = "Decision"


class TerminalNode(BaseNode):
    kind: Literal["Terminal"] = "Terminal"
    reason: str | None = None


Node = Annotated[QuestionNode | DecisionNode | TerminalNode, Field(discriminator="kind")]


class PolicyPathSelection(BaseModel):
    lock_threshold: int = 2
    allow_switch_before_lock: bool = True


class Policies(BaseModel):
    path_selection: PolicyPathSelection | None = None


class Flow(BaseModel):
    schema_version: Literal["v1"] = "v1"
    id: str
    entry: str
    nodes: list[Node]
    edges: list[Edge]
    policies: Policies = Field(default_factory=Policies)

    def node_by_id(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None
