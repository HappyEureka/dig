# Minimum DIG API

This is the small public surface most integrations need. Everything else is a
specialized read or renderer.

## 1. Record a firing directly

Use this when your runtime already knows one agent firing's DIG inputs and
outputs.

```python
from dig.graph import DIGActivation, DIGEvent, DIGGraph

dig = DIGGraph()
seen = DIGEvent(payload={"task": "root"})
out = DIGEvent(
    payload={"answer": "done"},
    recipients={"reviewer": DIGEvent.Reaction()},
)

act = dig.record_activation(DIGActivation(
    agent_id="worker",
    inputs=[seen],
    outputs=[out],
))
```

`record_activation` is the main funnel. It assigns activation/event ids, stamps
times, links input/output event nodes, and records how the activation reacted to its
inputs.

## 2. Wrap an agent behavior

Use this when you want DIG to own the activation lifecycle around a behavior
call.

```python
from dig.graph import DIGEvent, DIGGraph
from dig.interface import DIGAgent

dig = DIGGraph()

def worker(events):
    return DIGEvent(
        payload={"answer": "done"},
        recipients={"reviewer": DIGEvent.Reaction()},
    )

agent = DIGAgent("worker", worker, dig)
dig.deliver(dig.record_event(DIGEvent(
    payload={"task": "root"},
    recipients={"worker": DIGEvent.Reaction()},
)))

output_events, activation = await agent.fire()
```

`DIGAgent` records native timing, input events, output events, and the behavior's
return value while leaving scheduling policy to your runtime.

## 3. Adapt a framework-owned state

Use this when a framework already carries native state or messages. The framework
still receives its native return value; DIG records the event interpretation as a
side effect.

```python
agent = DIGAgent(
    "planner",
    planner_behavior,
    dig,
    input_to_events=lambda state: [
        event_for_message(msg, recipient="planner")
        for msg in state["messages"]
    ],
    output_to_events=lambda output: [
        event_for_message(msg, recipients=["worker"])
        for msg in output["messages"]
    ],
)

state_update = await agent(state)
```

This is the pattern used by LangGraph-style integrations: framework transport
carries native messages, and DIG records the same run as activation/event
structure.

## 4. Inspect, render, and save

```python
from dig import views
from dig.viz import LiveDIGRender, save_dig

dig.observe()                      # registered agents' visible runtime state
views.activation_event_graph(dig)  # derived bipartite view of the same record
live = LiveDIGRender(dig)          # live Matplotlib view; auto-updates on graph writes
save_dig(dig, "dig_artifacts")     # write dig_graph.json, dig_views.html, dig.png
```

`LiveDIGRender` subscribes to the graph's update hook (`DIGGraph.subscribe`) for
live visualization. `save_dig` writes finished-run artifacts from the current
graph: the graph JSON (with the derived edge view), one interactive HTML
presenting both views (bipartite + agent), and a PNG of the realtime
render. The graph itself answers nothing: derived views live in
`dig.views`, rendering in `dig.viz`.
