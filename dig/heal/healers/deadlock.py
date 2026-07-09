"""
deadlock.py

DeadlockHealer -- fires when the Runtime has been idle (no
in-progress activations) for more than `threshold` consecutive ticks
AND no activation in the DIG has rolled up all root DIG inputs yet.

DIG-only verdict: "covered" means at least one activation's backward
lineage covers every root event in the DIG
(`views.any_coverage_complete(dig)`). "Stuck" means no such activation
exists. This filters the most common false alarm: the observed input
lineage has already been rolled up and the Runtime is naturally quiet.

Trigger is DIG-flavored (idle counter belongs to the execution
environment, surfaced via `on_idle_tick`); the verdict is also
pure DIG. The recipients are the registered roster (`dig.agents`) at
fire time -- the healer carries no caller-supplied state.

The `threshold` must stay BELOW the runtime's own idle shutdown limit
(if its idle monitor ends the run after N quiet cycles), or the healer
can never fire.

Intervention: a new system event delivered to every registered agent
telling them to act with what they have. Once per stretch of idleness --
if activity resumes (idle_cycles drops) the healer resets and can fire
again on the next stretch.
"""

from __future__ import annotations

from typing import List, Optional

from ...graph import DIGGraph
from ...views import any_coverage_complete, untouched_root_events
from ..intervention import Intervention
from ..healer import Healer


class DeadlockHealer(Healer):
    name = "DeadlockHealer"

    def __init__(self, *, threshold: int = 40) -> None:
        super().__init__()
        self._threshold = threshold
        self._last_emit_idle: Optional[int] = None  # None = no prior emission

    def on_idle_tick(
        self,
        dig: DIGGraph,
        idle_cycles: int,
    ) -> List[Intervention]:
        # If activity resumed (idle resets to a smaller count), allow
        # a future emission.
        if (
            self._last_emit_idle is not None
            and idle_cycles < self._last_emit_idle
        ):
            self._last_emit_idle = None

        if idle_cycles < self._threshold:
            return []
        if self._last_emit_idle is not None:
            return []  # already fired this stretch

        # DIG-only cross-check: "stuck" vs "lineage covered." If anyone
        # has all root events in their lineage, the run is winding down
        # rather than deadlocked from DIG's perspective.
        if any_coverage_complete(dig):
            return []

        # The addressable team is the registered roster, read at fire time.
        recipients = sorted(dig.agents)
        if not recipients:
            return []

        self._last_emit_idle = idle_cycles
        untouched = [ev.id for ev in untouched_root_events(dig)]
        return [
            Intervention.create(
                label=Intervention.Label.DEADLOCK.value,
                recipients=recipients,
                message=(
                    f"SYSTEM: No progress for {idle_cycles} consecutive ticks. "
                    f"Process with what you have and share results with other "
                    f"agents (including yourself) -- unless you truly need to "
                    f"wait for a specific input."
                ),
                metadata={
                    "idle_cycles": idle_cycles,
                    "threshold": self._threshold,
                    "untouched_root_events": untouched,
                },
            )
        ]
