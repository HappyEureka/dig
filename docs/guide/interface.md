# The DIG Interface

The graph representation is imported from `dig`; the
agent-facing wrapper is imported from `dig.interface`:

- **`DIGGraph`** -- the recorder (see [The DIG graph](concept/graph.md)).
- **`DIGEvent`** -- one thing that flows between agents (see [The DIG nodes](concept/nodes.md)).
- **`DIGEvent.Reaction`** -- explicit recipient-reaction behavior annotation.
- **`DIGAgent`** -- wraps a behavior callable so that every firing, and the events it
  produces, are recorded into the graph.

You define one thing: the **behavior** (`out = behavior(in)`). The agent handles the
rest -- receive, fire, record, deliver. Start with the [minimum API](interface/minimum.md),
then use [DIGAgent](interface/agent.md) for the full wrapper API and
[DIG examples](interface/examples.md) for runnable programs.

## A minimal example

```python
import asyncio
from dig.interface import DIGAgent
from dig.graph import DIGGraph, DIGEvent

def my_llm(prompt):                                          # stand-in for your real LLM / tool call
    return "7"

dig = DIGGraph()                                             # the recorder

# `behavior` is the one thing you define
def agent_1_behavior(events):
    problem = events[-1].payload["problem"]                  # what was delivered to agent_1
    return DIGEvent(payload={"answer": my_llm(problem)}, recipients={"agent_2": DIGEvent.Reaction()})

agent_1 = DIGAgent("agent_1", agent_1_behavior, dig)                # passing `dig` registers the agent
dig.deliver(dig.record_event(DIGEvent(payload={"problem": "3+4"}, recipients={"agent_1": DIGEvent.Reaction()})))

# agent_1 fires once. `activate` runs the behavior and hands a built activation
# to `dig.record_activation` -- one activation node + its event nodes, linked.
# (No loop, no delivery -- this is the DIG-native single-fire entry point.)
output_events, activation = asyncio.run(agent_1.fire())

print(activation.id, activation.input_event_ids, "->", activation.output_event_ids)
# a1 ['e1'] -> ['e2']   -- the activation node, the problem it consumed, the result it produced
assert output_events == [dig.events["e2"]]                   # activate returns DIGEvents
assert dig.activations[activation.id] is activation          # the firing is in the graph
```

The firing is recorded as an **activation** node (`a1`) linking the problem it consumed
to the result it produced -- the graph built itself.

```{toctree}
:hidden:
:maxdepth: 2

interface/agent
interface/minimum
interface/examples
```
