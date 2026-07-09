"""research_domain.py -- an n-agent staged domain driven through DIG delivery.

A research question is answered in ORDERED stages: stage k may only
start after stage k-1's digest exists. The
stage work itself is split across N agents in parallel, and a reviewer
combines each stage's parts into the digest that unlocks the next stage.
Every hand-off is a delivered DIGEvent:

  - the domain CONSTRAINTS must hold: `DependencyConstraint` before any
    stage starts (all prerequisite stages complete), and
    `CapacityConstraint` for every worker firing (at most `max_parts`
    items; a reroute may only target a peer with spare capacity);
  - one overloaded agent REROUTES a work item to a peer (the reaction is
    recorded with the firing; the transport leg re-delivers), so the graph
    shows who actually did the work;
  - the final write-up carries the submit annotation, and the run checks
    itself with the lineage views (every root covered).

Run with:  python examples/research_domain.py [--agents N] [--viz]
"""

import argparse
import time

from dig import DIGEvent, DIGGraph
from dig.agent import DIGAgentEntity
from dig import views

Reaction = DIGEvent.Reaction

AGENT_API_SECONDS = 0.3   # simulated agent work per firing

STAGES = ("survey", "analyze", "write_up")


class DependencyConstraint:
    """A stage's prerequisites: it may only start once they are complete."""

    def __init__(self, stage: str, requires: tuple):
        self.stage = stage
        self.requires = tuple(requires)

    def holds(self, completed: set) -> bool:
        return all(prereq in completed for prereq in self.requires)

    def __repr__(self):
        return f"DependencyConstraint({self.stage} requires {list(self.requires)})"


class CapacityConstraint:
    """A worker's capacity: it may only work at most `max_parts` items in one firing."""

    def __init__(self, max_parts: int):
        self.max_parts = max_parts

    def holds(self, n_parts: int) -> bool:
        return n_parts <= self.max_parts

    def __repr__(self):
        return f"CapacityConstraint(max_parts={self.max_parts})"


def run(n_agents: int, *, live_viz: bool = False) -> None:
    dig = DIGGraph()
    reviewer = DIGAgentEntity("reviewer", dig)
    agents = [DIGAgentEntity(f"agent_{i + 1}", dig) for i in range(n_agents)]

    render = None
    if live_viz:
        from dig.viz import LiveDIGRender
        render = LiveDIGRender(dig)
    constraints = {
        stage: DependencyConstraint(stage, STAGES[:k])
        for k, stage in enumerate(STAGES)
    }
    capacities = {a.agent_id: CapacityConstraint(max_parts=2) for a in agents}

    # 1) The ROOT question arrives at the reviewer.
    root = dig.record_event(DIGEvent(
        payload={"question": "how do the agents coordinate?"},
        recipients={"reviewer": Reaction()},
    ))
    dig.deliver(root)

    completed: set = set()
    digest_event = None
    for stage in STAGES:
        constraint = constraints[stage]
        assert constraint.holds(completed), f"{constraint} violated"

        # 2) The reviewer fires: consume the unlock (the root, or the
        #    previous stage's digest) and fan the stage work out to all N.
        with reviewer.activate() as fan_out:
            time.sleep(AGENT_API_SECONDS)
            fan_out.outputs = [
                DIGEvent(
                    payload={"stage": stage, "part": i + 1},
                    recipients={agent.agent_id: Reaction()},
                )
                for i, agent in enumerate(agents)
            ]
        dig.deliver(fan_out.outputs)

        # 3) In the survey stage, agent_1 is overloaded and REROUTES its
        #    part to agent_2 -- recorded with the firing, then re-delivered.
        #    The reroute may only target a peer with spare CAPACITY.
        if stage == "survey" and n_agents >= 2:
            overloaded, helper = agents[0], agents[1]
            assert capacities[helper.agent_id].holds(
                len(helper.mailbox.pending) + 1
            ), f"{helper.agent_id} cannot absorb the rerouted part"
            with overloaded.activate() as handoff:
                time.sleep(AGENT_API_SECONDS)
                item = handoff.inputs[0]
                handoff.input_reactions = {item.id: Reaction(Reaction.Label.REROUTE)}
            dig.reroute_event(item, to=[helper.agent_id], by=handoff.id,
                              from_recipients=[])

        # 4) Every agent drains its buffer for this stage and reports its
        #    part(s) to the reviewer (the helper handles two in one firing).
        #    Every firing must be within the worker's CAPACITY.
        for agent in agents:
            if not agent.mailbox.pending:
                continue
            assert capacities[agent.agent_id].holds(len(agent.mailbox.pending)), (
                f"{agent.agent_id} over capacity: {len(agent.mailbox.pending)} > "
                f"{capacities[agent.agent_id].max_parts}"
            )
            with agent.activate() as work:
                time.sleep(AGENT_API_SECONDS)
                work.outputs = [DIGEvent(
                    payload={
                        "stage": stage,
                        "finding": f"{agent.agent_id}:{stage}:"
                                   f"{len(work.inputs)} part(s)",
                    },
                    recipients={"reviewer": Reaction()},
                )]
            dig.deliver(work.outputs)

        # 5) The reviewer combines the stage's findings into the digest
        #    that unlocks the next stage. The final digest is the SUBMIT.
        with reviewer.activate() as combine:
            time.sleep(AGENT_API_SECONDS)
            findings = [ev.payload["finding"] for ev in combine.inputs]
            digest = DIGEvent(
                payload={"digest": stage, "findings": findings},
                recipients={"reviewer": Reaction()},
            )
            combine.outputs = [digest]
            if stage == STAGES[-1]:
                combine.metadata = {"dig": {"submitting": True}}
        dig.deliver(combine.outputs)
        digest_event = combine.outputs[0]
        completed.add(stage)

    # 6) The run checks itself through the views.
    final = max(dig.activations.values(), key=lambda act: int(act.id[1:]))
    assert final.is_submitting
    assert views.lineage_covers_root_events(dig, final.id) is True
    assert views.any_coverage_complete(dig) is True
    graph = views.build_agent_graph(dig)
    reroutes = [e for e in graph.edges if e.kind == "rerouted"]
    if n_agents >= 2:
        assert reroutes, "the survey reroute should appear in the agent view"

    print(f"agents: {n_agents} + reviewer; stages: {' -> '.join(STAGES)}")
    print(f"recorded: {len(dig.activations)} activations, {len(dig.events)} events")
    print(f"constraints held: {[str(constraints[s]) for s in STAGES]} "
          f"+ {capacities[agents[0].agent_id]} per worker firing")
    if render is not None:
        from dig.viz import save_dig
        paths = save_dig(dig, "dig_artifacts")
        print(f"[viz] saved {paths['folder']}")
        render.freeze()
    print("research_domain: PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents", type=int, default=3, help="agents per stage")
    parser.add_argument("--viz", action="store_true", help="live window + save dig_artifacts/ folder")
    args = parser.parse_args()
    run(args.agents, live_viz=args.viz)
