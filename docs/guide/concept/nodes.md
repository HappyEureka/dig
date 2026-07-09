# The DIG nodes

The **node model** -- the two dataclasses the DIG records. The graph that holds +
records them is `DIGGraph` (see [the graph](graph.md)); the ergonomic agent wrapper
is [the interface](../interface.md).

The DIG records a run as a bipartite graph of two node dataclasses -- **events**
(`DIGEvent`) and **activations** (`DIGActivation`) -- each carrying its own data +
methods. The graph records the nodes and can deliver events through their
`recipients`; a runtime decides firing and policy.

---

## Node types -- data + their own methods

- **`DIGEvent`** holds the event's data + lifecycle methods:
  `stamp_generated` / `stamp_delivered` / `stamp_modified`.
  Each appends a timestamp record at the current wall-clock (the time is never
  caller-supplied). `DIGEvent.Label` marks the DIG-level event class
  (`COMMUNICATION` or `TOOL`). DIG does not reserve labels for domain meanings
  such as problem/result/solution/infeasible; task semantics belong to the env
  state or opaque event `payload` / `metadata`. The event records its own lifecycle,
  and since it IS the graph's node, mutating it updates the graph. Delivery is
  recorded by the recipient agent on `receive`
  (`stamp_delivered(self.agent_id)` -- it knows it is the `to`).
- **`DIGActivation`** holds its data + `identify_label()` ->
  `PROBLEM_REDUCING` / `PROBLEM_GENERATING` (computed from `#outputs` vs `#inputs`).
  DIG records that structural annotation under `metadata["dig"]["structural"]`;
  submit and failed annotations live beside it in `metadata["dig"]`.

`DIGActivation.Label` names an activation's structural class. How a recipient
treated an event is a recipient-reaction behavior
(`DIGEvent.Reaction.Label.CONSUME` / `WAIT` / `DISCARD` / `REROUTE`) reported on
`DIGActivation.input_reactions`, stamped on the event with the activation id, and
reflected on `DIGEvent.recipients[agent_id]`. A tool CALL itself is NOT an event -- it is the
activation's action (`DIGActivation.tool_calls`); what the env returns are events,
attached to that activation.

---

## `DIGEvent`

**Design.** The single event node -- one thing that flowed between agents or a tool
outcome returned by the env as pure data. A tool call is part of the producing
activation, not a `DIGEvent`. A harness builds the event id-less; the graph assigns
an `id` and stamps
`timestamps` (generated / delivered / modified) on record. Time is the event's
**own** (each stamp records the wall-clock instant it happened, never
caller-supplied) -- the event is not part of a DIG until recorded and can come
from a distributed source, so it carries its own time,
independent of the graph. The DIG knows when *it* was created and derives a
dig-relative view on demand (`DIGGraph.offset(at)`); it never sources the time.
`timestamps` is the single source of time: `generated_at`, `received_at`, and
event-reaction observations are
**derived views** over it, not stored fields, and the producing agent is derived
from `source_activation_id` (not stored). Compared by
identity, so the same object can be one activation's output and the next's input --
the graph maps it to one node. `payload` is the pure body.

**Definition.**

```python
@dataclass(eq=False)
class DIGEvent:                                    # data + its own lifecycle methods
    payload: Dict[str, Any] = {}                  # the pure body
    label: DIGEvent.Label = DIGEvent.Label.COMMUNICATION
    id: Optional[str] = None                      # assigned by the graph on record
    source_activation_id: Optional[str] = None    # producer (None = root; the agent derives from it)
    recipients: Dict[str, DIGEvent.Reaction] = {}      # recipient id -> current reaction record
    metadata: Dict[str, Any] = {}                 # optional runtime/domain annotations
    timestamps: List[DIGEvent.Timestamp] = []           # lifecycle log -- the single source of time
    delivery_policy: Optional[Dict] = {"mode": "immediate"}  # None = DIG delivery off (deliver skips it)
    # generated_at / received_at are derived @property views over `timestamps`
```

`DIGEvent.Label` is deliberately narrow:

```python
class DIGEvent.Label(str, Enum):
    COMMUNICATION = "communication"  # message/data flow between agents
    TOOL = "tool"                    # outcome produced by applying a tool call
```

---

## Event stamps

The event-side public API is method-based:

```python
event.stamp_generated()
event.stamp_delivered("agent_1")
event.stamp_modified(
    by="system",
    change="reroute",
    previous_recipient_reactions={"agent_1": {"label": "pending"}},
    recipients={
        "agent_1": {"label": "reroute", "routed_by": "a3"},
        "agent_2": {"label": "pending"},
    },
)
```

Each call appends a `DIGEvent.Timestamp` to `event.timestamps` with a `DIGEvent.Timestamp.Label`
and the current wall-clock. The method name is the stable interface, and the
timestamp record is the audit trail. `modified` stores the change details in the
stamp metadata, so recipient-changing mutations record the previous/resulting
recipient-reaction snapshots without duplicating recipient state as a top-level
timestamp field.
Recipient reaction is recorded on the activation and then stamped onto the event:
`input_reactions = {event_id: DIGEvent.Reaction(DIGEvent.Reaction.Label.CONSUME | WAIT | DISCARD)}`.

`DIGEvent.Timestamp.Label` names the lifecycle observation, not the event itself:

```python
class DIGEvent.Timestamp.Label(str, Enum):
    GENERATED = "generated"
    DELIVERED = "delivered"
    MODIFIED = "modified"
    REACTED = "reacted"
```

---

## `DIGEvent.Reaction` and `DIGEvent.Reaction.Label`

