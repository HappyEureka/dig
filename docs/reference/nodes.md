# Reference: the DIG nodes

The two node dataclasses the graph records -- the interface as the interpreter
sees it. See the [DIG nodes guide](../guide/concept/nodes.md) for the design
rationale and pseudocode.

`DIGEvent` and `DIGActivation` are plain dataclasses: each carries its own data
and its own methods, and its own time independent of any graph. DIG events do not
have a first-class domain content type. Domain/task meaning belongs to env
state or opaque `payload` / `metadata`. `DIGEvent.Label` names the narrow
DIG-level event class (`communication` or `tool`), while `DIGActivation.Label`
names activation structural labels.
How a recipient treated an event is stored as a `DIGEvent.Reaction` record in
`DIGActivation.input_reactions`, reflected on `DIGEvent.recipients`, and rendered
through the derived graph edge (`DIGEvent.Reaction.Label.CONSUME` / `WAIT` /
`DISCARD` / `REROUTE`). The three stores have distinct roles -- the activation's
`input_reactions` is the declaration, the event's REACTED timestamps are the log,
and `recipients` is the current-state view -- but declaration and current state
are ONE object, never a copy: `DIGEvent.apply_reaction` (the single write path)
stores the declared record itself as the recipient's entry, and routing rewrites
replace entries rather than mutate through them, so a past activation's
declaration is never edited.
Lifecycle stamps are recorded as `DIGEvent.Timestamp` objects through the explicit
`stamp_generated` / `stamp_delivered` / `stamp_modified` methods. A stamp records the wall-clock instant
it happened -- the time is never caller-supplied (this is an observation framework).
Delivery is recorded by the recipient agent on `receive` (it supplies its own id
as the `to`).

```{eval-rst}
.. autoclass:: dig.DIGEvent
   :members:
.. autoclass:: dig.DIGActivation
   :members:
```
