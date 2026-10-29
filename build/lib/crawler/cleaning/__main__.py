"""Run the cleaning stage on an existing page JSON, without crawling."""

import argparse
import json
from pathlib import Path

from . import clean_document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Choose a separate output path to preserve the raw crawl.")
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    cleaned = clean_document(raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(cleaned.model_dump_json(indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
