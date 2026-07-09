(function () {
  var DIG_NODE_DETAILS = __DIG_NODE_DETAILS_JSON__;
  function traceGraphDiv() {
    // The trace figure is the only plot outside a server-rendered section.
    var graphs = document.querySelectorAll(".plotly-graph-div");
    for (var i = 0; i < graphs.length; i++) {
      if (!graphs[i].closest("[data-dig-panel]")) {
        return graphs[i];
      }
    }
    return null;
  }
  function resizePlots(container) {
    if (!window.Plotly || !container) {
      return;
    }
    container.querySelectorAll(".plotly-graph-div").forEach(function (plot) {
      window.Plotly.Plots.resize(plot);
    });
  }
  function setupDIGTabs() {
    var traceGraph = traceGraphDiv();
    if (!traceGraph || document.getElementById("dig-view-tabs")) {
      return;
    }
    var parent = traceGraph.parentNode;
    var trace = document.createElement("section");
    trace.id = "dig-trace-section";
    trace.className = "dig-tab-panel";
    trace.setAttribute("data-dig-panel", "trace");
    trace.setAttribute("data-dig-tab-label", "Bipartite view");
    parent.insertBefore(trace, traceGraph);
    trace.appendChild(traceGraph);

    var panels = [trace];
    document.querySelectorAll(".dig-tab-section[data-dig-panel]").forEach(function (panel) {
      parent.insertBefore(panel, panels[panels.length - 1].nextSibling);
      panels.push(panel);
    });

    var tabs = document.createElement("div");
    tabs.id = "dig-view-tabs";
    tabs.setAttribute("role", "tablist");
    panels.forEach(function (panel) {
      var button = document.createElement("button");
      button.className = "dig-tab-button";
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("data-dig-tab", panel.getAttribute("data-dig-panel"));
      button.textContent = panel.getAttribute("data-dig-tab-label");
      tabs.appendChild(button);
    });
    parent.insertBefore(tabs, trace);

    function showTab(name) {
      panels.forEach(function (panel) {
        var show = panel.getAttribute("data-dig-panel") === name;
        panel.style.display = show ? "block" : "none";
        if (show) {
          resizePlots(panel);
        }
      });
      tabs.querySelectorAll("[data-dig-tab]").forEach(function (button) {
        var active = button.getAttribute("data-dig-tab") === name;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      });
    }
    tabs.addEventListener("click", function (event) {
      var button = event.target && event.target.closest
        ? event.target.closest("[data-dig-tab]")
        : null;
      if (!button) {
        return;
      }
      showTab(button.getAttribute("data-dig-tab"));
    });
    showTab("trace");
  }
  function bindNodeDetailPanel() {
    var panel = document.getElementById("dig-node-detail-panel");
    var content = document.getElementById("dig-node-detail-content");
    var close = document.getElementById("dig-node-detail-close");
    var header = document.getElementById("dig-node-detail-header");
    var back = document.getElementById("dig-node-detail-back");
    if (!panel || !content || !close || !header || !back) {
      return;
    }

    var history = [];
    var currentId = null;

    function render(id) {
      var detail = DIG_NODE_DETAILS[id];
      if (detail == null) {
        return false;
      }
      content.innerHTML = detail;
      content.scrollTop = 0;
      currentId = id;
      back.style.visibility = history.length ? "visible" : "hidden";
      return true;
    }
    function showNode(id, opts) {
      if (DIG_NODE_DETAILS[id] == null) {
        return;
      }
      var push = !opts || opts.push !== false;
      if (push && currentId !== null && currentId !== id) {
        history.push(currentId);
      }
      if (render(id)) {
        panel.classList.add("open");
      }
    }
    function openFresh(id) {
      // A graph click starts a new inspection, so drop the link history.
      history = [];
      currentId = null;
      showNode(id, { push: false });
    }
    function goBack() {
      if (!history.length) {
        return;
      }
      render(history.pop());
    }

    close.addEventListener("click", function () {
      panel.classList.remove("open");
    });
    back.addEventListener("click", goBack);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        panel.classList.remove("open");
      }
    });
    var dragging = false, startX = 0, startY = 0, startLeft = 0, startTop = 0;
    header.addEventListener("pointerdown", function (event) {
      if (event.target === close || event.target === back) {
        return;  // let the header buttons handle their own clicks
      }
      var rect = panel.getBoundingClientRect();
      // Re-anchor from right/top to left/top so the panel can move freely,
      // and pin the width so right:auto can't collapse it (e.g. under @media).
      panel.style.left = rect.left + "px";
      panel.style.top = rect.top + "px";
      panel.style.width = rect.width + "px";
      panel.style.right = "auto";
      panel.style.bottom = "auto";
      startX = event.clientX;
      startY = event.clientY;
      startLeft = rect.left;
      startTop = rect.top;
      dragging = true;
      header.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    header.addEventListener("pointermove", function (event) {
      if (!dragging) {
        return;
      }
      var maxLeft = Math.max(0, window.innerWidth - panel.offsetWidth);
      var maxTop = Math.max(0, window.innerHeight - panel.offsetHeight);
      panel.style.left = Math.min(Math.max(0, startLeft + event.clientX - startX), maxLeft) + "px";
      panel.style.top = Math.min(Math.max(0, startTop + event.clientY - startY), maxTop) + "px";
    });
    function endDrag() {
      dragging = false;
    }
    header.addEventListener("pointerup", endDrag);
    header.addEventListener("pointercancel", endDrag);

    content.addEventListener("click", function (event) {
      var target = event.target;
      var link = target && target.closest ? target.closest("[data-node-id]") : null;
      if (!link) {
        return;
      }
      event.preventDefault();
      showNode(link.getAttribute("data-node-id"));
    });
    // Clicks resolve against the registry, so binding every plot is safe:
    // customdata that is not a registry key (or is absent) just no-ops.
    document.querySelectorAll(".plotly-graph-div").forEach(function (graph) {
      if (!graph.on) {
        return;
      }
      graph.on("plotly_click", function (data) {
        if (!data || !data.points || !data.points.length) {
          return;
        }
        var id = data.points[0].customdata;
        if (id == null) {
          return;
        }
        openFresh(id);
      });
    });
  }
  function bindDIGInteractivePage() {
    setupDIGTabs();
    bindNodeDetailPanel();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindDIGInteractivePage);
  } else {
    bindDIGInteractivePage();
  }
})();
