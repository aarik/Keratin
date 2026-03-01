#!/usr/bin/env python3
"""
Rhino MCP Extended - Log Manager

This is a lightweight helper to view and filter logs across:
- ./logs/server/
- ./logs/rhino/
- ./logs/diagnostics/

(You can add more directories later if needed.)

It expects log lines formatted roughly like:
[YYYY-MM-DD HH:MM:SS] [LEVEL] [component] message

If lines don't match, they're still shown, just with a best-effort timestamp.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional


LOG_PATTERN = re.compile(
    r"^\[(?P<ts>[^]]+)\]\s+\[(?P<level>[^]]+)\]\s+\[(?P<component>[^]]+)\]\s+(?P<msg>.*)$"
)

DEFAULT_DIRS = [
    ("server", "logs/server"),
    ("rhino", "logs/rhino"),
    ("diagnostic", "logs/diagnostics"),
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(order=True)
class Entry:
    ts: datetime
    level: str
    component: str
    msg: str
    source: str


def _parse_ts(raw: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    # fallback
    return datetime.fromtimestamp(0)


def collect(paths: List[Path], since: Optional[datetime], levels: Optional[List[str]],
            components: Optional[List[str]]) -> List[Entry]:
    entries: List[Entry] = []
    for p in paths:
        try:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line.strip():
                        continue
                    m = LOG_PATTERN.match(line)
                    if m:
                        ts = _parse_ts(m.group("ts"))
                        level = m.group("level").upper()
                        comp = m.group("component")
                        msg = m.group("msg")
                    else:
                        ts = datetime.fromtimestamp(p.stat().st_mtime)
                        level = "INFO"
                        comp = "unknown"
                        msg = line

                    if since and ts < since:
                        continue
                    if levels and level not in levels:
                        continue
                    if components and comp not in components:
                        continue

                    entries.append(Entry(ts=ts, level=level, component=comp, msg=msg, source=str(p)))
        except Exception as e:
            print(f"Error reading {p}: {e}", file=sys.stderr)
    entries.sort()
    return entries


def _color(level: str) -> str:
    return {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41m\033[97m",
    }.get(level, "")


def display(entries: List[Entry], colors: bool, show_source: bool, tail: Optional[int]) -> None:
    if tail is not None and len(entries) > tail:
        entries = entries[-tail:]

    reset = "\033[0m"
    for e in entries:
        ts = e.ts.strftime("%Y-%m-%d %H:%M:%S")
        src = f" ({os.path.basename(e.source)})" if show_source else ""
        if colors:
            c = _color(e.level)
            print(f"{c}[{ts}] [{e.level}] [{e.component}] {e.msg}{src}{reset}")
        else:
            print(f"[{ts}] [{e.level}] [{e.component}] {e.msg}{src}")


def main() -> int:
    ap = argparse.ArgumentParser(description="View and filter Rhino MCP Extended logs.")
    ap.add_argument("--since-minutes", type=int, default=None, help="Only show entries newer than N minutes.")
    ap.add_argument("--level", action="append", default=None, help="Filter by level (repeatable). e.g. --level ERROR")
    ap.add_argument("--component", action="append", default=None, help="Filter by component (repeatable).")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--show-source", action="store_true")
    ap.add_argument("--tail", type=int, default=200, help="Show only last N entries (default 200). Use 0 for all.")
    args = ap.parse_args()

    root = _project_root()
    paths: List[Path] = []
    for _name, rel in DEFAULT_DIRS:
        d = root / rel
        d.mkdir(parents=True, exist_ok=True)
        paths.extend(Path(p) for p in glob.glob(str(d / "*.log")))

    since = None
    if args.since_minutes is not None:
        since = datetime.now() - timedelta(minutes=args.since_minutes)

    levels = [x.upper() for x in (args.level or [])] or None
    comps = args.component or None

    entries = collect(paths, since, levels, comps)
    tail = None if args.tail == 0 else args.tail
    display(entries, colors=not args.no_color, show_source=args.show_source, tail=tail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
