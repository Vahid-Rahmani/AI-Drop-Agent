"""Command-line entry point for the deterministic end-to-end simulation."""

from __future__ import annotations

import argparse
import json

from app.brain import Brain


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI Drop Agent in simulation mode")
    parser.add_argument("--query", default="hoodie")
    args = parser.parse_args()
    result = Brain().run_simulation(args.query)
    print(json.dumps(result, default=str, indent=2))


if __name__ == "__main__":
    main()
