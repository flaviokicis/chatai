from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def find_last_object(text: str) -> Tuple[Dict[str, Any], int, int]:
    """Return the last JSON object from a text that may be:
    - a JSON array of objects
    - a single JSON object
    - concatenated JSON objects

    Returns a tuple of (object, start_index, end_index).
    """
    decoder = json.JSONDecoder()

    # Try as JSON array or dict first
    try:
        data = json.loads(text)
        if isinstance(data, list) and data:
            return data[-1], 0, len(text)
        if isinstance(data, dict):
            return data, 0, len(text)
    except Exception:
        pass

    # Fallback: scan from right for an object start and decode
    pos = len(text)
    while True:
        brace_idx = text.rfind("{", 0, pos)
        if brace_idx == -1:
            raise RuntimeError("Could not locate a JSON object in the file tail")
        try:
            obj, end = decoder.raw_decode(text, brace_idx)
            return obj, brace_idx, end
        except Exception:
            pos = brace_idx
            continue


def walk_strings(obj: Any) -> List[str]:
    strings: List[str] = []
    if isinstance(obj, str):
        strings.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            strings.extend(walk_strings(v))
    elif isinstance(obj, list):
        for v in obj:
            strings.extend(walk_strings(v))
    return strings


def walk_keys(obj: Any, key_name: str) -> List[Any]:
    found: List[Any] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key_name:
                found.append(v)
            found.extend(walk_keys(v, key_name))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(walk_keys(v, key_name))
    return found


def extract_conversation_from_text(text: str) -> List[str]:
    lines = [ln.strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln.startswith("User:") or ln.startswith("Assistant:")]


def dedupe_preserve_order(seq: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def summarize_last_object(obj: Dict[str, Any], limit_lines: int = 48) -> Dict[str, Any]:
    strings = walk_strings(obj)

    # Aggregate conversation lines across all strings to avoid truncation
    all_convo_lines: List[str] = []
    for s in strings:
        if ("User:" in s) or ("Assistant:" in s):
            all_convo_lines.extend(extract_conversation_from_text(s))

    # Deduplicate while preserving order (some prompts repeat history)
    convo_excerpt = dedupe_preserve_order(all_convo_lines)

    if convo_excerpt and len(convo_excerpt) > limit_lines:
        convo_excerpt = convo_excerpt[-limit_lines:]

    node_ids = [v for v in walk_keys(obj, "current_node_id") if isinstance(v, str)]

    # Also parse current_node_id occurrences from embedded text blocks
    text_node_ids: List[str] = []
    pattern = re.compile(r'"current_node_id"\s*:\s*"([^"]+)"')
    for s in strings:
        text_node_ids.extend(m.group(1) for m in pattern.finditer(s))

    unknown_mentions = any("current node" in s.lower() and "unknown" in s.lower() for s in strings)

    # Summarize top-level keys and sizes (no payloads)
    top_keys = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            entry = {"key": k, "type": type(v).__name__}
            if isinstance(v, str):
                entry["len"] = len(v)
            elif isinstance(v, list):
                entry["len"] = len(v)
            elif isinstance(v, dict):
                entry["len"] = len(v)
            top_keys.append(entry)

    summary = {
        "top_level_keys": top_keys,
        "current_node_ids_seen": dedupe_preserve_order(node_ids + text_node_ids),
        "turn_count": next((t for t in walk_keys(obj, "turn_count") if isinstance(t, int)), None),
        "unknown_node_mentions": unknown_mentions,
        "conversation_excerpt": convo_excerpt,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize last JSON object of a large Langfuse export without prompts")
    parser.add_argument("--path", type=Path, required=True, help="Path to JSON file (array or concatenated JSON)")
    parser.add_argument("--limit-lines", type=int, default=48, help="Max number of User/Assistant lines to print")
    args = parser.parse_args()

    text = args.path.read_text(encoding="utf-8")
    obj, _start, _end = find_last_object(text)
    summary = summarize_last_object(obj, limit_lines=args.limit_lines)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


