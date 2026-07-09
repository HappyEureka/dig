"""Base healer detection hooks."""

from __future__ import annotations

from abc import ABC
from typing import Dict, List

from ..graph import DIGActivation, DIGEvent, DIGGraph
from .intervention import Intervention


class Healer(ABC):
    """Base class for DIG healers: detect, and optionally finalize.

    A healer DETECTS graph-shaped anomalies through the three hooks below and
    proposes `Intervention`s. Mutating the graph is not its job -- the hook
    runners hand each proposed intervention to `apply_intervention`
    (`heal/apply.py`), calling `prepare_intervention` first so a healer can
    finalize details that should be decided at application time.

    Each healer counts its own detections (`detections`, filled by the hook
    runners): detection is a healer-side fact, not graph state. Applied
    interventions live IN the graph as system activations -- derive their
    counts with `heal.intervention_stats(dig)`. Subclasses with their own
    __init__ must call `super().__init__()`.
    """

    name: str = "Healer"

    def __init__(self) -> None:
        self.detections: Dict[str, int] = {}

    def on_activation_complete(
        self,
        dig: DIGGraph,
        activation: DIGActivation,
    ) -> List[Intervention]:
        """Called after an agent activation is recorded."""
        return []

    def on_event_delivered(
        self,
        dig: DIGGraph,
        event: DIGEvent,
        recipients: List[str],
    ) -> List[Intervention]:
        """Called after an event has been delivered."""
        return []

    def on_idle_tick(
        self,
        dig: DIGGraph,
        idle_cycles: int,
    ) -> List[Intervention]:
        """Called periodically when no activations are in progress."""
        return []

    def prepare_intervention(
        self,
        itv: Intervention,
        *,
        dig: DIGGraph,
    ) -> None:
        """Finalize one of this healer's interventions just before it is
        applied (default: nothing to finalize). Use for details that must be
        decided at application time, e.g. picking a designated handler from
        the live team load."""
        return None
