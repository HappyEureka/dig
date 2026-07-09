"""count_frequency_domain.py -- an n-agent counting domain driven through DIG delivery.

A coordinator splits a character-counting problem into per-worker chunks, N
workers count their chunk in parallel, and an aggregator combines the
partials into the final tally. Every hand-off is a delivered DIGEvent, so
the whole run is observable as one interaction graph:

  - the domain CONSTRAINT (`CapacityConstraint`) must hold for every
    assignment: a worker never receives a chunk longer than its capacity;
  - the aggregator WAITS until every partial has arrived (waited inputs
    stay buffered across firings), then consumes them all in one firing;
  - the final firing carries the submit annotation, and the run checks
    itself with the lineage views (every root covered).

Run with:  python examples/count_frequency_domain.py [--agents N] [--viz]
"""

import argparse
import time
import random
from collections import Counter

from dig import DIGEvent, DIGGraph
from dig.agent import DIGAgentEntity
from dig import views

Reaction = DIGEvent.Reaction

AGENT_API_SECONDS = 0.3   # simulated agent work per firing


class CapacityConstraint:
    """A worker's capacity: it may only count chunks up to `max_len` chars."""

    def __init__(self, max_len: int):
        self.max_len = max_len

    def holds(self, chunk: str) -> bool:
        return len(chunk) <= self.max_len

    def __repr__(self):
        return f"CapacityConstraint(max_len={self.max_len})"


def run(n_agents: int, *, seed: int = 7, live_viz: bool = False) -> None:
    rng = random.Random(seed)
    text = "".join(rng.choice("abcde") for _ in range(20 * n_agents))
    truth = Counter(text)

    dig = DIGGraph()
    coordinator = DIGAgentEntity("coordinator", dig)
    workers = [DIGAgentEntity(f"agent_{i + 1}", dig) for i in range(n_agents)]
    aggregator = DIGAgentEntity("aggregator", dig)
    constraints = {w.agent_id: CapacityConstraint(max_len=25) for w in workers}

    render = None
    if live_viz:
        from dig.viz import LiveDIGRender
        render = LiveDIGRender(dig)

    # 1) The ROOT problem arrives at the coordinator (no producing activation).
    root = dig.record_event(DIGEvent(
        payload={"problem": "count character frequencies", "text": text},
        recipients={"coordinator": Reaction()},
    ))
    dig.deliver(root)

    # 2) The coordinator fires: split the text into one chunk per worker.
    #    The capacity constraint must HOLD for every assignment.
    per = (len(text) + n_agents - 1) // n_agents
    with coordinator.activate() as split:
        time.sleep(AGENT_API_SECONDS)
        chunks = [text[i * per:(i + 1) * per] for i in range(n_agents)]
        for worker, chunk in zip(workers, chunks):
            assert constraints[worker.agent_id].holds(chunk), (
                f"{worker.agent_id} over capacity: {len(chunk)} > "
                f"{constraints[worker.agent_id].max_len}"
            )
        split.outputs = [
            DIGEvent(payload={"chunk": chunk}, recipients={w.agent_id: Reaction()})
            for w, chunk in zip(workers, chunks)
        ]
    dig.deliver(split.outputs)

    # 3) Each worker fires on its delivered chunk and sends a partial count.
    partials = []
    for worker in workers:
        with worker.activate() as count:
            time.sleep(AGENT_API_SECONDS)
            chunk = count.inputs[0].payload["chunk"]
            count.outputs = [DIGEvent(
                payload={"partial": dict(Counter(chunk))},
                recipients={"aggregator": Reaction()},
            )]
        dig.deliver(count.outputs)
        partials.append(count.outputs[0])

        # The aggregator peeks after each arrival but WAITS until all N are
        # in -- waited inputs stay buffered for the next firing.
        if len(aggregator.mailbox.pending) < n_agents:
            with aggregator.activate() as peek:
                time.sleep(AGENT_API_SECONDS)
                peek.input_reactions = {
                    ev.id: Reaction(Reaction.Label.WAIT) for ev in peek.inputs
                }

    # 4) The aggregator consumes ALL partials in one firing and submits.
    with aggregator.activate() as combine:
        time.sleep(AGENT_API_SECONDS)
        assert len(combine.inputs) == n_agents
        total: Counter = Counter()
        for ev in combine.inputs:
            total.update(ev.payload["partial"])
        combine.outputs = [DIGEvent(
            payload={"answer": dict(total)},
            recipients={"coordinator": Reaction()},
        )]
        combine.metadata = {"dig": {"submitting": True}}
    dig.deliver(combine.outputs)

    # 5) The run checks itself through the views.
    assert dict(truth) == combine.outputs[0].payload["answer"]
    assert views.lineage_covers_root_events(dig, combine.id) is True
    assert views.any_coverage_complete(dig) is True
    graph = views.build_agent_graph(dig)
    assert "aggregator" in graph.agents and f"agent_{n_agents}" in graph.agents

    print(f"agents: {n_agents} workers + coordinator + aggregator")
    print(f"recorded: {len(dig.activations)} activations, {len(dig.events)} events")
    print(f"answer matches ground truth over {len(text)} chars; roots covered")
    if render is not None:
        from dig.viz import save_dig
        paths = save_dig(dig, "dig_artifacts")
        print(f"[viz] saved {paths['folder']}")
        render.freeze()
    print("count_frequency_domain: PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents", type=int, default=3, help="number of workers")
    parser.add_argument("--viz", action="store_true", help="live window + save dig_artifacts/ folder")
    args = parser.parse_args()
    run(args.agents, live_viz=args.viz)
