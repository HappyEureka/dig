# dig

**DIG** is a representation for the **emergent** collaboration of LLM
agents: no predefined protocol or workflow -- the graph captures whatever
actually happens as agents interact. A run is recorded as a **Dynamic
Interaction Graph** -- a bipartite graph of agent **activations** and the
**events** between them -- so the collaboration that emerged is observable
as one graph. LLM- and environment-agnostic; depends on `matplotlib` and
`plotly`.

## The concept

A run is two kinds of node:

- **activation** -- one agent firing once: the events it consumed, the events it
  produced, its DIG annotation metadata (`structural`, optional `submitting` /
  `failed`), and its timing.
- **event** -- one thing that flowed between agents (a message, a problem, a
  result); addressed through `recipients`, pointing back to the activation
  that made it.

**How it fits together.** The **interface** (`DIGAgent`, or a runtime calling
`record_activation` directly) is how an agent's firing enters the DIG;
what gets recorded -- the graph of events + activations -- is the **concept**. A
**policy** decides (`obs` -> `act`); observers read the graph, never drive it.
Recording is DIG's source of truth. Delivery is a helper over event
`recipients`; triggering and policy are runtime concerns.

New here? Start with the [Quick start](guide/quickstart.md) -- three
short, runnable programs covering both modes (DIG delivers, or DIG
observes your framework) and the LLM plug-in seam.

## API map

Each guide page is **Design** (what it is) -> **Definition** (signature) ->
**Pseudocode**.

| Symbol | What it is | Guide |
|---|---|---|
| `DIGEvent`, `DIGActivation` | the two node dataclasses -- data + their own methods | [DIG nodes](guide/concept/nodes.md) |
| `DIGGraph` | the graph: the `record_activation` + `record_event` funnels + read views | [DIG graph](guide/concept/graph.md) |
| `DIGAgent` | wrap any agent so its activity records into a DIG | [DIG API](guide/interface.md) |
| `Healer`, `Intervention` | detect graph-shaped anomalies and repair the run in place | [Healing](guide/concept/healing.md) |

```{toctree}
:hidden:
:maxdepth: 2

Home <self>
guide/quickstart
guide/concept
guide/interface
reference
```
