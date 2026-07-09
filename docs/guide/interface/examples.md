# DIG examples

Programs that use the [DIG API](../interface.md). Each is shown in the two delivery
modes, because that is the choice every integration makes:

- **DIG delivers** (the default) -- an event's `delivery_policy` is
  `{"mode": "immediate"}`, so `dig.deliver(event)` routes it through
  `recipients`.
- **DIG delivery off** -- DIG only RECORDS the firing; something else carries the
  message. That happens when nobody calls `dig.deliver` (a framework owns transport), or
  when an event's `delivery_policy` is `None` so `dig.deliver` skips it. The recorded
  graph is the same shape either way -- only who delivers differs.

## Instantiating a DIGAgent

The constructor is the same everywhere -- the behavior callable plus optional hooks.
What varies per setting is which hooks you pass and which drive method you call:

```python
DIGGraph()  # attach LiveDIGRender(dig) for a live view that updates on graph writes

DIGAgent(agent_id, behavior, dig, *,
         input_to_events=None,   # adapter: native framework input -> DIGEvent(s)
         events_to_input=None,    # adapter: DIGEvents -> the behavior's input
         output_to_events=None,   # adapter: the behavior's output -> DIGEvent(s)
         label_input_events=None, # adapter: DIGEvents -> DIGEvent.Reaction values
         trigger=None)            # when to fire (default: the mailbox holds a fresh delivery)
```

| Setting | Instantiation | Drive | Who carries messages |
|---|---|---|---|
| **DIG delivers** (default) | `DIGAgent(id, behavior, dig)` | `run` (autonomous) or `await agent.fire()` (you order the firings) | DIG -- `dig.deliver` routes each produced event through its `recipients` |
| **A framework delivers** (LangGraph, ...) | `DIGAgent(id, behavior, dig, input_to_events=..., output_to_events=...)` | pass `agent` directly as the framework node | the framework carries native state/messages; `DIGAgent` records receipt/timing/lineage as a side effect |

The two changes are independent:

- **Delivery is a run-time choice, not a constructor one.** DIG delivers when you call
  `dig.deliver` (which `run` does for you); a framework delivers when it owns transport
  and nobody calls `dig.deliver`. To skip DIG delivery for a *specific* event while still
  using `dig.deliver` / `run`, set its `delivery_policy=None` (e.g. via an
  `output_to_events` that stamps it) -- `dig.deliver` then passes it over.
- **The adapters are the instantiation change.** Pass `input_to_events` /
  `output_to_events` when wrapping a framework whose native input/output is not
  `DIGEvent`s. The framework still sees its own state and return values; DIG sees
  the projected event flow. Pass `events_to_input` when DIG-owned events need to be
  converted before calling the behavior.

The third override, `trigger`, sets WHEN an agent fires in the autonomous `run` loop
(default: a fresh, unprocessed delivery; pass a predicate, e.g. one that waits until two
results have arrived). The controlled and framework paths fire agents themselves, so
they leave it default.

`label_input_events` is optional but important when an agent does not consume every
input it sees. Return `{event_id: DIGEvent.Reaction(...)}` with a `DIGEvent.Reaction.Label` such as
`CONSUME`, `WAIT`, `DISCARD`, or `REROUTE`. The default is consume for all
inputs. Those reports become event -> recipient reaction behavior in the DIG.

```python
from dig.interface import DIGAgent
from dig.graph import DIGEvent

def label_inputs(events):
    return {
        event.id: DIGEvent.Reaction(
            DIGEvent.Reaction.Label.WAIT
            if event.metadata.get("reference_only")
            else DIGEvent.Reaction.Label.CONSUME
        )
        for event in events
    }

reviewer = DIGAgent("reviewer", review, dig, label_input_events=label_inputs)
```

The examples below fill in each row.

## Inspecting the DIG

Each runnable example can show the DIG live as the run records each activation,
then save the finished graph:

