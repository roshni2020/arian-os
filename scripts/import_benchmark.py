"""Inspect and save one supported public URL without repository execution."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wildfire_researcher.benchmarks.routes import catalog
from wildfire_researcher.benchmarks.service import import_url

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True)
    args = p.parse_args()
    try:
        record = import_url(catalog(), args.url)
    except ValueError as exc:
        p.error(str(exc))
    print(json.dumps({"id": record["id"], "status": record["status"], "benchmark_id": (record["benchmark"] or {}).get("id"), "warnings": record["warnings"]}, indent=2))

if __name__ == "__main__":
    main()
