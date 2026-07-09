"""Persistent DIG agent entity state."""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from ..graph import DIGGraph
from ..node import DIGActivation, DIGEvent
from .mailbox import DIGMailbox


class DIGAgentEntity:
    """Persistent DIG participant associated with one agent id.

    Owns the per-agent loop machinery every runtime shares: the mailbox,
    receive-and-wake on delivery, the wake/wait primitive, and the firing
    lifecycle -- `activate()` opens one firing as a `DIGActivation` and
    records it on clean exit. Runtimes (`DIGAgent`'s autonomous loop, or
    any external agent loop) build on this entity; they do not redo it. The
    entity itself never decides WHEN to fire -- that is the runtime's call.
    """

    def __init__(
        self,
        agent_id: str,
        dig: DIGGraph,
    ):
        self.agent_id = agent_id
        self.dig = dig
        self.active = False
        self.mailbox = DIGMailbox(agent_id)
        self._wakeup = asyncio.Event()
        dig.register(self)

    def wake(self) -> None:
        """Nudge this entity's loop (delivery does this automatically)."""
        self._wakeup.set()

    def receive(self, events: "DIGEvent | List[DIGEvent]") -> bool:
        """Buffer delivered events, wake the loop, and return whether any
        new event arrived."""
        woke = False
        for event in (events if isinstance(events, (list, tuple)) else [events]):
            if self.mailbox.receive(event):
                woke = True
        if woke:
            self.wake()
        return woke

    async def _wait_for_mail(self, stop: Optional[asyncio.Event] = None) -> None:
        """Sleep until delivery (or an explicit `wake`) or stop."""
        if stop is None:
            await self._wakeup.wait()
            self._wakeup.clear()
            return
        wakeup = asyncio.ensure_future(self._wakeup.wait())
        stopped = asyncio.ensure_future(stop.wait())
        try:
            await asyncio.wait({wakeup, stopped}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (wakeup, stopped):
                if not task.done():
                    task.cancel()
        self._wakeup.clear()

    @contextmanager
    def activate(self) -> Iterator[DIGActivation]:
        """One firing, as a lifecycle. Entering marks this entity active and
        yields the firing itself -- a `DIGActivation` prefilled with the
        agent id, the span start, and the pending buffer as inputs (a
        firing's input is the agent's whole buffer). The runtime fills in
        what the firing produced (outputs, input reaction, tool calls,
        metadata). A clean exit records that same node into the DIG
        (`dig.record_activation` completes it in place -- id assigned,
        events interned) and reconciles the mailbox -- recording is part of
        the lifecycle, never a separate step to remember. An exception
        inside the block records the firing as FAILED and re-raises: the
        attempt stays observable (agent, inputs, span, error), but nothing
        is produced, no reactions are declared, and the mailbox is NOT
        committed, so the inputs stay pending for a retry."""
        activation = DIGActivation(
            agent_id=self.agent_id,
            inputs=list(self.mailbox.pending),
            started_at=time.time(),
        )
        self.active = True
        try:
            yield activation
        except BaseException as error:
            try:
                activation.mark_failed(error)
                self.dig.record_activation(activation)
            except Exception:
                pass   # bookkeeping must never mask the original failure
            raise
        finally:
            self.active = False
        self.dig.record_activation(activation)
        resolved = [
            event for event in activation.inputs
            if activation.reaction_to(event.id) != DIGEvent.Reaction.Label.WAIT
        ]
        self.mailbox.commit(activation.inputs, resolved=resolved)

    def visible_state(self) -> Dict[str, Any]:
        """Runtime state exposed to `DIGGraph.observe()`."""
        return {
            "agent_id": self.agent_id,
            "active": self.active,
            "mailbox": len(self.mailbox.pending),
            "pending_event_ids": [event.id for event in self.mailbox.pending],
        }
