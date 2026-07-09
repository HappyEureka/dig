"""DIGGraph event delivery methods."""

from __future__ import annotations

from typing import List

from ..node import DIGEvent
from ..util.validate import expect_type


class DIGDelivery:
    """Route events over the registered DIG agent roster."""

    def deliver(self, events: "DIGEvent | List[DIGEvent]") -> None:
        """Deliver recorded events to recipients not yet delivered to.

        Delivery state is derived from the DELIVERED stamps (`received_at`),
        never from reaction -- PENDING means only "no reaction yet". Routing
        INTENT does read the current reaction: a recipient whose entry is
        REROUTE was routed away and is skipped (`reroute_event` diverts)."""
        event_list = list(events) if isinstance(events, (list, tuple)) else [events]
        for event in event_list:
            expect_type(event, DIGEvent, what="DIGGraph.deliver")
        updated = False
        for event in event_list:
            if event.delivery_policy is None:
                continue
            mode = event.delivery_policy.get("mode", "immediate")
            if mode != "immediate":
                raise NotImplementedError(
                    f"delivery policy {mode!r} is not implemented; only 'immediate' is "
                    "supported (future interface: predicate-recipient delivery scheduler)"
                )
            received = event.received_at
            for recipient, reaction in event.recipients.items():
                if recipient in received:
                    continue
                if reaction.label == DIGEvent.Reaction.Label.REROUTE:
                    continue   # rerouted away: no longer an intended target
                agent = self.agents.get(recipient)
                if agent is not None:
                    agent.receive(event)
                    updated = True
        if updated:
            self._notify_update()
