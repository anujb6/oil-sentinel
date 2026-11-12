#!/usr/bin/env python3
"""Validate a previously published data.json and print its image paths, one per line.

Exits non-zero when the snapshot is unusable (wrong schema, demo data, or unreadable),
so the workflow keeps the bundled file instead.
"""
from __future__ import annotations

import json
import re
import sys

SCHEMA_VERSION = 1
IMAGE_PATTERN = re.compile(r"^images/cushing-\d{4}-\d{2}-\d{2}\.png$")


def image_paths(snapshot: dict) -> list[str]:
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported snapshot schema")
    if snapshot.get("snapshot_mode") == "demo":
        raise ValueError("published snapshot is still the demo")
    scenes = (snapshot.get("satellite") or {}).get("scenes") or []
    return [s["image"] for s in scenes if isinstance(s, dict) and isinstance(s.get("image"), str) and IMAGE_PATTERN.match(s["image"])]


def main(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as handle:
            paths = image_paths(json.load(handle))
    except (OSError, ValueError) as exc:
        print(f"Unusable snapshot: {exc}", file=sys.stderr)
        return 1
    print("\n".join(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
