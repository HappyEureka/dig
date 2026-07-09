# dig

**DIG -- Dynamic Interaction Graph**: a representation built to capture
the **emergent** collaboration of LLM agents.

Project page: [happyeureka.github.io/dig](https://happyeureka.github.io/dig/)

Emergent means nothing is predefined: no protocol, no workflow, no role
structure. DIG records whatever actually happens as agents interact.

The graph has two node types. An **event** is one thing that flowed
between agents. An **activation** is one span of an agent acting: input
events in, output events out. An agent may activate many times, at
different times, and DIG also captures how it reacts to each input event
(consume / wait / discard / reroute). LLM-agnostic,
environment-agnostic, and working with any number of agents, DIG is
designed to monitor whatever happens among agents at run time.

DIG monitors emergent collaboration structurally, so it works well with
any builder framework, like LangGraph. DIG can also be the framework: it
provides an optional delivery function that sends messages to the other
agents.

**Part 1** below: use DIG as a monitoring system. **Part 2**: the
[DIG to Heal](https://arxiv.org/abs/2603.00309) paper and its experiment
domains.

## Part 1 -- Use DIG as a monitoring system

### Install

Use Python 3.10 or newer, with whatever environment manager you like: the
script installs the package editable into the ACTIVE environment and
builds the docs.

```bash
conda create -n dig python=3.10
conda activate dig
./scripts/install.sh
```

Then run a first graph right away -- a three-agent run, recorded live:

```bash
python examples/hello_dig.py --viz
```

Docs are available through:

```bash
open docs/_build/html/index.html
```

### Quick start

Two modes: DIG can deliver the events itself (1), or observe another
framework's run (3). Either way, your model plugs in as the policy (2).

#### 1. Observe and deliver: DIG is the framework

```python
import asyncio

from dig import DIGEvent, DIGGraph
from dig.interface import DIGAgent

graph = DIGGraph()

# an agent = its policy, any callable: DIG events in -> DIG events out
async def policy_1(events):
    problem = events[0].payload["problem"]
    await asyncio.sleep(1)          # simulate LLM response time
    return DIGEvent(payload={"answer": 7}, recipients=["agent_2", "agent_3"])

async def policy_2(events):
    answer = events[0].payload["answer"]
    await asyncio.sleep(1)          # simulate LLM response time
    if answer == 7:
        return DIGEvent(payload={"verdict": "correct"}, recipients=["agent_1"])
    return DIGEvent(payload={"verdict": "wrong"}, recipients=["agent_1"])

agent_1 = DIGAgent("agent_1", policy_1, graph)
agent_2 = DIGAgent("agent_2", policy_2, graph)
agent_3 = DIGAgent("agent_3", policy_2, graph)

root = DIGEvent(payload={"problem": "3+4"}, recipients=["agent_1"])
graph.record_event(root)
graph.deliver(root)

# fire() records the activation; delivering its outputs is your call
produced, activation = asyncio.run(agent_1.fire())
graph.deliver(produced)          # one deliver fans out to both verifiers

# the verifiers are independent agents, so they run concurrently:
# two 1-second policies, ~1 second total
async def verify():
    return await asyncio.gather(agent_2.fire(), agent_3.fire())
(produced_2, _), (produced_3, _) = asyncio.run(verify())
graph.deliver(produced_2 + produced_3)   # verdicts return to agent_1
```

#### 2. Plug in a real LLM

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
surface.

#### 3. Observe only: DIG observes your framework

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
graph has the same shape either way -- only who delivers differs.

### Examples

```bash
python examples/hello_dig.py --viz             # three agents, DIG-owned delivery
python examples/hello_dig_langgraph.py --viz   # framework-owned transport; DIG records
```

`--viz` (supported by every example) opens a realtime window where the
graph grows as the run records; `hello_dig` also saves the finished graph
as JSON, an interactive agent-graph HTML, and a PNG.

Design guides and the API reference are the Sphinx site under `docs/`.

## Part 2 -- The paper: DIG to Heal

This is the codebase for [DIG to Heal: Scaling General-purpose Agent
Collaboration via Explainable Dynamic Decision Paths](https://arxiv.org/abs/2603.00309).

The paper takes the representation one step further: once the
collaboration is captured as a graph, errors show up as graph shapes --
and graph-shaped errors can be detected and corrected mid-run, while the
agents are still working. The healing layer (`dig.heal`) is that
correction side: detectors propose interventions from graph shape alone,
and every applied intervention is recorded back into the graph.

### The experiment domains

The paper's experiments run n-agent teams in two self-contained domains,
shipped here as runnable examples. Each defines small constraint classes
that must hold (worker capacity in both; stage dependencies in the
research domain), splits the work across `--agents N` agents through DIG
delivery, and checks itself with the lineage views before printing PASS.

```bash
python examples/count_frequency_domain.py --agents 5
python examples/research_domain.py --agents 4
```

- `count_frequency_domain` -- a coordinator splits a character-counting
  problem into per-worker chunks (each within the worker's capacity), N
  workers count in parallel, and an aggregator WAITS until every partial
  has arrived before combining and submitting.
- `research_domain` -- ordered stages gated by a dependency constraint;
  the stage work fans out to N agents (every firing within capacity),
  one overloaded agent REROUTES an item to a peer with spare capacity,
  and a reviewer combines each stage into the digest that unlocks the
  next.

But DIG works with ANY domain: nothing in the substrate knows these two
exist.

### Citation

If you use DIG in your research, please cite:

```bibtex
@article{yang2026dig,
  title={DIG to Heal: Scaling General-purpose Agent Collaboration via Explainable Dynamic Decision Paths},
  author={Yang, Hanqing and Lee, Hyungwoo and Yao, Yuhang and Liu, Zhiwei and Liu, Kay and Chen, Jingdi and Joe-Wong, Carlee},
  journal={arXiv preprint arXiv:2603.00309},
  year={2026}
}
```
