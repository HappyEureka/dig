# Reference: DIG views

Ways of looking at one recorded DIG. The graph (`dig`) is the
representation; a VIEW is a way of looking at that same underlying record.
Each view is a subpackage of `dig.views`: `view.py` holds the way
of looking (its structure/materialization), and sibling topical modules
hold its ANALYSES -- the questions and computations that way of looking
makes easy (query a property, check coverage). Renderers
and viz consume views; the dig package never imports them.

The views:

- **bipartite** -- every activation and event as a
  node-and-edge trace (`edges`, `activation_event_graph`; nothing here is
  separately stored state). Its lineage analysis asks ancestry questions
  walked backward over the trace: the run's root events (events with no
  producing activation), an activation's backward lineage, and whether
  that lineage covers every root (`root_events`,
  `lineage_event_ids_from`, `lineage_covers_root_events`,
  `uncovered_root_events`, `untouched_root_events`,
  `any_coverage_complete`, `submit_activations` -- FAILED firings neither
  consume nor produce, so coverage skips them). Its node-detail analysis
  summarizes what one trace node opens up to
  (`activation_detail_fields`, `activation_detail_text`).
- **agent** -- one node per agent, directed edges
  bundling every event flow between each pair, grouped by reaction kind
  (`build_agent_graph`); root events flow out of a synthetic `ROOT_AGENT`
  node, and `agent_node_key` / `agent_edge_key` mint the stable string ids
  renderers key their registries on.

To add a view: a new subpackage with `view.py` (+ analysis modules),
re-exported from `dig/views/__init__.py`.

```{eval-rst}
.. automodule:: dig.views.bipartite.view
   :members: edges, activation_event_graph, DIGBipartiteNode, DIGBipartiteEdge, DIGBipartiteGraphData

.. automodule:: dig.views.bipartite.lineage
   :members:

.. automodule:: dig.views.bipartite.detail
   :members: activation_detail_fields, activation_detail_text


.. automodule:: dig.views.agent.view
   :members: build_agent_graph, producer_agent, agent_node_key, agent_edge_key, AgentGraph, AgentGraphEdge, AgentGraphLink
```
