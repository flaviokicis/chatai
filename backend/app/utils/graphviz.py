from __future__ import annotations

import json
import json as _json
import os
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.agents.common.question_graph import (
    QuestionGraph,
    build_question_graph_from_params,
)


def _escape(label: str) -> str:
    # For Mermaid inside a text node, avoid escaping quotes or <br/>. Keep as-is.
    return label


def _mermaid_nodes_edges(graph: QuestionGraph, indent: str = "") -> str:
    lines: list[str] = []
    # Nodes
    for key, q in graph.items():
        safe_label = _escape(f"{q.prompt}<br/>({key})")
        lines.append(f'{indent}{key}["{safe_label}"]')
    # Edges from dependencies
    for key, q in graph.items():
        lines.extend(f"{indent}{dep} --> {key}" for dep in q.dependencies if graph.get(dep))
    return "\n".join(lines)


def _mermaid_for_flat_graph(graph: QuestionGraph, title: str | None = None) -> str:
    lines: list[str] = ["flowchart TD"]
    if title:
        lines.append(f"  %% {title}")
    ne = _mermaid_nodes_edges(graph, indent="  ")
    if ne:
        lines.append(ne)
    return "\n".join(lines) + "\n"


def build_graph_from_json_payload(
    payload: dict[str, Any],
) -> tuple[QuestionGraph, dict[str, QuestionGraph] | None, dict[str, Any] | None]:
    cfg = payload.get("question_graph")
    if isinstance(cfg, dict) and ("global" in cfg or "paths" in cfg):
        global_qg = build_question_graph_from_params({"question_graph": cfg.get("global", [])})
        path_to_qg: dict[str, QuestionGraph] = {}
        paths = cfg.get("paths", {})
        if isinstance(paths, dict):
            for name, section in paths.items():
                questions = section.get("questions", []) if isinstance(section, dict) else []
                path_to_qg[str(name)] = build_question_graph_from_params(
                    {"question_graph": questions}
                )
        # No special disambiguation step; rely on questions and LLM to infer path if needed
        return global_qg, path_to_qg, None

    # flat list fallback
    return build_question_graph_from_params(payload), None, None


def _zero_dependency_keys(graph: QuestionGraph) -> list[str]:
    return [k for k, q in graph.items() if not q.dependencies]


def _sanitize_id(raw: str) -> str:
    return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in raw)


def render_mermaid_from_json(payload: dict[str, Any], title: str | None = None) -> str:
    global_qg, path_qgs, _ = build_graph_from_json_payload(payload)

    if not path_qgs:
        return _mermaid_for_flat_graph(global_qg, title)

    # Compose a subgraph per path, plus global
    lines: list[str] = ["flowchart TD"]
    if title:
        lines.append(f"  %% {title}")

    # Global subgraph
    lines.append('  subgraph GLOBAL["Global Questions"]')
    ne = _mermaid_nodes_edges(global_qg, indent="    ")
    if ne:
        lines.append(ne)
    lines.append("  end")

    # Paths
    for name, qg in path_qgs.items():
        label = _escape(str(name))
        sid = _sanitize_id(str(name))
        entry = f"PATH_{sid}__ENTRY"
        lines.append(f'  subgraph PATH_{sid}["Path: {label}"]')
        # Entry node for the path to attach edges to
        lines.append(f'    {entry}(("{label}"))')
        ne = _mermaid_nodes_edges(qg, indent="    ")
        if ne:
            lines.append(ne)
        # Entry connects to zero-dependency questions for this path
        lines.extend(f"    {entry} --> {k}" for k in _zero_dependency_keys(qg))
        lines.append("  end")

    return "\n".join(lines) + "\n"


def render_html_mermaid_via_kroki(payload: dict[str, Any], title: str | None = None) -> str:
    """
    Render using the Kroki HTTP API to generate SVG server-side. Useful to bypass
    browser Mermaid issues and to validate syntax before opening the file.
    """
    diagram_src = render_mermaid_from_json(payload, title)
    api_url = os.environ.get("KROKI_URL", "https://kroki.io") + "/mermaid/svg"
    parsed = urlparse(api_url)
    if parsed.scheme not in {"http", "https"}:
        msg = f"Unsupported URL scheme for KROKI_URL: {parsed.scheme}"
        raise ValueError(msg)
    req = urllib.request.Request(  # noqa: S310 - scheme validated above
        api_url,
        data=_json.dumps({"diagram_source": diagram_src}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - scheme validated above
            svg = resp.read().decode("utf-8")
    except Exception as exc:  # pragma: no cover - network fallback
        svg = f"<pre>Failed to render via Kroki: {exc}\n\n{diagram_src}</pre>"

    return f"""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{_escape(title or "Question Graph")}</title>
    <style>
      body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Helvetica Neue, Arial, \"Apple Color Emoji\", \"Segoe UI Emoji\"; padding: 16px; }}
      #diagram {{ background: white; border-radius: 8px; padding: 12px; }}
    </style>
  </head>
  <body>
    <h1>{_escape(title or "Question Graph")}</h1>
    <div id=\"diagram\">{svg}</div>
  </body>
</html>
"""


def render_html_file_from_json_path(path: str | Path, title: str | None = None) -> str:
    p = Path(path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    return render_html_mermaid_via_kroki(payload, title or p.stem)
