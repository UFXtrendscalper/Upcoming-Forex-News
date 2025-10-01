"""Utility tasks for development workflows."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_pytest() -> int:
    result = subprocess.run([sys.executable, "-m", "pytest"], cwd=ROOT)
    return result.returncode


def export_high() -> int:
    result = subprocess.run([sys.executable, "-m", "src.export_markdown", "--impact", "High"], cwd=ROOT)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project task runner")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("test", help="Run the pytest suite")
    sub.add_parser("export", help="Run the high-impact markdown exporter")

    args = parser.parse_args(argv)
    if args.command == "test":
        return run_pytest()
    if args.command == "export":
        return export_high()
    parser.error("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
