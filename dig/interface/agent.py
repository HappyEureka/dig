"""Callable agent adapter that records behavior activations into a DIG."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..graph import (
    DIGActivation,
    DIGEvent,
    DIGGraph,
)
from ..agent import DIGAgentEntity
from ..util.validate import is_instance_sequence


def _default_output_to_events(output: Any) -> List[DIGEvent]:
    """Convert the default output shapes into DIG events."""
    if output is None:
        return []
    if isinstance(output, DIGEvent):
        return [output]
    if is_instance_sequence(output, DIGEvent):
        return list(output)
    raise TypeError(
        f"DIGAgent: don't know how to map a {type(output).__name__} output to dig "
        "events. Pass an `output_to_events(output) -> list[DIGEvent]` adapter, or "
        "have the behavior return a DIGEvent / list[DIGEvent] / None."
    )


def _native_value(value: Any) -> Any:
    """DIGAgent's native-IO convention: store the native value only when it
    is not already DIG events."""
    if value is None or isinstance(value, DIGEvent) or is_instance_sequence(value, DIGEvent):
        return None
    return value


class DIGAgent(DIGAgentEntity):
    """Callable behavior adapter that records activations into a DIG."""

    def __init__(
        self,
        agent_id: str,
        behavior: Callable[[Any], Any],
        dig: DIGGraph,
        *,
        input_to_events: Optional[Callable[[Any], Sequence[DIGEvent]]] = None,
        events_to_input: Optional[Callable[[Sequence[DIGEvent]], Any]] = None,
        output_to_events: Optional[Callable[[Any], List[DIGEvent]]] = None,
        label_input_events: Optional[Callable[[Sequence[DIGEvent]], Any]] = None,
        trigger: Optional[Callable[["DIGAgent"], bool]] = None,
    ):
        super().__init__(agent_id, dig)
        self._behavior = behavior
        self._input_to_events = input_to_events
        self._events_to_input = events_to_input
        self._output_to_events = output_to_events
        self._label_input_events = label_input_events
        self._trigger = trigger

    def should_trigger(self) -> bool:
        """Return whether the callable wrapper should fire now."""
        if self._trigger is not None:
            return self._trigger(self)
        return not self.active and self.mailbox.has_unseen()

    async def run(self, stop: Optional[asyncio.Event] = None) -> None:
        """Run the autonomous mailbox loop until stopped."""
        while stop is None or not stop.is_set():
            await self._wait_for_mail(stop)
            while self.should_trigger() and (stop is None or not stop.is_set()):
                output_events, _ = await self.fire()
                self.dig.deliver(output_events)

    def input_to_events(self, value: Any) -> List[DIGEvent]:
        """Map native framework input to DIG events."""
        if self._input_to_events is not None:
            return list(self._input_to_events(value))
        if is_instance_sequence(value, DIGEvent):
            return list(value)
        raise TypeError(
            "DIGAgent needs `input_to_events(input) -> sequence[DIGEvent]` for native "
            f"{type(value).__name__} inputs"
        )

    def events_to_input(self, events: Sequence[DIGEvent]) -> Any:
        """Map DIG events to the behavior input."""
        if self._events_to_input is not None:
            return self._events_to_input(events)
        return events

    def output_to_events(self, output: Any) -> List[DIGEvent]:
        """Map behavior output to DIG events."""
        if self._output_to_events is not None:
            return self._output_to_events(output)
        return _default_output_to_events(output)

    def label_input_events(
        self,
        events: Sequence[DIGEvent],
    ) -> Dict[str, DIGEvent.Reaction]:
        """Return event-id -> reaction for this activation's inputs."""
        raw = None if self._label_input_events is None else self._label_input_events(events)
        return DIGActivation.normalize_input_reactions(events, raw)

    async def _record_call(
        self,
        inputs: List[DIGEvent],
        behavior_input: Any,
        *,
        native_input: Any = None,
        started_at: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, List[DIGEvent], DIGActivation]:
        with self.activate() as act:
            if started_at is not None:
                act.started_at = started_at
            act.inputs = [self.dig.record_event(event) for event in inputs]
            output = self._behavior(behavior_input)
            output = await output if inspect.isawaitable(output) else output
            act.input_reactions = self.label_input_events(act.inputs)
            act.outputs = self.output_to_events(output)
            act.native_input = native_input
            act.native_output = _native_value(output)
            if metadata:
                act.metadata = dict(metadata)
        # exiting activate() recorded `act` in place and reconciled the mailbox
        return output, act.outputs, act

    async def fire(
        self,
        events: Optional[Sequence[DIGEvent]] = None,
        *,
        started_at: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[DIGEvent], DIGActivation]:
        """Run one externally scheduled activation over DIG events."""
        inputs = list(self.mailbox.pending if events is None else events)
        inputs = [self.dig.record_event(event) for event in inputs]
        if events is not None:
            for event in inputs:
                self.mailbox.receive(event)
        behavior_input = self.events_to_input(inputs)
        _output, output_events, activation = await self._record_call(
            inputs,
            behavior_input,
            native_input=None if is_instance_sequence(behavior_input, DIGEvent) else behavior_input,
            started_at=started_at,
            metadata=metadata,
        )
        return output_events, activation

    async def __call__(
        self,
        value: Optional[Any] = None,
        *,
        started_at: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Run the wrapped behavior, record DIG as a side effect, and return native output."""
        inputs = (
            list(self.mailbox.pending)
            if value is None
            else self.input_to_events(value)
        )
        if value is not None:
            for event in inputs:
                self.mailbox.receive(event)
        uses_event_input = (
            value is None
            or (self._input_to_events is None and is_instance_sequence(value, DIGEvent))
        )
        behavior_input = self.events_to_input(inputs) if uses_event_input else value
        native_input = _native_value(behavior_input)
        output, _output_events, _activation = await self._record_call(
            inputs,
            behavior_input,
            native_input=native_input,
            started_at=started_at,
            metadata=metadata,
        )
        return output
