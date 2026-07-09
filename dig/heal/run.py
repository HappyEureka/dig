"""Hook runners for DIG-only healers."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from .apply import apply_intervention
from .healer import Healer
from .healers import (
    DeadlockHealer,
    DependencyWarningHealer,
    ExcessiveReroutingHealer,
    IncompleteCoverageHealer,
    MissedSubmissionHealer,
    OrphanEventHealer,
    RepeatedEffortsHealer,
)
from .intervention import Intervention


def default_healers() -> List[Any]:
    """Return the bundled DIG-only healer roster for a runtime."""
    return [
        OrphanEventHealer(),
        ExcessiveReroutingHealer(),
        RepeatedEffortsHealer(),
        DependencyWarningHealer(),
        IncompleteCoverageHealer(),
        MissedSubmissionHealer(),
        DeadlockHealer(),
    ]


def detection_stats(healers) -> Dict[str, int]:
    """Aggregate detection counts across a healer roster.

    Detection is a healer-side fact (a proposal, whether or not it was
    applied), so each healer counts its own (`Healer.detections`); the
    graph records only APPLIED interventions -- see `intervention_stats`.
    """
    out: Dict[str, int] = {}
    for healer in (healers or []):
        for detection_label, count in healer.detections.items():
            out[detection_label] = out.get(detection_label, 0) + count
    return out


def intervention_stats(dig) -> Dict[str, int]:
    """Derive applied-intervention counts from the recorded graph.

    Every applied intervention IS a system activation carrying
    `metadata["dig"]["intervention"]`, so the counts are a read over the
    record -- never stored state (derive, don't denormalize)."""
    out: Dict[str, int] = {}
    for activation in dig.activations.values():
        if activation.intervention_type:
            out[activation.intervention_type] = (
                out.get(activation.intervention_type, 0) + 1
            )
    return out


async def _run_hook(
    dig,
    healers,
    apply: bool,
    hook: Callable[[Healer], List[Intervention]],
) -> List[Any]:
    """Collect one hook's interventions across healers; optionally apply.

    Every detection is counted on its proposing healer; when applying, that
    healer gets to finalize each intervention (`prepare_intervention`)
    before `apply_intervention` mutates the graph.
    """
    delivered: List[Any] = []
    for h in (healers or []):
        for itv in hook(h):
            h.detections[itv.label] = h.detections.get(itv.label, 0) + 1
            if apply:
                h.prepare_intervention(itv, dig=dig)
                delivered.append(await apply_intervention(itv, dig=dig))
    return delivered


async def run_activation_healers(dig, activation, healers, apply: bool = False) -> List[Any]:
    """Run activation-complete hooks and optionally apply interventions."""
    return await _run_hook(
        dig, healers, apply, lambda h: h.on_activation_complete(dig, activation)
    )


async def run_event_healers(dig, event, recipients, healers, apply: bool = False) -> List[Any]:
    """Run event-delivered hooks and optionally apply interventions."""
    return await _run_hook(
        dig, healers, apply, lambda h: h.on_event_delivered(dig, event, recipients)
    )


async def run_idle_healers(dig, idle_cycles: int, healers, apply: bool = False) -> List[Any]:
    """Run idle hooks and optionally apply interventions."""
    return await _run_hook(
        dig, healers, apply, lambda h: h.on_idle_tick(dig, idle_cycles)
    )
