"""
incomplete_coverage.py

IncompleteCoverageHealer -- fires when an agent SUBMITs a final
answer while DIG interaction-lineage coverage isn't complete.

The verdict is DIG-only: when a SUBMIT activation lands, walk
backward through the DIG to find every root input event reachable
from it. If any root event in the DIG is NOT in that lineage, the
submission lacks required observed information lineage -- fire the
healer.

This is a pure DIG-graph check -- it never consults a work-structure
model (that belongs to the domain/env side). It is not a
task-completeness verdict; it is an interaction/provenance verdict.

Intervention: annotate each output event of the SUBMIT activation
and reroute it back to the submitting agent so the agent
re-processes its own (premature) solution. The message lists which
root events were not in the lineage.

Attempt limit: after `max_attempts` global emissions the healer
stops firing (let the (max+1)th submission through).
"""

from __future__ import annotations

from typing import List

from ...graph import DIGActivation, DIGGraph
from ...views import lineage_covers_root_events, uncovered_root_events
from ..intervention import Intervention
from ..healer import Healer


class IncompleteCoverageHealer(Healer):
    name = "IncompleteCoverageHealer"

    def __init__(self, *, max_attempts: int = 3) -> None:
        super().__init__()
        self._max_attempts = max_attempts
        self._emission_count = 0  # global counter

    def on_activation_complete(
        self,
        dig: DIGGraph,
        activation: DIGActivation,
    ) -> List[Intervention]:
        # Only SUBMIT activations are candidates.
        if not activation.is_submitting:
            return []

        # DIG-only verdict: backward lineage from this SUBMIT must
        # cover every root input event in the DIG.
        if lineage_covers_root_events(dig, activation.id):
            return []

        # Attempt limit -- let the (max+1)th submission through.
        if self._emission_count >= self._max_attempts:
            return []

        # One Intervention per output event (typically just the
        # solution event, but support multiple).
        if not activation.output_event_ids:
            return []

        uncovered = [ev.id for ev in uncovered_root_events(dig, activation.id)]
        message = self._build_message(uncovered)
        out: List[Intervention] = []
        for ev_id in activation.output_event_ids:
            out.append(
                Intervention.annotate(
                    label=Intervention.Label.INCOMPLETE_COVERAGE.value,
                    target_event_id=ev_id,
                    message=message,
                    reroute_to=[activation.agent_id],
                    metadata={
                        "submitter": activation.agent_id,
                        "attempt": self._emission_count + 1,
                        "max_attempts": self._max_attempts,
                        "uncovered_root_events": uncovered,
                    },
                )
            )

        self._emission_count += 1
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_message(self, uncovered: List[str]) -> str:
        if uncovered:
            shown = uncovered if len(uncovered) <= 5 else uncovered[:5] + ["..."]
            tail = (
                f" Root DIG events not in your submission's lineage: {shown}. "
                f"Broadcast your current partial to other agents and "
                f"coordinate to finish."
            )
        else:
            tail = (
                " Broadcast your partial to other agents and coordinate "
                "to finish."
            )
        attempt = self._emission_count + 1
        return (
            f"SYSTEM: Submission blocked -- the DIG information lineage is incomplete "
            f"(attempt {attempt}/{self._max_attempts})."
            + tail
        )
