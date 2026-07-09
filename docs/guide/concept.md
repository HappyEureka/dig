# The DIG concept

A run is recorded as a **bipartite graph of two node dataclasses** -- events
(`DIGEvent`) and activations (`DIGActivation`) -- held by a graph (`DIGGraph`).
Observers then **read** that graph. Delivery is a helper over
event `recipients`; triggering, policy, and env stepping are runtime-owned.

Three pages:

| Page | Covers |
|---|---|
| [The DIG nodes](concept/nodes.md) | `DIGEvent`, `DIGActivation`, and activation/input/event-stamp semantics |
| [The DIG graph](concept/graph.md) | `DIGGraph` -- the `record_activation` / `record_event` funnels + read views |
| [Healing](concept/healing.md) | `Healer` + `Intervention` -- detect graph-shaped anomalies, repair mid-run |

```{toctree}
:hidden:
:maxdepth: 2

concept/nodes
concept/graph
concept/healing
```
