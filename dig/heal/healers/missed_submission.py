"""
missed_submission.py

MissedSubmissionHealer -- fires when the just-completed activation
has rolled up the run's root DIG inputs (its backward lineage covers
every root event in the DIG) but no SUBMIT activation has been seen
yet, AND the activation isn't problem-expanding.

Inverse of IncompleteCoverage: that one catches "submitted too
early"; this one catches "should submit but hasn't." Trigger is
DIG-shaped: `views.lineage_covers_root_events(dig, activation.id)` is True
and `views.submit_activations(dig)` is empty.

This is an interaction-lineage hint, not a task-completeness verdict.
Task correctness belongs to the task/env side.

The "problem-reducing" constraint (num_output <= num_input) keeps
us from nudging an agent whose latest activation just decomposed
work -- they're in the middle of expanding, not converging.

Intervention: a fresh system event sent to the agent who just
acted, asking it to submit. Fires once per run (work either gets
submitted or doesn't; no point pestering).
"""

from __future__ import annotations

from typing import List

from ...graph import DIGActivation, DIGGraph
from ...views import lineage_covers_root_events, root_events, submit_activations
from ..intervention import Intervention
from ..healer import Healer


class MissedSubmissionHealer(Healer):
    name = "MissedSubmissionHealer"

    def __init__(self) -> None:
        super().__init__()
        self._emitted = False

    def on_activation_complete(
        self,
        dig: DIGGraph,
        activation: DIGActivation,
    ) -> List[Intervention]:
        if self._emitted:
            return []

        # If the agent IS currently submitting, don't nag -- they're
        # already on the right track.
        if activation.is_submitting:
            return []

        # DIG-shaped trigger: this activation's backward lineage
        # covers every root event in the DIG.
        if not lineage_covers_root_events(dig, activation.id):
            return []

        # If a SUBMIT activation has already been recorded, the
        # submission is in flight; don't fire.
        if submit_activations(dig):
            return []

        # Problem-reducing heuristic: skip if the agent just expanded
        # the problem (output > input).
        num_input = len(activation.input_event_ids)
        num_output = len(activation.output_event_ids)
        if num_output > num_input:
            return []

        self._emitted = True
        return [
            Intervention.create(
                label=Intervention.Label.MISSED_SUBMISSION.value,
                recipients=[activation.agent_id],
                message=(
                    f"SYSTEM NOTICE: Your activation lineage covers all root "
                    f"DIG inputs, but no submission has been made. Agent "
                    f"{activation.agent_id}, SUBMIT if your task-side result "
                    f"is complete; otherwise coordinate the final result with "
                    f"the other agents."
                ),
                metadata={
                    "target_agent": activation.agent_id,
                    "covering_activation_id": activation.id,
                    "root_events_in_lineage": [
                        ev.id for ev in root_events(dig)
                    ],
                },
            )
        ]
