"""Live DIG rendering attached to a graph via its update hook.

The graph layer owns no rendering: `LiveDIGRender(dig)` subscribes to
`DIGGraph.subscribe` and pushes every mutation into the realtime
matplotlib window. If the backend is non-interactive (or the window
fails to open, or the user closes it), rendering disables itself and
the run continues headless.
"""

from __future__ import annotations

from typing import Any


class LiveDIGRender:
    """Auto-updating live matplotlib window over one DIG."""

    def __init__(self, dig: Any):
        self._dig = dig
        self._visualizer: Any = None
        self._disabled = False
        dig.subscribe(self.update)

    def update(self) -> None:
        """Push the current graph state into the live window."""
        if self._disabled:
            return
        if self._visualizer is not None and self._visualizer.is_closed():
            self._visualizer = None
            self._disabled = True
            return
        if self._visualizer is None:
            import matplotlib
            try:
                from matplotlib.backends import BackendFilter, backend_registry
                interactive = backend_registry.list_builtin(BackendFilter.INTERACTIVE)
            except Exception:  # older matplotlib
                from matplotlib import rcsetup
                interactive = rcsetup.interactive_bk
            backend = matplotlib.get_backend()
            if backend.lower() not in {b.lower() for b in interactive}:
                print(f"[DIG render disabled] backend {backend!r} is non-interactive")
                self._disabled = True
                return
            from .realtime import RealtimeDIGVisualizer
            try:
                self._visualizer = RealtimeDIGVisualizer()
                self._visualizer.start(block=False)
            except Exception as exc:  # noqa: BLE001
                print(f"[DIG render disabled] {exc}")
                self._disabled = True
                self._visualizer = None
                return
        self._visualizer.update_from_dig(self._dig)

    def freeze(self, *, wait_for_close: bool = False) -> None:
        """Stop the animation loop; optionally block until the window closes."""
        if self._visualizer is None:
            return
        if wait_for_close and not self._visualizer.is_closed():
            self._visualizer.render(self._dig)
            self._visualizer.freeze()
            self._visualizer.wait_for_close()
            return
        self._visualizer.freeze()
