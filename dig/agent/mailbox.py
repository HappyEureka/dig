"""Agent-owned buffer of delivered, unconsumed DIG events."""

from __future__ import annotations

from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..node import DIGEvent


class DIGMailbox:
    """Pending events plus ids already presented to a firing."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.pending: List[DIGEvent] = []
        self.seen: set = set()

    def receive(self, event: DIGEvent) -> bool:
        """Buffer an event and stamp its arrival.

        Every buffered copy stamps DELIVERED -- a reroute back after a past
        settlement is a fresh arrival, and the append-only log should say so
        (`received_at` still derives the FIRST arrival per recipient)."""
        if event.id is not None and event.id in self.seen:
            return False
        if event in self.pending:
            return False
        event.stamp_delivered(self.agent_id)
        self.pending.append(event)
        return True

    def has_unseen(self) -> bool:
        """Return whether pending contains a never-presented event."""
        return any(e.id not in self.seen for e in self.pending)

    def retract(self, event: DIGEvent) -> bool:
        """Withdraw a buffered event (a routing rewrite took it away).

        Also clears the dedup memory for its id, so a later reroute BACK to
        this agent arrives as a fresh delivery. A no-op for events not
        currently buffered (e.g. already consumed)."""
        before = len(self.pending)
        if event.id is not None:
            self.pending = [e for e in self.pending if e.id != event.id]
            self.seen.discard(event.id)
        else:
            self.pending = [e for e in self.pending if e is not event]
        return len(self.pending) < before

    def commit(self, inputs: List[DIGEvent], resolved: List[DIGEvent]) -> None:
        """Mark presented inputs seen and remove inputs no longer pending."""
        self.seen.update(e.id for e in inputs if e.id is not None)
        taken = set(resolved)
        self.pending = [e for e in self.pending if e not in taken]