```bash
python examples/hello_dig.py --viz              # live window + save dig_artifacts/ folder
python examples/hello_dig.py --viz out          # live window + save out/ artifact folder
python examples/hello_dig.py --realtime-viz     # live window only
```

The live path attaches a `LiveDIGRender` to the graph's update hook, so graph
writes and delivery updates push the current state into the live Matplotlib
window. Finished-run artifacts are written from the current graph with
`save_dig(dig, ...)`:

```python
from dig.viz import LiveDIGRender, save_dig

dig = DIGGraph()
live = LiveDIGRender(dig)   # subscribes to dig; updates on every graph write
save_dig(dig, "dig_artifacts")   # write dig_graph.json, dig_views.html, dig.png
```

`LiveDIGRender` only updates the live window; `save_dig(...)` bulk-overwrites
the finished-run graph data and visual artifacts: the graph JSON (with the
derived edge view), one interactive Plotly HTML presenting both views, and
a PNG of the realtime render. The HTML's bipartite section shows every
activation and event over the agent lanes (Full and Clean panels plus the
activation spans); its agent section shows one node per agent, with
directed arcs bundling every event that flowed between a pair of agents,
grouped by reaction kind; hover shows a compact per-edge label with the
bundled counts.
`LiveDIGRender` disables the live window path automatically under
non-interactive/headless backends.

## A two-agent walk-through

Two agents passing one message -- the smallest end-to-end loop.

### With DIG delivery (the default)

Each agent's `run` fires on its mailbox and DELIVERS what it produced (the events carry
the default `immediate` policy). The driver just launches the loops + a quiescence
watchdog. This is the minimal API pattern behind DIG-owned delivery; the runnable
`hello_dig.py` example below uses the same delivery semantics in a richer
planner / worker / verifier loop.

```python
import asyncio
from dig.interface import DIGAgent
from dig.graph import DIGGraph, DIGEvent

dig = DIGGraph()
agent_1 = DIGAgent(
    "agent_1",
    lambda evs: DIGEvent(payload={"text": "hello"}, recipients={"agent_2": DIGEvent.Reaction()}),
    dig,
)
agent_2   = DIGAgent("agent_2",   lambda evs: None, dig)                  # terminal: consumes, emits nothing

dig.deliver(dig.record_event(DIGEvent(payload={"text": "start"}, recipients={"agent_1": DIGEvent.Reaction()})))   # root -> agent_1

async def main():
    stop = asyncio.Event()
    tasks = [asyncio.create_task(a.run(stop)) for a in (agent_1, agent_2)]   # each agent: its own loop
    while any(a.active or a.mailbox.pending for a in (agent_1, agent_2)):     # quiescence watchdog
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.gather(*tasks)

asyncio.run(main())
print(dig.observe())              # the graph built itself; observe the team
```

### Without DIG delivery

The instantiation is unchanged -- the difference is purely at run time: nobody calls
`dig.deliver`, so DIG records each firing but routes nothing; you (or a framework) carry
transport. Same two agents, external hand-off:

```python
dig = DIGGraph()
agent_1 = DIGAgent("agent_1", lambda evs: DIGEvent(payload={"text": "hello"}, recipients={"agent_2": DIGEvent.Reaction()}), dig)
agent_2   = DIGAgent("agent_2",   lambda evs: None, dig)
agent_1.receive(dig.record_event(DIGEvent(payload={"text": "start"}, recipients={"agent_1": DIGEvent.Reaction()})))  # root -- no dig.deliver

output_events, activation = await agent_1.fire()   # agent_1 fires + records; DIG transports nothing
for event in output_events:                      # YOU carry transport (here, into agent_2's mailbox)
    agent_2.receive(event)
```

DIG still records the full graph (the activation, the message, the lineage) -- it just
does not do the delivery. This is the seam every external integration uses: a framework's
state or transport carries native messages, while `agent(state)` or
`DIGAgent.fire(...)` records each firing.

