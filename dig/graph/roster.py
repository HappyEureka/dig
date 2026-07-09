"""Registered DIG agent endpoints and observable runtime state."""

from __future__ import annotations

from typing import Any, Dict


class DIGRoster:
    """Agent endpoints that can receive DIG-delivered events."""

    def register(self, agent: Any) -> None:
        """Register an agent with DIGGraph delivery and observation."""
        mailbox = getattr(agent, "mailbox", None)
        if (
            not getattr(agent, "agent_id", None)
            or not callable(getattr(agent, "receive", None))
            or not callable(getattr(agent, "visible_state", None))
            or mailbox is None
            or not hasattr(mailbox, "pending")
            or not hasattr(agent, "active")
        ):
            raise TypeError(
                "DIGGraph.register expects an agent with `agent_id`, a `receive(event)` "
                "method, a `visible_state()` method, a `mailbox` (a DIGMailbox, with "
                "`.pending`), and an `active` flag; got "
                f"{type(agent).__name__}. Use DIGAgentEntity, DIGAgent, "
                "or provide the same registered-agent surface."
            )
        existing = self.agents.get(agent.agent_id)
        if existing is not None and existing is not agent:
            raise ValueError(
                f"DIG agent id {agent.agent_id!r} is already registered; "
                "unregister it first or pick a distinct id (silently replacing "
                "the endpoint would steal its deliveries)"
            )
        self.agents[agent.agent_id] = agent

    def unregister(self, agent_id: str) -> Any:
        """Remove and return a registered agent endpoint."""
        try:
            return self.agents.pop(agent_id)
        except KeyError as exc:
            raise KeyError(f"unknown DIG agent id: {agent_id}") from exc

    def is_registered(self, agent_id: str) -> bool:
        """Return whether an agent id is addressable through DIG delivery."""
        return agent_id in self.agents

    def observe(self) -> Dict[str, Any]:
        """Summarize registered agents from the state they expose."""
        return {
            agent_id: agent.visible_state()
            for agent_id, agent in self.agents.items()
        }
