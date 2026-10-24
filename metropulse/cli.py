from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ingest import load_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MetroPulse deterministic pipeline.")
    parser.add_argument("command", choices=["ingest"])
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    dataset = load_dataset(args.data)
    result = {
        "events": len(dataset["events"]),
        "tickets": len(dataset["tickets"]),
        "telemetry": len(dataset["telemetry"]),
        "rejects": dataset["rejects"],
        "topology_nodes": len(dataset["topology"].nodes),
        "topology_edges": sum(len(value) for value in dataset["topology"]._adj.values()) // 2,
    }
    print(json.dumps(result, indent=2))
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "ingest_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
