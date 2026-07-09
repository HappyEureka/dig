"""
examples/hello_dig.py

Hello, DIG -- a tiny agent message flow recorded as a Dynamic Interaction Graph.

DIG observes the interaction structure:

    root event -> planner activation -> worker activation -> verifier activation

It does not decide task correctness, classify failures, or model agent capability.
Those semantics belong to a task/env layer outside DIG. Here events are opaque
payloads plus recipients; the graph records timing, delivery, activation
lineage, and per-input reactions.

Run:
      python examples/hello_dig.py
      python examples/hello_dig.py --viz                 # live window + save dig_artifacts/ folder
      python examples/hello_dig.py --viz out             # live window + save out/ artifact folder
      python examples/hello_dig.py --realtime-viz        # live window only
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any, Callable, Dict, List

from dig.interface import DIGAgent
from dig.graph import DIGEvent, DIGGraph
from dig.views import edges
from dig.viz import LiveDIGRender, save_dig

DEFAULT_AGENT_API_SECONDS = 1.0


def simulated_agent_api(
    behavior: Callable[[List[DIGEvent]], DIGEvent],
    seconds: float = DEFAULT_AGENT_API_SECONDS,
):
    seconds = max(0.0, seconds)

    async def call(events: List[DIGEvent]) -> DIGEvent:
        if seconds:
            await asyncio.sleep(seconds)
        return behavior(events)

    return call


class Planner:
    def __call__(self, events: List[DIGEvent]) -> DIGEvent:
        seed = events[-1].payload if events else {}
        return DIGEvent(
            payload={"text": "draft plan", "saw": seed.get("text", "")},
            recipients={"worker": DIGEvent.Reaction()},
        )


class Worker:
    def __call__(self, events: List[DIGEvent]) -> DIGEvent:
        plan = events[-1]
        return DIGEvent(
            payload={"text": "worked from plan", "input_event": plan.id},
            recipients={"verifier": DIGEvent.Reaction()},
        )


class Verifier:
    def __call__(self, events: List[DIGEvent]) -> DIGEvent:
        result = events[-1]
        return DIGEvent(
            payload={"text": "verified", "input_event": result.id},
            recipients={"planner": DIGEvent.Reaction()},
        )


async def _fire(dig: DIGGraph, agent: DIGAgent) -> DIGEvent:
    produced, _ = await agent.fire()
    for event in produced:
        dig.deliver(event)
    return produced[0]


async def orchestrate(
    dig: DIGGraph,
    planner: DIGAgent,
    worker: DIGAgent,
    verifier: DIGAgent,
) -> Dict[str, Any]:
    seed = dig.record_event(DIGEvent(
        payload={"text": "start"},
        recipients={"planner": DIGEvent.Reaction()},
        metadata={"seed": True},
    ))
    dig.deliver(seed)

    for agent in (planner, worker, verifier):
        event = await _fire(dig, agent)

    return event.payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--viz", nargs="?", const="dig_artifacts", default=None, metavar="STEM",
                    help="open live DIG view and save final STEM/ artifact folder (default STEM: dig_artifacts)")
    ap.add_argument("--realtime-viz", action="store_true",
                    help="open a live matplotlib DIG window during execution without saving artifacts")
    ap.add_argument("--activation-time", type=float, default=DEFAULT_AGENT_API_SECONDS,
                    help="seconds spent by the simulated agent API")
    args = ap.parse_args()

    live_viz = args.realtime_viz or args.viz is not None
    dig = DIGGraph()
    live = LiveDIGRender(dig) if live_viz else None
    planner = DIGAgent("planner", simulated_agent_api(Planner(), args.activation_time), dig)
    worker = DIGAgent("worker", simulated_agent_api(Worker(), args.activation_time), dig)
    verifier = DIGAgent("verifier", simulated_agent_api(Verifier(), args.activation_time), dig)

    final_payload = asyncio.run(
        orchestrate(dig, planner, worker, verifier)
    )

    print("=" * 60)
    print(f"outcome: {final_payload}")
    print(f"DIG: {len(dig.activations)} activations, {len(dig.events)} events, "
          f"{len(edges(dig))} derived edges")
    print(f"observe: {dig.observe()}")
    print("PASS")
    if args.viz is not None:
        paths = save_dig(dig, args.viz)
        print(f"[viz] saved {paths['folder']}")
    if live is not None:
        live.freeze()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
