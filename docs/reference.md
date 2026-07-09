# API reference

Auto-generated from the code's own signatures and docstrings via Sphinx
[autodoc](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html).
This is the interface as the interpreter sees it; the [guides](guide/concept.md) add
the design rationale and pseudocode.

One page per part, each mirroring its guide:

| Reference page | Covers | Guide |
|---|---|---|
| [The DIG nodes](reference/nodes.md) | `DIGEvent`, `DIGActivation`, activation labels, and event stamps | [DIG nodes](guide/concept/nodes.md) |
| [The DIG graph](reference/graph.md) | `DIGGraph` | [DIG graph](guide/concept/graph.md) |
| [DIG views](reference/views.md) | `dig.views` -- the bipartite and lineage views of one DIG | [DIG graph](guide/concept/graph.md) |
| [The DIG interface](reference/interface.md) | `DIGAgent` | [DIG API](guide/interface.md) |
| [Healing](reference/healing.md) | `dig.heal` -- `Healer`, `Intervention`, the hook runners | [Healing](guide/concept/healing.md) |

```{toctree}
:hidden:
:maxdepth: 2

reference/nodes
reference/graph
reference/views
reference/interface
reference/healing
```
