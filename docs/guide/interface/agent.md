# DIGAgent

**Design.** `DIGAgent` wraps a behavior callable and records its firings into a
DIG. The wrapper is general: the behavior can be a DIG-native callable, a
framework node, an LLM call, a tool call, or any other Python callable.

There are two boundary shapes:

```text
DIG-owned call:
mailbox/events -> events_to_input -> behavior -> output_to_events -> record

framework-owned call:
native input -> input_to_events --------------\
native input -> behavior -> native output -> output_to_events -> record
return native output
```

In the second path, DIG is only the recorder. The framework keeps its own state
shape and receives the behavior's normal return value.

## Constructor Hooks

```python
DIGAgent(
    agent_id,
    behavior,
    dig,
    *,
    input_to_events=None,     # native input -> DIGEvent(s), for framework calls
    events_to_input=None,     # DIGEvent(s) -> behavior input, for DIG-owned calls
    output_to_events=None,    # behavior output -> DIGEvent(s)
    label_input_events=None,  # DIGEvent(s) -> DIGEvent.Reaction values
    trigger=None,             # autonomous run-loop firing predicate
)
```

- `input_to_events` is for framework-owned execution. It lets DIG observe a
  framework-native state/input without requiring the framework to carry
  `DIGEvent`s.
- `events_to_input` is for DIG-owned execution. It converts mailbox/input events
  into whatever the behavior expects.
- `output_to_events` turns the behavior's native output into the DIG events that
  should be recorded as activation outputs.
- `label_input_events` reports how this activation reacted to each input event.
  The default is `DIGEvent.Reaction.Label.CONSUME`.
- `trigger` controls only the autonomous `run()` loop. Direct calls and
  framework schedulers decide their own firing order.

`DIGAgentEntity` owns persistent agent identity, the mailbox, registration,
receive-and-wake on delivery, the wake/wait primitive, visible state, and the
firing lifecycle. `activate()` is one firing: entering marks the entity
active and yields the firing itself -- a `DIGActivation` prefilled with the
agent id, the span start, and the pending buffer as inputs; the runtime
fills in what the firing produced; a clean exit records that same node into
the DIG (`dig.record_activation` completes it in place -- id assigned,
events interned) and reconciles the mailbox. Recording is part of the
lifecycle, never a separate step to remember, and there is no draft-vs-node
split: one firing is one `DIGActivation` from start to record. An exception
inside the block records the firing as FAILED (`metadata["dig"]["failed"]`)
and re-raises -- the attempt stays observable, but it produces nothing,
declares no reactions, and leaves the mailbox uncommitted, so its inputs
stay pending for a retry.
The entity does not decide WHEN to fire -- that is the runtime's call. Every
runtime builds on the entity rather than redoing this machinery: `DIGAgent`
adds the callable behavior surface plus the optional autonomous `run()` loop,
and an async runtime can add its own env side on the same machinery.
Observation-shaping is not the entity's job: a policy's `obs()` owns what its
agent perceives, and `dig.observe()` aggregates each agent's `visible_state()`
for team-level monitoring.

## Entry Points

- `await agent()` fires once from the current mailbox, records the activation,
  and returns the behavior's native output.
- `await agent(native_input)` fires once from framework/native input, records the
  activation using `input_to_events` and `output_to_events`, and returns the
  behavior's native output unchanged.
- `await agent.fire(events=None)` is the DIG-native fire. It consumes mailbox
  events, or the explicit `events`, and returns `(output_events, activation)`.
  Use this when the caller needs the produced DIG events for `dig.deliver(...)`.
- `await agent.run(stop)` is the `DIGAgent` autonomous mailbox loop. It repeatedly calls
  `activate()` and DIG-delivers the produced events.

`DIGAgent` stores behavior-native IO on the recorded activation when it is distinct
from DIG events: `native_input` is the value passed to the wrapped behavior, and
`native_output` is the behavior's normal return value. If either side is already a
`DIGEvent` or a sequence of `DIGEvent`s, the event nodes are the representation and
the corresponding native field is left empty.

## Input Reaction Labels

`label_input_events` is how an agent marks what happened to each incoming event.
Return `{event_id: DIGEvent.Reaction(...)}` or a same-length sequence of
`DIGEvent.Reaction` values.

```python
def label_inputs(events):
    return {
        event.id: DIGEvent.Reaction(
            DIGEvent.Reaction.Label.WAIT
            if event.metadata.get("reference_only")
            else DIGEvent.Reaction.Label.CONSUME
        )
        for event in events
    }
```

These records drive event -> activation edge style and the
`consumed_event_ids` / `waited_event_ids` / `discarded_event_ids` views.

[DIG examples](examples.md) shows the hooks in runnable settings. The LangGraph
example passes `DIGAgent` directly as a framework node: LangGraph carries normal
message state, while `input_to_events` and `output_to_events` project that state
into DIG for recording.
