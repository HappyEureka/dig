"""Intervention data returned by DIG healers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


@dataclass
class Intervention:
    """A requested annotate/create intervention."""

    class Label(str, Enum):
        """Built-in DIG-structural anomaly labels."""

        INCOMPLETE_COVERAGE = "incomplete_coverage"  # submission left root DIG inputs uncovered
        MISSED_SUBMISSION = "missed_submission"      # root DIG inputs covered but no submit
        ORPHANED_EVENT = "orphaned_event"            # event delivered but no live recipient
        EXCESSIVE_REROUTING = "excessive_rerouting"  # event bounced too many times
        REPEATED_EFFORTS = "repeated_efforts"        # multiple agents working on the same item
        DEPENDENCY_WARNING = "dependency_warning"    # agent mixing partials from distinct lineages
        DEADLOCK = "deadlock"                        # no progress; all agents idle/waiting

        def __str__(self) -> str:
            return self.value

    class Strategy(str, Enum):
        """How an intervention mutates the DIG."""

        ANNOTATE = "annotate"  # annotate (and optionally reroute) an existing event
        CREATE = "create"      # create + deliver a new system event

        def __str__(self) -> str:
            return self.value

    label: str  # Intervention.Label value or custom string
    strategy: Strategy
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    target_event_id: Optional[str] = None
    reroute_to: Optional[List[str]] = None

    recipients: Optional[List[str]] = None
    input_event_ids: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        target = self.target_event_id or self.recipients or "-"
        return (
            f"Intervention(label={self.label}, strategy={self.strategy}, target={target}, "
            f"message={self.message!r})"
        )

    @classmethod
    def annotate(
        cls,
        label: str,
        target_event_id: str,
        message: str,
        *,
        reroute_to: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Intervention":
        """Annotate (and optionally reroute) an existing event."""
        return cls(
            label=label,
            strategy=cls.Strategy.ANNOTATE,
            message=message,
            target_event_id=target_event_id,
            reroute_to=reroute_to,
            metadata=metadata or {},
        )

    @classmethod
    def create(
        cls,
        label: str,
        recipients: List[str],
        message: str,
        *,
        input_event_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Intervention":
        """Create a new system event for delivery to `recipients`."""
        return cls(
            label=label,
            strategy=cls.Strategy.CREATE,
            message=message,
            recipients=recipients,
            input_event_ids=input_event_ids or [],
            metadata=metadata or {},
        )
