"""Activation-side DIG node model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from .event import DIGEvent

DIG_METADATA = "dig"
DIG_STRUCTURAL = "structural"
DIG_SUBMITTING = "submitting"
DIG_FAILED = "failed"
DIG_INTERVENTION = "intervention"

# The reserved agent_id for system (healer/intervention) activations.
SYSTEM_AGENT_ID = "system"


@dataclass(eq=False)
class DIGActivation:
    """One agent firing."""

    class Label(str, Enum):
        PROBLEM_REDUCING = "problem-reducing"
        PROBLEM_GENERATING = "problem-generating"

    agent_id: str
    inputs: List[DIGEvent] = field(default_factory=list)
    outputs: List[DIGEvent] = field(default_factory=list)
    native_input: Any = None
    native_output: Any = None
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None
    input_reactions: Dict[str, DIGEvent.Reaction] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.metadata = self.normalize_metadata(self.metadata)
        for event in self.inputs:
            if not isinstance(event, DIGEvent):
                raise TypeError(
                    "DIGActivation.inputs must contain DIGEvent instances; "
                    f"got {event!r}"
                )
        for event in self.outputs:
            if not isinstance(event, DIGEvent):
                raise TypeError(
                    "DIGActivation.outputs must contain DIGEvent instances; "
                    f"got {event!r}"
                )
        self.input_reactions = {
            event_id: self.normalize_reaction(reaction)
            for event_id, reaction in self.input_reactions.items()
        }

    @staticmethod
    def normalize_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        out = dict(metadata or {})
        dig_metadata = out.get(DIG_METADATA)
        if dig_metadata is not None and not isinstance(dig_metadata, dict):
            raise TypeError('DIGActivation.metadata["dig"] must be a dict')
        return out

    @staticmethod
    def normalize_reaction(reaction: Any) -> DIGEvent.Reaction:
        if not isinstance(reaction, DIGEvent.Reaction):
            raise TypeError(
                "input_reactions values must be DIGEvent.Reaction instances; "
                f"got {reaction!r}"
            )
        return reaction

    @classmethod
    def check_input_reactions_shape(
        cls,
        events: Sequence[DIGEvent],
        raw: Any,
    ) -> None:
        """Validate a reaction declaration WITHOUT touching ids.

        The record funnel calls this before it mutates the graph, so an
        ill-shaped declaration raises while the graph is still untouched
        (no partially interned events)."""
        if raw is None:
            return
        if isinstance(raw, (list, tuple)):
            if len(raw) != len(events):
                raise ValueError(
                    "input reaction sequence length "
                    f"{len(raw)} does not match {len(events)} input events"
                )
            for reaction in raw:
                cls.normalize_reaction(reaction)
            return
        if not isinstance(raw, dict):
            raise TypeError(
                "input reaction must be a dict, a sequence of DIGEvent.Reaction "
                "values, or None"
            )
        for reaction in raw.values():
            cls.normalize_reaction(reaction)

    @classmethod
    def normalize_input_reactions(
        cls,
        events: Sequence[DIGEvent],
        raw: Any,
    ) -> Dict[str, DIGEvent.Reaction]:
        """Normalize activation input reaction for events already known to DIG."""
        if raw is None:
            raw = {}
        elif isinstance(raw, (list, tuple)):
            if len(raw) != len(events):
                raise ValueError(
                    "input reaction sequence length "
                    f"{len(raw)} does not match {len(events)} input events"
                )
            raw = {event.id: label for event, label in zip(events, raw)}
        if not isinstance(raw, dict):
            raise TypeError(
                "input reaction must be a dict, a sequence of DIGEvent.Reaction "
                "values, or None"
            )

        out: Dict[str, DIGEvent.Reaction] = {}
        for event in events:
            if event.id is None:
                raise ValueError(
                    "cannot label an input event before it has been recorded in DIG"
                )
            out[event.id] = cls.normalize_reaction(
                raw.get(
                    event.id,
                    DIGEvent.Reaction(DIGEvent.Reaction.Label.CONSUME),
                )
            )
        return out

    @property
    def dig_metadata(self) -> Dict[str, Any]:
        dig_metadata = self.metadata.setdefault(DIG_METADATA, {})
        if not isinstance(dig_metadata, dict):
            raise TypeError('DIGActivation.metadata["dig"] must be a dict')
        return dig_metadata

    @property
    def label(self) -> Label:
        value = self.metadata.get(DIG_METADATA, {}).get(DIG_STRUCTURAL)
        if value is not None:
            return DIGActivation.Label(value)
        return self.identify_label()

    @property
    def is_submitting(self) -> bool:
        return bool(self.metadata.get(DIG_METADATA, {}).get(DIG_SUBMITTING, False))

    @property
    def failed(self) -> bool:
        return bool(self.metadata.get(DIG_METADATA, {}).get(DIG_FAILED))

    @property
    def intervention_type(self) -> Optional[str]:
        value = self.metadata.get(DIG_METADATA, {}).get(DIG_INTERVENTION)
        return str(value) if value is not None else None

    def mark_failed(self, error: BaseException) -> None:
        """Mark this firing FAILED (`metadata["dig"]["failed"]`): it raised
        instead of completing. A failed firing is an observability record of
        the attempt -- it keeps its agent, inputs, and span, but produces
        nothing and declares no reactions (the record funnel enforces both),
        so its inputs stay pending and coverage analyses skip it."""
        self.dig_metadata[DIG_FAILED] = {
            "error": type(error).__name__,
            "message": str(error),
        }

    def identify_label(self) -> Label:
        if len(self.outputs) > len(self.inputs):
            return DIGActivation.Label.PROBLEM_GENERATING
        return DIGActivation.Label.PROBLEM_REDUCING

    def annotate_recorded(self) -> None:
        """Stamp this node's own annotation namespace (`metadata["dig"]`) at
        record time: the structural label derives from the recorded shape
        (`identify_label`), and only truthy submitting/intervention
        annotations are kept. The node owns both sides of its namespace --
        the graph funnel just calls this."""
        self.metadata = self.normalize_metadata(self.metadata)
        dig_metadata = dict(self.metadata.get(DIG_METADATA, {}))
        dig_metadata[DIG_STRUCTURAL] = self.identify_label().value
        if dig_metadata.get(DIG_SUBMITTING):
            dig_metadata[DIG_SUBMITTING] = True
        else:
            dig_metadata.pop(DIG_SUBMITTING, None)
        if not dig_metadata.get(DIG_FAILED):
            dig_metadata.pop(DIG_FAILED, None)
        if not dig_metadata.get(DIG_INTERVENTION):
            dig_metadata.pop(DIG_INTERVENTION, None)
        self.metadata[DIG_METADATA] = dig_metadata

    @property
    def input_event_ids(self) -> List[str]:
        return [event.id for event in self.inputs]

    @property
    def output_event_ids(self) -> List[str]:
        return [event.id for event in self.outputs]

    def reaction_to(self, event_id: str) -> DIGEvent.Reaction.Label:
        """How THIS firing reacted to one of its input events.

        Reads the event's REACTED stamp for this firing when recorded, else
        the declared `input_reactions` entry, else the record default
        (CONSUME) for a not-yet-recorded preview. An id that is not among
        this firing's inputs raises ValueError -- a typo must never read as
        a silent consume. (`DIGEvent.reaction_label_for` is the event-side
        question: what did an activation/agent stamp on ME.)"""
        match = next(
            (event for event in self.inputs if event.id == event_id), None
        )
        if event_id is None or match is None:
            raise ValueError(
                f"event {event_id!r} is not an input of activation {self.id or '-'}"
            )
        if self.failed:
            # A failed firing declared no reactions; the default-CONSUME
            # fallback below must not make derived views show consumption.
            return DIGEvent.Reaction.Label.PENDING
        stamped = match.reaction_label_for(
            activation_id=self.id,
            agent_id=self.agent_id,
        )
        if stamped is not None:
            return stamped
        reaction = self.input_reactions.get(event_id)
        if reaction is None:
            return DIGEvent.Reaction.Label.CONSUME
        return reaction.label

    def _inputs_with(self, label: "DIGEvent.Reaction.Label") -> List[str]:
        return [
            event.id for event in self.inputs
            if event.id is not None and self.reaction_to(event.id) == label
        ]

    @property
    def consumed_event_ids(self) -> List[str]:
        return self._inputs_with(DIGEvent.Reaction.Label.CONSUME)

    @property
    def waited_event_ids(self) -> List[str]:
        return self._inputs_with(DIGEvent.Reaction.Label.WAIT)

    @property
    def discarded_event_ids(self) -> List[str]:
        return self._inputs_with(DIGEvent.Reaction.Label.DISCARD)

    def __str__(self) -> str:
        inputs = ",".join(event.id or "-" for event in self.inputs) or "-"
        outputs = ",".join(event.id or "-" for event in self.outputs) or "-"
        return (
            f"DIGActivation(id={self.id or '-'}, agent={self.agent_id}, "
            f"label={self.label.value}, inputs=[{inputs}], outputs=[{outputs}], "
            f"tool_calls={len(self.tool_calls)})"
        )
