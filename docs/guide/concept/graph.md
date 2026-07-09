# The DIG graph

`DIGGraph` is the graph that records the [node model](nodes.md) and exposes read
views over it. Recording is its source of truth; `deliver` is a helper that
releases recorded events through their `recipients`. DIG never triggers
agents or runs a policy. Callers hand it built nodes through two symmetric funnels,
`record_activation` and `record_event`; the per-agent buffer is the agent's own
(see [the interface](../interface.md)), and `DIGGraph` only observes the team.

---

## `DIGGraph.record_activation`

**Design.** The single funnel from a `DIGActivation` to graph nodes + edges.
It records only; callers decide whether to route the returned output events with
`deliver` or through an external framework.

**Definition.** `record_activation(activation: DIGActivation) -> DIGActivation`.
Returns the recorded activation; its `output_event_ids` are the materialized outputs
in order.

**Pseudocode.**

```text
record_activation(activation):
    aid     = next_activation_id()                       # mint up front so outputs link to it
    inputs  = [record_event(e) for e in activation.inputs]
    if activation.failed:                                # a FAILED firing records the attempt only:
        outputs, input_reactions = [], {}                # nothing produced, no reactions declared
    else:
        outputs = [record_event(e.with(source=aid) if e is newly minted
                                else e)                  # a recorded event keeps its producer
                   for e in activation.outputs]
        input_reactions = activation.input_reactions or {each input: DIGEvent.Reaction(DIGEvent.Reaction.Label.CONSUME)}
    return write_activation(aid, activation.agent_id,
                            inputs        = inputs,
                            outputs       = outputs,
                            native_input  = activation.native_input,
                            native_output = activation.native_output,
                            started_at    = activation.started_at or now(),
                            ended_at      = activation.ended_at or now(),
                            metadata      = activation.metadata with metadata["dig"],
                            tool_calls    = activation.tool_calls,
                            input_reactions     = input_reactions)
```

`DIGAgent` is the agent-side lifecycle wrapper: it reads the agent's own state
(mailbox or externally supplied DIGEvents), maps behavior output into `DIGEvent`s,
records input reaction (`DIGEvent.Reaction.Label.CONSUME` / `WAIT` / `DISCARD`),
builds a `DIGActivation`, and calls `record_activation`. Those reaction records are
the recipient's later interpretation of the delivered event, and the graph reflects
them on the event's `recipients`. The graph never reaches into the agent -- the agent
hands it a node.

### Editing activation metadata

Use `update_activation_metadata(activation_id, updates)` to attach later runtime
context to a recorded activation. The method deep-merges into the activation's real
`metadata` field, preserves DIG's own `metadata["dig"]` annotations unless you
explicitly update them, and notifies subscribers (live renderers attach via `subscribe`). Renderers print that stored
metadata directly.

```python
act = dig.record_activation(DIGActivation(agent_id="planner"))
dig.update_activation_metadata(act.id, {"reasoning": "prefer merge path"})
```

---

## `DIGGraph.record_event`

**Design.** Wire a caller-built `DIGEvent` into the log -- the event-side
counterpart of `record_activation`. Assigns an id, stamps `generated`, adds the
node, and -- if the event names a SOURCE activation that is already recorded --
forward-links it onto that activation's outputs (so lineage walks see it). That
forward-link is how a LATE event attaches (the env's reaction to a tool call, a
system-side injection); a standalone event (a root) has no source and just records.
Idempotent by id: an event already in the log returns its canonical node, not
re-linked.

**Definition.** `record_event(event: DIGEvent) -> DIGEvent`.

**Pseudocode.**

```text
record_event(event):
    if event.id already in the log:  return that node       # idempotent, no re-link
    assign an id, stamp generated, add the node
    act = activations.get(event.source_activation_id)
    if act:  act.outputs.append(event)                      # forward-link a LATE event
    return event
```

(An output produced DURING a firing has a source that is not yet recorded when it is
wired, so it is not linked here -- `record_activation` links it via the activation
node's `outputs`.)

---

## `DIGGraph.deliver`

**Design.** Release one event -- or a list of them -- through its `recipients`;
the address and route interpretation are already on each event, so delivery
takes no separate target. Each event's `delivery_policy` decides what happens: `None`
skips it (DIG delivery OFF -- an external framework carries the event and DIG only
records); `{"mode": "immediate"}` (the default) hands it to each registered recipient
right away for each recipient not yet delivered to (derived from the
`DELIVERED` stamps -- reaction never encodes delivery STATE; routing INTENT
does read the current reaction, so a recipient whose entry is `REROUTE` is
skipped -- rerouted away), and each recipient
stamps its own arrival (`receive`). Other modes raise
`NotImplementedError` by design. Conditional release policies are an intentional
future seam, not current partial behavior.

**Definition.** `deliver(events: DIGEvent | list[DIGEvent]) -> None` -- one event or a list.

---

## `DIGGraph.reroute_event`

**Design.** Reroute a recorded event in place and DIVERT it: flip the
rerouted-away recipients' reaction to `REROUTE` (attributing it to activation
`by`), retract their unconsumed buffered copies, add `to` as fresh `PENDING`
recipients, stamp the change, and deliver the new recipients (a rerouted-back
recipient gets a fresh copy). A recipient whose entry is `REROUTE` is skipped
by `deliver` -- rerouting redirects outstanding work; it does not rewrite
history (the default flip skips recipients who already consumed or
discarded) -- while naming a recipient in `to` declares NEW outstanding
work for them, fresh copy included, even if they reacted before (the
append-only stamps keep that history). `from_recipients=None` flips the
LIVE recipients (still PENDING or
WAIT -- the system-side use); passing `[agent_id]` flips only that agent's own
reaction (an agent self-rerouting); `[]` is transport only (the flip was
declared with the firing). Recipients in `from_recipients` not on the event
are skipped.

`to=[]` is a CANCELLATION: withdraw the event from every live recipient
(copies retracted, no successor named) -- the model needs no separate
cancel primitive.

**Definition.** `reroute_event(event: DIGEvent, *, to: list[str], by: str,
from_recipients: list[str] | None = None) -> DIGEvent`. Returns `event`.

**Pseudocode.**

```text
reroute_event(event, to, by, from_recipients):
    previous = event.recipient_reactions_snapshot()          # before image
    flipping = live recipients (PENDING/WAIT) if from_recipients is None
               else from_recipients
    for r in flipping:                                       # skip ones not on the event
        event.recipients[r] -> REROUTE, routed_by = by
        r's mailbox retracts its unconsumed copy              # divert
    for r in to:  event.recipients[r] = DIGEvent.Reaction()  # fresh PENDING
    event.stamp_modified(by=by, change="reroute",
                         previous_recipient_reactions=previous,
                         recipients=event.recipient_reactions_snapshot())
    if event.delivery_policy is not None:                    # framework-carried events:
        receive + deliver(event)                             # rewrite only, no DIG transport
    return event
```

---

## `DIGGraph.observe`

**Design.** The team's state at a glance -- `DIGGraph` as a special "communication
env" that manages the events flowing among agents and can observe them. Each
registered agent exposes `visible_state()`; the graph aggregates those summaries
instead of reconstructing agent-local runtime state itself.

**Definition.** `observe() -> {agent_id: {"active": bool, "mailbox": int,
"pending_event_ids": list[str], ...}}`. Agents register via `register(agent)` (a
`DIGAgent` does so on construction).
