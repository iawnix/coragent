"""CLI for the evidence-directed search recovery planner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from recovery import decide


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description="Plan a general reaction-path search recovery")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def run(args):
    output = args.output_dir
    if output.exists():
        raise ValueError("new output directory required")
    spec = json.loads(args.input.read_text(encoding="utf-8"))
    result = decide(spec)
    output.mkdir(parents=True)
    (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    run(parse_arguments())
