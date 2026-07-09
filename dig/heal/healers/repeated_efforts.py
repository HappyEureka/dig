"""Healer for one event delivered to multiple live recipients."""

from __future__ import annotations

from typing import Callable, List, Optional, Set

from ...graph import DIGEvent, DIGGraph
from ..intervention import Intervention
from ..healer import Healer


class RepeatedEffortsHealer(Healer):
    """Designate a sole handler when one event lands on multiple recipients.

    The anomaly is graph-shaped: several live recipients of the SAME event
    may each independently work on it. Which events represent
    work-for-one-handler (rather than broadcast FYI) is domain knowledge, so
    `relevant` narrows the watched events -- e.g. a runtime passes a
    predicate for its solution events. With `relevant=None` every
    multi-recipient event qualifies.
    """

    name = "RepeatedEffortsHealer"

    def __init__(
        self,
        *,
        relevant: Optional[Callable[[DIGEvent], bool]] = None,
    ) -> None:
        super().__init__()
        self._relevant = relevant
        self._seen: Set[str] = set()

    def on_event_delivered(
        self,
        dig: DIGGraph,
        event: DIGEvent,
        recipients: List[str],
    ) -> List[Intervention]:
        if event.id in self._seen:
            return []
        if len(recipients) <= 1:
            return []
        if self._relevant is not None and not self._relevant(event):
            return []

        self._seen.add(event.id)
        return [
            Intervention.annotate(
                label=Intervention.Label.REPEATED_EFFORTS.value,
                target_event_id=event.id,
                message="",  # filled in by prepare_intervention()
                metadata={
                    "candidates": list(recipients),
                    "needs_handler_selection": True,
                },
            )
        ]

    def prepare_intervention(
        self,
        itv: Intervention,
        *,
        dig: DIGGraph,
    ) -> None:
        """Choose the least-loaded recipient just before application."""
        if not itv.metadata.get("needs_handler_selection"):
            return

        candidates: List[str] = list(itv.metadata.get("candidates") or [])
        if not candidates:
            return

        team = dig.observe()
        loads = {c: team.get(c, {}).get("mailbox", 0) for c in candidates}
        designated = sorted(candidates, key=lambda c: loads[c])[0]
        others = [c for c in candidates if c != designated]

        itv.metadata["designated_handler"] = designated
        itv.metadata["candidate_loads"] = loads
        itv.metadata["needs_handler_selection"] = False

        if others:
            others_str = ", ".join(others)
            tail = (
                f" The other recipients ({others_str}) will NOT receive "
                f"this event -- discard signal handled at the system level."
            )
        else:
            tail = ""
        itv.message = (
            f"SYSTEM NOTICE: This event has {len(candidates)} "
            f"original recipients ({', '.join(candidates)}). To avoid "
            f"redundant merge, {designated} has been designated as "
            f"the sole handler (least-loaded at selection time, "
            f"loads={loads}).{tail}"
        )

        itv.reroute_to = [designated]
