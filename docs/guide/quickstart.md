# Quick start

Two modes: DIG can deliver the events itself (1), or observe another
framework's run (3). Either way, your model plugs in as the policy (2).
Every snippet on this page is runnable as written.

## 1. Observe and deliver: DIG is the framework

An agent is its policy -- any callable from DIG events to DIG events.
`DIGAgent` wraps it; `fire()` runs one activation over the mailbox and
records it; delivering the produced events is your call.

```python
import asyncio

from dig import DIGEvent, DIGGraph
from dig.interface import DIGAgent

graph = DIGGraph()

async def policy_1(events):
    problem = events[0].payload["problem"]
    await asyncio.sleep(1)          # simulate LLM response time
    return DIGEvent(payload={"answer": 7}, recipients=["agent_2", "agent_3"])

async def policy_2(events):
    answer = events[0].payload["answer"]
    if answer == 7:
        return DIGEvent(payload={"verdict": "correct"}, recipients=["agent_1"])
    return DIGEvent(payload={"verdict": "wrong"}, recipients=["agent_1"])

agent_1 = DIGAgent("agent_1", policy_1, graph)
agent_2 = DIGAgent("agent_2", policy_2, graph)
agent_3 = DIGAgent("agent_3", policy_2, graph)

root = DIGEvent(payload={"problem": "3+4"}, recipients=["agent_1"])
graph.record_event(root)
graph.deliver(root)

produced, activation = asyncio.run(agent_1.fire())
graph.deliver(produced)          # one deliver fans out to both verifiers

# the verifiers are independent agents: they run concurrently
async def verify():
    return await asyncio.gather(agent_2.fire(), agent_3.fire())
(produced_2, _), (produced_3, _) = asyncio.run(verify())
graph.deliver(produced_2 + produced_3)   # verdicts return to agent_1
```

Things this run just demonstrated:

- **Recipients are addressing.** `recipients=["agent_2", "agent_3"]` says
  WHO; a fresh pending reaction per recipient is implied. The recipient's
  relationship to the event updates when it fires (consume by default;
  wait / discard / reroute by declaration).
- **One deliver fans out.** A single `graph.deliver(produced)` routes the
  event into every recipient's mailbox.
- **Concurrency is real.** The two verifiers awaited 1 second each and
  finished in ~1 second total; each activation's recorded span carries
  its latency.
- **Every firing is recorded** -- including the verifiers' and the final
  fan-in of verdicts back to agent_1.

## 2. Plug in a real LLM

The policy is just a callable, so a real model drops in directly. An
event's payload can hold anything -- any schema, any datatype; DIG never
looks inside. Here the decision schema carries the answer AND the
routing, and the model fills it:

```python
from pydantic import BaseModel

class Decision(BaseModel):
    answer: str             # the model's answer to the problem
    recipients: list[str]   # who should receive it next, e.g. ["agent_2"]
```

The policy does three things: convert the mailbox events into a prompt,
call the model, and wrap the response back into a DIG event:

```python
def llm_policy(events):
    messages = [{"role": "user", "content": str(event.payload)} for event in events]
    response = llm_client(messages=messages, output_format=Decision)   # <- your model
    return DIGEvent(payload={"answer": response.answer},
                    recipients=response.recipients)

llm_agent = DIGAgent("agent_1", llm_policy, graph)
```

Those two conversions are exactly what the `events_to_input` /
`output_to_events` adapters are for. Factored through them, the policy
speaks only your model's native types -- messages in, `Decision` out --
and the `Decision` is also kept on the activation as its native output:

```python
def to_messages(events):
    return [{"role": "user", "content": str(event.payload)} for event in events]

def to_events(response):
    return [DIGEvent(payload={"answer": response.answer},
                     recipients=response.recipients)]

def llm_policy(messages):
    return llm_client(messages=messages, output_format=Decision)   # <- your model

llm_agent = DIGAgent("agent_1", llm_policy, graph,
                     events_to_input=to_messages,
                     output_to_events=to_events)
```

The model decides the answer *and* who gets it (`recipients` comes back
from the schema and feeds DIG delivery directly). Swap the model call for
any provider or framework -- the policy seam is the whole integration
surface. The full wrapper API (triggers, input labeling, async behaviors)
is in [DIGAgent](interface/agent.md).

## 3. Observe only: DIG observes your framework

`graph.deliver` is a choice, not a requirement. Wrap a plain framework
node -- here LangGraph -- and never call deliver: the framework delivers
every message, and DIG still observes the run.

```python
from langgraph.graph import START, END, StateGraph

def plan(state):        # a plain LangGraph node: framework state in / out
    return {"messages": [...]}

planner = DIGAgent("planner", plan, graph,
                   input_to_events=...,      # framework state -> DIGEvents
                   output_to_events=...)     # state update    -> DIGEvents

flow = StateGraph(FlowState)
flow.add_node("planner", planner)            # the wrapped agent IS the node
flow.add_edge(START, "planner")
# ...more nodes, then:
app = flow.compile()
asyncio.run(app.ainvoke({"messages": [seed]}))

# no dig.deliver anywhere: LangGraph does the delivery, DIG observes --
# activations, events, and lineage are all recorded
print(len(graph.activations), len(graph.events))
```

The runnable version is `examples/hello_dig_langgraph.py`; the recorded
graph has the same shape either way -- only who delivers differs. The
same pattern fits any framework that owns delivery; see
[DIG examples](interface/examples.md) for the full adapter code.

## See it

Every example supports `--viz` -- a realtime window where the graph grows
as the run records. `save_dig(graph, "dig_artifacts")` writes the
finished run: the graph JSON, one interactive HTML presenting both views
(bipartite + agent), and a PNG.