## A planner / worker / verifier flow

A small agentic flow: a planner sends a message, a worker responds, and a verifier
emits a terminal message. The ORCHESTRATOR owns the order, so it fires each agent
once with `await agent.fire()` rather than the autonomous `run`.

### With DIG delivery

`examples/hello_dig.py` is the runnable version. The orchestrator fires an agent, then
delivers what it produced through DIG:

```python
async def step(dig, agent):                      # fire one agent, then DIG-deliver its output
    produced, _ = await agent.fire()           # direct DIG fire returns events + activation
    for e in produced:
        dig.deliver(e)                            # default policy -> DIG routes through recipients
    return produced[0]

# one pass: planner -> worker -> verifier
plan    = await step(dig, planner)
result  = await step(dig, worker)
verdict = await step(dig, verifier)
```

### With LangGraph delivery

`examples/hello_dig_langgraph.py` builds the three roles as a plain LangGraph-style
program first: planner / worker / verifier consume and return normal LangGraph
state updates, with no DIG imports. The DIG part is the adapter layer:

```python
from dig.interface import DIGAgent
from dig.graph import DIGEvent

message_events = {}

def event_for_message(message, *, recipients=()):
    message_id = message["id"]
    if message_id not in message_events:
        message_events[message_id] = DIGEvent(
            payload=dict(message.get("payload", {})),
            recipients={recipient: DIGEvent.Reaction() for recipient in recipients},
            metadata={"message_id": message_id},
            delivery_policy=None,       # LangGraph does the delivery
        )
    else:
        for recipient in recipients:
            message_events[message_id].recipients.setdefault(recipient, DIGEvent.Reaction())
    return message_events[message_id]

def input_to_events(state, *, recipient):
    return [
        event_for_message(message, recipients=[recipient])
        for message in state.get("messages", [])
    ]

def output_to_events(output, *, recipients):
    return [
        event_for_message(message, recipients=recipients)
        for message in output.get("messages", [])
    ]

planner = DIGAgent("planner", PlainPlanner(), dig,
                   input_to_events=lambda state: input_to_events(state, recipient="planner"),
                   output_to_events=lambda output: output_to_events(output, recipients=["worker"]))
worker = DIGAgent("worker", PlainWorker(...), dig,
                  input_to_events=lambda state: input_to_events(state, recipient="worker"),
                  output_to_events=lambda output: output_to_events(output, recipients=["verifier"]))

graph.add_node("planner", planner)              # framework state -> framework state update
graph.add_node("worker", worker)
```

LangGraph's `StateGraph` carries the messages between nodes and its edges drive the
plan -> work -> verify loop; DIG only records. `agent(state)` returns the plain
LangGraph state update. The same pattern fits any framework that owns delivery --
OpenAI Agents SDK, MetaGPT, a message broker -- not just LangGraph.

The recorded DIG is the **same shape** in both examples -- only who carried the
messages between the agents differs.

### The n-agent domains: constraints, reactions, lineage

Two self-contained domains exercise DIG delivery at any team size (both
take `--agents N`):

```bash
python examples/count_frequency_domain.py --agents 5
python examples/research_domain.py --agents 4
```

- `count_frequency_domain.py` -- a coordinator splits a counting problem into
  per-worker chunks (a `CapacityConstraint` must HOLD for every
  assignment), N workers count in parallel, and an aggregator WAITS until
  every partial has arrived before consuming them all in one submitting
  firing.
- `research_domain.py` -- ordered stages
  gated by a `DependencyConstraint`; the stage work fans out to N agents,
  one overloaded agent REROUTES an item to a peer, and a reviewer combines
  each stage into the digest that unlocks the next.

Both check themselves through the lineage views (`views.root_events`,
`views.lineage_covers_root_events`, `views.any_coverage_complete`) and end
with PASS.
