"""
dig/viz/config.py

DIG visualization config -- the single place to tweak the appearance of the
interaction-graph renderers (the matplotlib realtime view + the plotly
interactive view). All colors and sizes live here so the two renderers never
drift apart.

Tweak a color or size here and both renderers pick it up.
"""

from typing import Dict, Optional

# --- node colors ---------------------------------------------------------

# Activation node colors by classification from the derived bipartite graph.
ACTIVATION_COLORS: Dict[Optional[str], str] = {
    "submit": "#0ea5e9",             # sky blue -- matches the submit edge (NOT consume-green)
    "problem-reducing": "#1f77b4",   # blue
    "problem-expanding": "#DAA520",  # goldenrod
    "failed": "#b91c1c",             # dark red -- a firing that raised instead of completing
    None: "#1f77b4",                 # default
}
SYSTEM_COLOR = "#ff1493"             # hot pink -- system (healer) activations

# Event node colors.
EVENT_DEFAULT_COLOR = "lightgray"    # communication / plain events
EVENT_ROOT_COLOR = "lightgray"       # root events (no producing activation; same color, bigger)
EVENT_TOOL_COLOR = "#e8a04b"         # tool-generated events (carry metadata["tool_call_id"])

# Shared ink -- marker outlines and in-node label text, both renderers.
NODE_OUTLINE_COLOR = "#333333"
NODE_LABEL_COLOR = "#111111"

# Edge colors in the derived graph view.
EDGE_ACTION_COLORS: Dict[str, str] = {
    "consume": "#2ca02c",     # green
    "rerouted": "#9370db",    # solid purple for a rerouted path that continued
    "reroute": "#9370db",     # dashed purple for reaction marked as reroute
    "discard": "#d62728",     # red
    "wait": "#ff8c00",        # orange
    "pending": "gray",
    "submit": "#0ea5e9",      # sky blue -- consumed by a submitting activation
}
SYSTEM_ANNOTATION_COLOR = "#ff1493"  # hot pink -- system (healer) edges; matches SYSTEM_COLOR, distinct from wait-orange

# Edge line style per reaction kind -- the single source for solid-vs-dashed.
#   SOLID  = problem-solving dataflow (consume / submit / production / continued
#            reroute path): drawn in BOTH the Full and Clean panels.
#   DASHED = control / no-op (reroute / discard / wait, and system interventions):
#            drawn in the Full panel ONLY -- the Clean panel drops them.
EDGE_STYLE_SOLID = "-"
EDGE_STYLE_DASHED = "--"
EDGE_ACTION_STYLES: Dict[str, str] = {
    "consume": EDGE_STYLE_SOLID,
    "rerouted": EDGE_STYLE_DASHED,   # reroute is a control reaction (no task action)
    "submit": EDGE_STYLE_SOLID,
    "pending": EDGE_STYLE_SOLID,     # production edges (activation -> event it generated)
    "reroute": EDGE_STYLE_DASHED,    # the outgoing-rerouted (away) edge
    "discard": EDGE_STYLE_DASHED,
    "wait": EDGE_STYLE_DASHED,
}

# --- node sizes (matplotlib scatter `s`) ---------------------------------

EVENT_SIZE = 90
EVENT_ROOT_SIZE = 105                # root events drawn bigger
EVENT_TOOL_SIZE = 90
ACTIVATION_SIZE = 250
SYSTEM_SIZE = 150
ACTIVATION_NODE_ALPHA = 0.78
EVENT_NODE_ALPHA = 0.88

# --- timeline (gantt) panel ----------------------------------------------

ACT_HEIGHT = 0.5                     # activation bar height (lanes)
MIN_ACT_WIDTH_FRAC = 0.005           # min bar width as a fraction of the x-range

# --- agent view ------------------------------------------------------

AGENT_NODE_SIZE = 44                  # agent-node marker diameter (plotly)
AGENT_ROOT_NODE_SIZE = 30             # root-node marker diameter (plotly)
AGENT_ARC_CURVATURE = 0.18            # arc bow as a fraction of chord length
AGENT_ARC_KIND_SPREAD = 0.05          # extra bow between same-direction kinds
AGENT_SELF_LOOP_RADIUS = 0.16         # self-loop radius (unit-circle coords)
AGENT_EDGE_LABEL_FONTSIZE = 11        # link-count label on each arc
AGENT_NODE_LABEL_FONTSIZE = 13        # agent-name label under each node (plotly)
AGENT_BADGE_SIZE = 18                 # link-count badge marker diameter (plotly)
AGENT_BADGE_FILL = "#ffffff"          # badge fill; the ring takes the edge-kind color

# --- fonts ---------------------------------------------------------------

AXIS_LABEL_FONTSIZE = 18
PANEL_LABEL_FONTSIZE = 28
TICK_FONTSIZE = 16
LEGEND_FONTSIZE = 14
ACTIVATION_LABEL_FONTSIZE = 7
EVENT_LABEL_FONTSIZE = 6
