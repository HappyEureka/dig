"""DIG renderers.

Public surface: attach `LiveDIGRender` for a live matplotlib window (the
realtime render), build the agent view as an interactive
figure, or call `save_dig` for the finished-run artifact folder. The data
views live in `dig.views`; viz owns no graph state.
"""

from .html.agent_graph_view import build_agent_graph_viz
from .mpl.live import LiveDIGRender
from .mpl.realtime import RealtimeDIGVisualizer
from .save import save_dig

__all__ = [
    "LiveDIGRender",
    "RealtimeDIGVisualizer",
    "build_agent_graph_viz",
    "save_dig",
]
