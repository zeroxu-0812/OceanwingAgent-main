#!/usr/bin/env python3
"""DeerFlow wrapper for ABA keyword rank trend runs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _default_project_root() -> Path:
    env_root = os.environ.get("ABA_TRENDS_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "modules" / "aba-trends"
        if (candidate / "aba_trend_viewer" / "server.py").is_file():
            return candidate
    return Path(__file__).resolve().parents[4] / "modules" / "aba-trends"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ABA keyword rank trends from DeerFlow.")
    parser.add_argument("--project-root", default="", help="ABA trends project root. Defaults to ABA_TRENDS_ROOT or repo modules/aba-trends.")
    parser.add_argument("--keyword", action="append", default=[], help="Keyword to query. Repeat for multiple keywords.")
    parser.add_argument("--keywords", default="", help="Comma/newline-separated keyword list.")
    parser.add_argument("--granularity", choices=["week", "month", "all"], default="all", help="Trend granularity.")
    parser.add_argument("--start-date", help="Filter start date, YYYY-MM-DD for week or YYYY-MM for month.")
    parser.add_argument("--end-date", help="Filter end date, YYYY-MM-DD for week or YYYY-MM for month.")
    parser.add_argument("--batch-size", type=int, default=10, help="Keywords per SIF request, max 10.")
    return parser.parse_args()


def _keyword_payload(args: argparse.Namespace) -> list[str] | str:
    if args.keyword:
        return args.keyword
    return args.keywords


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).expanduser() if args.project_root else _default_project_root()
    project_root = project_root.resolve()
    if not (project_root / "aba_trend_viewer" / "server.py").exists():
        print(f"ERROR: aba_trend_viewer/server.py not found under project root: {project_root}", file=sys.stderr)
        return 2

    harness = project_root.parents[1] / "backend" / "packages" / "harness"
    for path in (project_root, harness):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

    print("Project root:", project_root)
    try:
        from deerflow.community.aba_trends.schema import AbaTrendsRunRequest
        from deerflow.community.aba_trends.workflow import run_aba_trends
    except Exception:
        from aba_deerflow.schema import AbaTrendsRunRequest
        from aba_deerflow.workflow import run_aba_trends

    request = AbaTrendsRunRequest(
        keywords=_keyword_payload(args),
        granularity=args.granularity,
        start_date=args.start_date,
        end_date=args.end_date,
        batch_size=args.batch_size,
        project_root=str(project_root),
    )
    summary = run_aba_trends(request)
    result = summary.model_dump() if hasattr(summary, "model_dump") else dict(summary.__dict__)
    print("Result:", result)
    return 0 if summary.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
