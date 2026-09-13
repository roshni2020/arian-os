"""Refresh bounded public benchmark metadata; never executes training."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wildfire_researcher.benchmarks.routes import catalog
from wildfire_researcher.benchmarks.service import sync_provider

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provider", choices=["huggingface", "openml"], default="huggingface")
    p.add_argument("--query", default="")
    p.add_argument("--curated", action="store_true", help="Read and refresh the five source-reviewed library examples")
    p.add_argument("--limit", type=int, choices=range(1, 101), default=10)
    args = p.parse_args()
    if args.curated:
        from wildfire_researcher.benchmarks.curated import seed_library
        result = seed_library(catalog())
    else:
        result = sync_provider(catalog(), args.provider, args.query, args.limit)
    print(json.dumps({"ids": [b["id"] for b in result["items"]], "warnings": result["warnings"]}, indent=2))

if __name__ == "__main__":
    main()
