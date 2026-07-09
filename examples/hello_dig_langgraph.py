"""
examples/hello_dig_langgraph.py

The same tiny message flow as `hello_dig.py`, but LangGraph owns scheduling and
transport. The domain-side nodes consume and return normal LangGraph state
updates; the DIG wrapper projects those messages into DIGEvents so DIG can record
receipt timing, activations, event lineage, and output events.

DIG does not classify event meaning here. The message payload is opaque to DIG.

Run:
      python examples/hello_dig_langgraph.py                       # needs `langgraph`
      python examples/hello_dig_langgraph.py --viz                 # live window + save dig_artifacts/ folder
      python examples/hello_dig_langgraph.py --viz out             # live window + save out/ artifact folder
      python examples/hello_dig_langgraph.py --realtime-viz        # live window only
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
from typing import Any, Dict, List, Optional, Sequence, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover
    raise SystemExit("this example needs langgraph:  pip install langgraph")

from dig.interface import DIGAgent
from dig.views import edges
from dig.viz import LiveDIGRender, save_dig
from dig.graph import DIGEvent, DIGGraph

DEFAULT_AGENT_API_SECONDS = 1.0
Message = Dict[str, Any]
_MESSAGE_COUNTER = itertools.count(1)


class FlowState(TypedDict):
    messages: List[Message]


def _message(payload: Optional[Dict[str, Any]] = None,
             *,
             message_id: Optional[str] = None) -> Message:
    return {
        "id": message_id or f"m{next(_MESSAGE_COUNTER)}",
        "payload": dict(payload or {}),
    }


class LangGraphPlanner:
    """Plain LangGraph-side planner. No DIG types, no graph writes."""

    def __init__(self, api_seconds: float = DEFAULT_AGENT_API_SECONDS):
        self.api_seconds = api_seconds

    async def __call__(self, state: FlowState) -> FlowState:
        messages = state.get("messages", [])
        seed = messages[-1]["payload"] if messages else {}
        message = await simulated_agent_api(
            _message({"text": "draft plan", "saw": seed.get("text", "")}),
            seconds=self.api_seconds,
        )
        return {"messages": [message]}


class LangGraphWorker:
    """Plain LangGraph-side worker. It returns framework state, not a DIGEvent."""

    def __init__(self, api_seconds: float = DEFAULT_AGENT_API_SECONDS):
        self.api_seconds = api_seconds

    async def __call__(self, state: FlowState) -> FlowState:
        plan = state["messages"][-1]["payload"]
        message = await simulated_agent_api(
            _message({"text": "worked from plan", "saw": plan.get("text", "")}),
            seconds=self.api_seconds,
        )
        return {"messages": [message]}


class LangGraphVerifier:
    """Plain LangGraph-side verifier. It returns framework state, not a DIGEvent."""

    def __init__(self, api_seconds: float = DEFAULT_AGENT_API_SECONDS):
        self.api_seconds = api_seconds

    async def __call__(self, state: FlowState) -> FlowState:
        result = state["messages"][-1]["payload"]
        message = await simulated_agent_api(
            _message({"text": "verified", "saw": result.get("text", "")}),
            seconds=self.api_seconds,
        )
        return {"messages": [message]}


async def simulated_agent_api(
    response: Message,
    *,
    seconds: float = DEFAULT_AGENT_API_SECONDS,
) -> Message:
    seconds = max(0.0, seconds)
    if seconds:
        await asyncio.sleep(seconds)
    return response


def _recipient_reaction(recipients: Sequence[str]) -> Dict[str, DIGEvent.Reaction]:
    return {
        recipient: DIGEvent.Reaction()
        for recipient in recipients
    }


def _event_for_message(
    message: Message,
    registry: Dict[str, DIGEvent],
    *,
    recipients: Sequence[str] = (),
) -> DIGEvent:
    message_id = str(message["id"])
    event = registry.get(message_id)
    if event is None:
        event = DIGEvent(
            payload=dict(message.get("payload", {})),
            recipients=_recipient_reaction(recipients),
            metadata={"message_id": message_id},
            delivery_policy=None,
        )
        registry[message_id] = event
    else:
        for recipient in recipients:
            event.recipients.setdefault(recipient, DIGEvent.Reaction())
    return event


def _input_to_events(
    state: FlowState,
    registry: Dict[str, DIGEvent],
    *,
    recipient: str,
) -> List[DIGEvent]:
    return [
        _event_for_message(message, registry, recipients=[recipient])
        for message in state.get("messages", [])
    ]


def _output_to_events(
    output: FlowState | Message | Sequence[Message] | None,
    registry: Dict[str, DIGEvent],
    *,
    recipients: Sequence[str],
) -> List[DIGEvent]:
    if output is None:
        return []
    if isinstance(output, dict) and "messages" in output:
        messages = list(output["messages"])
    elif isinstance(output, dict):
        messages = [output]
    else:
        messages = list(output)
    return [
        _event_for_message(message, registry, recipients=recipients)
        for message in messages
    ]


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
    message_events: Dict[str, DIGEvent] = {}

    planner = DIGAgent(
        "planner",
        LangGraphPlanner(args.activation_time),
        dig,
        input_to_events=lambda state: _input_to_events(
            state,
            message_events,
            recipient="planner",
        ),
        output_to_events=lambda output: _output_to_events(
            output,
            message_events,
            recipients=["worker"],
        ),
    )
    worker = DIGAgent(
        "worker",
        LangGraphWorker(args.activation_time),
        dig,
        input_to_events=lambda state: _input_to_events(
            state,
            message_events,
            recipient="worker",
        ),
        output_to_events=lambda output: _output_to_events(
            output,
            message_events,
            recipients=["verifier"],
        ),
    )
    verifier = DIGAgent(
        "verifier",
        LangGraphVerifier(args.activation_time),
        dig,
        input_to_events=lambda state: _input_to_events(
            state,
            message_events,
            recipient="verifier",
        ),
        output_to_events=lambda output: _output_to_events(
            output,
            message_events,
            recipients=["planner"],
        ),
    )

    graph = StateGraph(FlowState)
    graph.add_node("planner", planner)
    graph.add_node("worker", worker)
    graph.add_node("verifier", verifier)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "worker")
    graph.add_edge("worker", "verifier")
    graph.add_edge("verifier", END)
    app = graph.compile()

    seed = _message({"text": "start"}, message_id="m0")
    final = asyncio.run(app.ainvoke({"messages": [seed]}, {"recursion_limit": 20}))
    last = final["messages"][-1]

    print("=" * 60)
    print(f"outcome: {last['payload']}")
    print(f"DIG: {len(dig.activations)} activations, {len(dig.events)} events, "
          f"{len(edges(dig))} derived edges -- recorded WITHOUT DIG delivery")
    print("PASS")
    if args.viz is not None:
        paths = save_dig(dig, args.viz)
        print(f"[viz] saved {paths['folder']}")
    if live is not None:
        live.freeze()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
