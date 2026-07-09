# Reference: the DIG graph

`DIGGraph` -- the graph that records the nodes and exposes read views over them.
See the [DIG graph guide](../guide/concept/graph.md) for the design rationale and
pseudocode.

It records nodes through the two symmetric funnels -- an activation via
`record_activation` (which completes the given `DIGActivation` in place: the
node you pass in IS the recorded node), an event via `record_event` (which also
forward-links a late event onto its already-recorded source activation) --
delivers events to registered agents (each agent stamps its own arrival), and
exposes the representation reads (`observe`, `offset`, `to_dict`) plus the
`subscribe` update hook that live renderers attach to. The graph answers
nothing beyond its own state: derived views -- the bipartite edge list and the
lineage/coverage queries -- are questions you ask OF the graph and live in
[`dig.views`](views.md).
Recording is DIG's source of truth; delivery is a transport helper over recorded
events. `update_activation_metadata` edits a recorded activation's metadata in
place and notifies subscribers. A `DIGAgent` builds its activation from its own
lifecycle, then calls `record_activation`. The per-agent buffer is not here -- it
is the agent's own `DIGMailbox`, which the graph only observes via `observe`.

```{eval-rst}
.. autoclass:: dig.DIGGraph
   :members: record_activation, update_activation_metadata, record_event, deliver, reroute_event, observe, register, offset, subscribe, to_dict
```
