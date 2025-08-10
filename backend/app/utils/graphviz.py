from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.common.question_graph import (
    QuestionGraph,
    build_question_graph_from_params,
)


def _escape(label: str) -> str:
    return label.replace('"', '\\"')


def _mermaid_nodes_edges(graph: QuestionGraph, indent: str = "") -> str:
    lines: list[str] = []
    # Nodes
    for key, q in graph.items():
        safe_label = _escape(f"{q.prompt}\\n({key})")
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
        disamb = cfg.get("disambiguation") if isinstance(cfg.get("disambiguation"), dict) else None
        return global_qg, path_to_qg, disamb

    # flat list fallback
    return build_question_graph_from_params(payload), None, None


def render_mermaid_from_json(payload: dict[str, Any], title: str | None = None) -> str:
    global_qg, path_qgs, disamb = build_graph_from_json_payload(payload)

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

    # Disambiguation node (optional)
    if disamb:
        safe_label = _escape(f"{disamb.get('prompt', 'Select Path')}")
        lines.append(f'  disamb{{"{safe_label}"}}')

    # Paths
    for name, qg in path_qgs.items():
        label = _escape(str(name))
        lines.append(f'  subgraph PATH_{name}["Path: {label}"]')
        ne = _mermaid_nodes_edges(qg, indent="    ")
        if ne:
            lines.append(ne)
        lines.append("  end")
        if disamb:
            lines.append(f"  disamb --> PATH_{name}")

    return "\n".join(lines) + "\n"


def render_html_mermaid(payload: dict[str, Any], title: str | None = None) -> str:
    mermaid_src = render_mermaid_from_json(payload, title)
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{_escape(title or "Question Graph")}</title>
    <script src=\"https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js\"></script>
    <script>window.mermaid.initialize({{ startOnLoad: true }});</script>
    <style>
      body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Helvetica Neue, Arial, \"Apple Color Emoji\", \"Segoe UI Emoji\"; padding: 16px; }}
      .mermaid {{ background: white; border-radius: 8px; padding: 12px; }}
    </style>
  </head>
  <body>
    <h1>{_escape(title or "Question Graph")}</h1>
    <div class=\"mermaid\">{_escape(mermaid_src)}</div>
  </body>
</html>
"""


def render_html_file_from_json_path(path: str | Path, title: str | None = None) -> str:
    p = Path(path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    return render_html_mermaid(payload, title or p.stem)
