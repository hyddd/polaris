from dataclasses import dataclass, field


@dataclass
class AgentRequest:
    message: str
    session_id: str


@dataclass
class AgentResponse:
    response: str
    steps: list[str] = field(default_factory=list)