**Design.** DIG has two structural node types. `DIGEvent.Reaction` is not a
separate edge object; it is the per-recipient reaction record owned by a
`DIGEvent`. Delivery adds an event to a recipient mailbox and stamps delivery
time. Only when that recipient processes the event can DIG know whether the event
was consumed, waited on, discarded, or rerouted.

`recipients` lives on `DIGEvent`:

```python
recipients = {
    "agent_2": DIGEvent.Reaction(DIGEvent.Reaction.Label.PENDING),
    "agent_3": DIGEvent.Reaction(DIGEvent.Reaction.Label.REROUTE, routed_by="a3"),
}
```

At CREATION time the only valid reaction state is pending -- addressing
says WHO, reacting comes later -- so the constructor takes shorthands and
normalizes them to fresh PENDING entries:

```python
DIGEvent(payload={...}, recipients=["agent_2", "agent_3"])   # list of ids
DIGEvent(payload={...}, recipients="agent_2")                # a single id
```

`input_reactions` lives on `DIGActivation`:

```python
input_reactions = {
    "e1": DIGEvent.Reaction(DIGEvent.Reaction.Label.CONSUME),
    "e2": DIGEvent.Reaction(DIGEvent.Reaction.Label.WAIT),
    "e3": DIGEvent.Reaction(DIGEvent.Reaction.Label.DISCARD),
}
```

**Definition.**

```python
class DIGEvent.Reaction.Label(str, Enum):
    PENDING = "pending"    # recipient has not reacted to this event yet
    CONSUME = "consume"    # recipient used this event as input
    WAIT = "wait"          # recipient left this event in the buffer
    DISCARD = "discard"      # recipient discarded this event
    REROUTE = "reroute"    # recipient/system rerouted this event

@dataclass
class DIGEvent.Reaction:
    label: DIGEvent.Reaction.Label = DIGEvent.Reaction.Label.PENDING
    routed_by: Optional[str] = None
    metadata: Dict[str, Any] = {}
```

A `REROUTE` may be DECLARED without `routed_by`: the record funnel attributes it
with the activation id it mints, so recorded reroutes always carry provenance.
These values are one recipient-behavior vocabulary, not separate routing and
input taxonomies. When an activation records input reaction, DIG stamps the event
with the activation id and updates the matching `recipients[agent_id]` reaction
record, so the event keeps the time-ordered audit trail and the graph can render
the derived input edge. A reroute marks old recipient reaction as `REROUTE`, adds
new `PENDING` reaction records for the new recipients, and diverts the event:
undelivered copies stop going to rerouted-away recipients, and unconsumed copies
are retracted from their mailboxes.

---

## `DIGActivation`

**Design.** The single activation type -- one agent firing: the events it consumed
(`inputs`), the events it produced (`outputs`), the optional behavior-native input
(`native_input`), the optional behavior-native output (`native_output`), and a
`metadata` bag. `started_at` / `ended_at` bracket the firing (a harness may set
either; the graph stamps any left None). DIG-derived annotations live in
`metadata["dig"]`: `structural`, optional `submitting`, and optional
`failed`. The id-list views are DERIVED from
`inputs` / `outputs` / `input_reactions`, so there is one source of truth: `agent_id`
(the firing agent -- a unique key), `input_event_ids`, `output_event_ids`, and the
reaction buckets `consumed_event_ids` / `waited_event_ids` / `discarded_event_ids`.

**Definition.**

```python
@dataclass(eq=False)
class DIGActivation:                               # data + identify_label()
    agent_id: str                        # the firing agent -- a unique key
    inputs: List[DIGEvent] = []          # events consumed
    outputs: List[DIGEvent] = []         # events produced (incl. what the env returned)
    native_input: Any = None             # optional behavior/framework input
    native_output: Any = None            # optional behavior/framework output
    started_at: Optional[float] = None   # None -> stamped on record
    ended_at: Optional[float] = None     # None -> stamped on record
    metadata: Dict[str, Any] = {}        # reasoning / runtime + metadata["dig"] annotations
    input_reactions: Dict[str, DIGEvent.Reaction] = {}
    tool_calls: List[Dict[str, Any]] = [] # activation action(s), not output events
    # filled on record: id
```

`record_activation` reads `input_reactions` from the activation field
(`{event_id: DIGEvent.Reaction(DIGEvent.Reaction.Label.CONSUME | WAIT | DISCARD)}`, default all consume;
`DIGAgent.label_input_events` is the ergonomic hook). `metadata` carries runtime
annotations such as `reasoning`; DIG annotations stay under `metadata["dig"]`. A
tool call is PART OF the activation, not an output event -- the events the env returns
are the outputs.

Activation detail text puts `metadata["dig"]` near the top under the activation id,
then shows event IO and native IO. It does not recursively print whole event
payloads. It summarizes each input event by event identity/label/source/recipients
plus this activation's reaction, and each output event by event identity/label/source
and recipients. The stored `inputs` / `outputs` are still full `DIGEvent` objects
for lineage and timestamp queries; full event payloads and timestamps live on the
event nodes.

---

## `DIGActivation.Label`

**Design.** An activation's structural shape -- how it reshapes the problem --
computed by `identify_label()` from output count vs input count and recorded
as `metadata["dig"]["structural"]`. Submit and failed annotations are
orthogonal metadata entries, not additional structural types.

**Definition.**

```python
class DIGActivation.Label(str, Enum):
    PROBLEM_REDUCING   = "problem-reducing"     # outputs <= inputs -- folds work up
    PROBLEM_GENERATING = "problem-generating"   # outputs >  inputs -- expands the work
```

The graph that records these nodes -- the funnels and read views -- is
[`DIGGraph`](graph.md).
