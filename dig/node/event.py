"""Event-side DIG node model."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Event-annotation metadata keys: written by heal (`apply_intervention`),
# read by views/viz. One definition, so a rename cannot silently split the
# writers from the readers.
EVENT_INTERVENTION_TYPE = "intervention_type"
EVENT_SYSTEM_ACTIVATION_ID = "system_activation_id"
EVENT_INTERVENTION_MESSAGE = "message"


@dataclass(eq=False)
class DIGEvent:
    """One thing that flowed between agents."""

    class Label(str, Enum):
        COMMUNICATION = "communication"
        TOOL = "tool"

    @dataclass
    class Reaction:
        """Per-recipient reaction record stored on a DIG event."""

        class Label(str, Enum):
            PENDING = "pending"
            CONSUME = "consume"
            WAIT = "wait"
            DISCARD = "discard"
            REROUTE = "reroute"

            def describe(self) -> str:
                """One-sentence prose for message/UI copy."""
                return _REACTION_DESCRIPTIONS[self]

            def __str__(self) -> str:
                # Like every sibling enum: str() is the value; prose is
                # opt-in via describe().
                return self.value

        label: Label = Label.PENDING
        routed_by: Optional[str] = None
        metadata: Dict[str, Any] = field(default_factory=dict)

        def __post_init__(self) -> None:
            if not isinstance(self.label, DIGEvent.Reaction.Label):
                raise TypeError(
                    "DIGEvent.Reaction.label must be a DIGEvent.Reaction.Label "
                    f"enum value; got {self.label!r}"
                )
            # A REROUTE without `routed_by` is a valid DECLARATION: the record
            # funnel attributes it with the activation id it mints
            # (`apply_reaction`). Recorded reroutes always carry provenance.

        def __str__(self) -> str:
            label = (
                "rerouted"
                if self.label == DIGEvent.Reaction.Label.REROUTE
                else self.label.value
            )
            parts = [label]
            if self.routed_by:
                parts.append(f"by {self.routed_by}")
            if self.metadata:
                details = ", ".join(f"{k}={v!r}" for k, v in self.metadata.items())
                parts.append(details)
            return " ".join(parts)

    @dataclass(frozen=True)
    class Timestamp:
        """One timestamped observation owned by a DIG event."""

        class Label(str, Enum):
            GENERATED = "generated"
            DELIVERED = "delivered"
            MODIFIED = "modified"
            REACTED = "reacted"

        label: Label
        at: float
        to: Optional[str] = None
        by: Optional[str] = None
        activation_id: Optional[str] = None
        agent_id: Optional[str] = None
        reaction_label: Optional[Reaction.Label] = None
        metadata: Dict[str, Any] = field(default_factory=dict)

        def __post_init__(self) -> None:
            if not isinstance(self.label, DIGEvent.Timestamp.Label):
                raise TypeError(
                    "DIGEvent.Timestamp.label must be DIGEvent.Timestamp.Label; "
                    f"got {self.label!r}"
                )
            if self.reaction_label is not None and not isinstance(
                self.reaction_label,
                DIGEvent.Reaction.Label,
            ):
                raise TypeError(
                    "DIGEvent.Timestamp.reaction_label must be a "
                    "DIGEvent.Reaction.Label enum value; "
                    f"got {self.reaction_label!r}"
                )
            if self.label == DIGEvent.Timestamp.Label.DELIVERED and not self.to:
                raise ValueError("delivered timestamps require `to`")
            if self.label == DIGEvent.Timestamp.Label.REACTED:
                if not self.activation_id or not self.agent_id or self.reaction_label is None:
                    raise ValueError(
                        "reacted timestamps require activation_id, agent_id, "
                        "and reaction_label"
                    )

        def __str__(self) -> str:
            at = f"{self.at:.6f}"
            if self.label == DIGEvent.Timestamp.Label.GENERATED:
                text = f"generated at {at}"
                if self.by:
                    text += f" by {self.by}"
            elif self.label == DIGEvent.Timestamp.Label.DELIVERED:
                text = f"delivered to {self.to} at {at}"
                if self.by:
                    text += f" by {self.by}"
            elif self.label == DIGEvent.Timestamp.Label.MODIFIED:
                text = f"modified at {at}"
                if self.by:
                    text += f" by {self.by}"
                if self.activation_id:
                    text += f" in activation {self.activation_id}"
            elif self.label == DIGEvent.Timestamp.Label.REACTED:
                text = f"{self.agent_id} reacted as {self.reaction_label.value} at {at}"
                if self.activation_id:
                    text += f" in activation {self.activation_id}"
            else:
                text = f"{self.label.value} at {at}"

            if self.metadata:
                details = ", ".join(f"{k}={v!r}" for k, v in self.metadata.items())
                text += f" ({details})"
            return text

    payload: Dict[str, Any] = field(default_factory=dict)
    label: Label = Label.COMMUNICATION
    id: Optional[str] = None
    source_activation_id: Optional[str] = None
    recipients: Dict[str, Reaction] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamps: List[Timestamp] = field(default_factory=list)
    delivery_policy: Optional[Dict[str, Any]] = field(
        default_factory=lambda: {"mode": "immediate"}
    )

    def __post_init__(self) -> None:
        if not isinstance(self.label, DIGEvent.Label):
            raise TypeError(
                "DIGEvent.label must be a DIGEvent.Label enum value; "
                f"got {self.label!r}"
            )
        if self.metadata is None:
            self.metadata = {}
        self.recipients = self._normalize_recipients(self.recipients)

    @staticmethod
    def _normalize_recipients(value: Any) -> Dict[str, Reaction]:
        """Normalize a recipients declaration to {agent_id: Reaction}.

        Addressing says WHO should get the event; reaction state is the
        graph's job, and the only valid state at creation is a fresh
        PENDING Reaction. So the shorthands -- one agent id, a sequence of
        agent ids, or a dict with None values -- all normalize to pending
        entries; explicit Reaction values pass through for callers that
        attach per-recipient metadata."""
        if value is None:
            return {}
        if isinstance(value, str):
            return {value: DIGEvent.Reaction()}
        if isinstance(value, (list, tuple)):
            out: Dict[str, DIGEvent.Reaction] = {}
            for agent_id in value:
                if not isinstance(agent_id, str):
                    raise TypeError(
                        "DIGEvent.recipients sequence entries must be agent-id "
                        f"strings; got {agent_id!r}"
                    )
                out[agent_id] = DIGEvent.Reaction()
            return out
        if isinstance(value, dict):
            out = {}
            for agent_id, reaction in value.items():
                if reaction is None:
                    reaction = DIGEvent.Reaction()
                elif not isinstance(reaction, DIGEvent.Reaction):
                    raise TypeError(
                        "DIGEvent.recipients values must be DIGEvent.Reaction instances "
                        f"or None; got {reaction!r} for {agent_id!r}"
                    )
                out[str(agent_id)] = reaction
            return out
        raise TypeError(
            "DIGEvent.recipients must be an agent id, a sequence of agent ids, "
            "or a dict of agent_id -> DIGEvent.Reaction (or None)"
        )

    @property
    def generated_at(self) -> Optional[float]:
        for timestamp in self.timestamps:
            if timestamp.label == DIGEvent.Timestamp.Label.GENERATED:
                return timestamp.at
        return None

    @property
    def received_at(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for timestamp in self.timestamps:
            if (
                timestamp.label == DIGEvent.Timestamp.Label.DELIVERED
                and timestamp.to
                and timestamp.to not in out
            ):
                out[timestamp.to] = timestamp.at
        return out

    @property
    def reaction_stamps(self) -> List[Timestamp]:
        return [
            timestamp
            for timestamp in self.timestamps
            if timestamp.label == DIGEvent.Timestamp.Label.REACTED
        ]

    def recipient_reactions_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """A plain-dict copy of the per-recipient reaction, for stamping a change
        record (before/after the routing was rewritten)."""
        return {
            agent_id: {
                "label": reaction.label.value,
                "routed_by": reaction.routed_by,
                "metadata": dict(reaction.metadata),
            }
            for agent_id, reaction in self.recipients.items()
        }

    def reaction_label_for(
        self,
        *,
        activation_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Optional[Reaction.Label]:
        for stamp in reversed(self.timestamps):
            if stamp.label != DIGEvent.Timestamp.Label.REACTED:
                continue
            if activation_id is not None and stamp.activation_id != activation_id:
                continue
            if agent_id is not None and stamp.agent_id != agent_id:
                continue
            return stamp.reaction_label
        return None

    def _stamp(self, label: Timestamp.Label, **extra: Any) -> None:
        self.timestamps.append(DIGEvent.Timestamp(label=label, at=time.time(), **extra))

    def stamp_generated(self) -> None:
        self._stamp(DIGEvent.Timestamp.Label.GENERATED)

    def stamp_delivered(self, to: str) -> None:
        self._stamp(DIGEvent.Timestamp.Label.DELIVERED, to=to)

    def stamp_modified(
        self,
        by: Optional[str] = None,
        *,
        activation_id: Optional[str] = None,
        **what: Any,
    ) -> None:
        """Stamp a MODIFIED observation. `by` names an AGENT actor;
        `activation_id` names an ACTIVATION actor (e.g. the rerouting
        firing) -- two id spaces, two fields, never mixed."""
        self._stamp(
            DIGEvent.Timestamp.Label.MODIFIED,
            by=by,
            activation_id=activation_id,
            metadata=dict(what),
        )

    def stamp_reaction(
        self,
        label: Reaction.Label,
        *,
        activation_id: str,
        agent_id: str,
    ) -> None:
        if not isinstance(label, DIGEvent.Reaction.Label):
            raise TypeError(
                "label must be a DIGEvent.Reaction.Label enum value; "
                f"got {label!r}"
            )
        self._stamp(
            DIGEvent.Timestamp.Label.REACTED,
            reaction_label=label,
            activation_id=activation_id,
            agent_id=agent_id,
        )

    def apply_reaction(
        self,
        reaction: Reaction,
        *,
        agent_id: str,
        activation_id: str,
    ) -> None:
        """The single write path for one recipient's reaction of this event.

        Backfills the delivered stamp if the recipient never formally received
        the event, appends the REACTED stamp (the log), and stores the declared
        reaction record ITSELF as the recipient's entry -- the declaration IS
        the current state, one object, never a copy. Writers replace recipient
        entries; they never mutate through them, so a past activation's
        declaration is never edited by anyone else.
        """
        if not isinstance(reaction, DIGEvent.Reaction):
            raise TypeError(
                "apply_reaction expects a DIGEvent.Reaction; "
                f"got {reaction!r}"
            )
        if (
            reaction.label == DIGEvent.Reaction.Label.REROUTE
            and reaction.routed_by is None
        ):
            # Complete the declaration: only the funnel knows the id it minted.
            reaction.routed_by = activation_id
        if agent_id not in self.received_at:
            self.stamp_delivered(agent_id)
        self.stamp_reaction(
            reaction.label,
            activation_id=activation_id,
            agent_id=agent_id,
        )
        self.recipients[agent_id] = reaction
        if reaction.label == DIGEvent.Reaction.Label.DISCARD:
            self.stamp_modified(by=agent_id, change="discard")

    def __str__(self) -> str:
        recipients = ",".join(self.recipients) or "-"
        source = self.source_activation_id or "root"
        return (
            f"DIGEvent(id={self.id or '-'}, label={self.label.value}, source={source}, "
            f"recipients=[{recipients}], payload={self.payload})"
        )


_REACTION_DESCRIPTIONS: Dict[DIGEvent.Reaction.Label, str] = {
    DIGEvent.Reaction.Label.PENDING: "recipient has not reacted to this event yet",
    DIGEvent.Reaction.Label.CONSUME: "recipient consumed this event",
    DIGEvent.Reaction.Label.WAIT: "recipient left this event pending",
    DIGEvent.Reaction.Label.DISCARD: "recipient discarded this event",
    DIGEvent.Reaction.Label.REROUTE: "recipient rerouted this event",
}
