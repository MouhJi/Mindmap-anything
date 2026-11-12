"""Replay a saved extraction pilot's original candidates without a provider call."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from knowledge.extraction import GROUNDING_VERSION, CandidateExtraction, validate_candidates
from knowledge.extraction_batch import _read_chunks


def replay(chunks_path: Path, pilot: Path, cache_path: Path) -> list[dict]:
    chunks, failures = _read_chunks(chunks_path)
    if failures:
        raise ValueError("The source dataset contains invalid rows")
    by_id = {chunk.chunk_id: chunk for _, chunk in chunks}
    status = (pilot / "chunk_status.jsonl").read_text(encoding="utf-8").splitlines()
    baseline = json.loads((pilot / "extraction_statistics.json").read_text(encoding="utf-8"))
    rows = []
    with closing(sqlite3.connect(cache_path.resolve().as_uri() + "?mode=ro", uri=True)) as cache:
        for line in status:
            record = json.loads(line)
            if record["status"] != "success" or not record["raw_relationships"]:
                continue
            chunk = by_id[record["chunk_id"]]
            if record["content_hash"] != chunk.content_hash:
                raise ValueError("The saved candidate source has changed")
            payloads = [
                json.loads(payload)
                for (payload,) in cache.execute(
                    "SELECT outcome FROM extractions WHERE completed_at = ?", (record["completed_at"],),
                )
            ]
            matches = [
                payload for payload in payloads
                if len(payload["relationship_checks"]) == record["raw_relationships"]
                and payload["metrics"] == record["metrics"]
            ]
            if len(matches) != 1:
                raise ValueError(f"Could not identify the original cache entry for {chunk.chunk_id}")
            saved, = matches
            old_checks = saved["relationship_checks"]
            candidates = CandidateExtraction(
                entities=saved["result"]["entities"],
                relationships=[item["candidate"] for item in old_checks],
            )
            result = validate_candidates(candidates, chunk)
            for before, checked in zip(old_checks, result.relationship_checks, strict=True):
                span = checked.evidence_span
                if span and span.text != chunk.text[span.start:span.end]:
                    raise ValueError("The replay produced an invalid evidence span")
                after = checked.model_dump(mode="json", exclude={"candidate"})
                rows.append({
                    "line": record["line"],
                    "chunk_id": chunk.chunk_id,
                    "source_url": chunk.url,
                    "candidate": before["candidate"],
                    "before": {key: before[key] for key in (
                        "accepted", "evidence_text_matched", "reasons",
                    )},
                    "after": after,
                })

    counts = _counts(rows, "before")
    if (counts["candidates"] != baseline["raw_relationships"]
            or counts["accepted"] != baseline["accepted_relationships"]
            or counts["rejected"] != baseline["rejected_relationships"]
            or (counts["matched"] / len(rows) if rows else None) != baseline["evidence_match_rate"]):
        raise ValueError("The replayed baseline does not match the saved pilot statistics")
    return rows


def _counts(rows: list[dict], phase: str) -> dict[str, int]:
    accepted = sum(row[phase]["accepted"] for row in rows)
    return {"candidates": len(rows), "accepted": accepted, "rejected": len(rows) - accepted,
            "matched": sum(row[phase]["evidence_text_matched"] for row in rows)}


def _edge(row: dict) -> str:
    candidate = row["candidate"]
    if not isinstance(candidate, dict):
        return "Malformed candidate"
    return " → ".join(
        str(candidate.get(key, "?")).replace("|", r"\|").replace("\n", " ")
        for key in ("source", "relation_type", "target")
    )


def _decision(decision: dict) -> str:
    return "Accepted" if decision["accepted"] else ", ".join(decision["reasons"])


def write_report(rows: list[dict], output: Path) -> None:
    before, after = (_counts(rows, phase) for phase in ("before", "after"))
    new = [row for row in rows if row["after"]["accepted"] and not row["before"]["accepted"]]
    remaining = [row for row in rows if not row["after"]["accepted"]]
    lines = [
        "# Offline evidence replay", "",
        f"Replayed {len(rows)} saved candidates with {GROUNDING_VERSION}. Gemini calls: 0.", "",
        "The comparison measures validator decisions and source matches. "
        "It does not estimate precision or recall.", "",
        "| Measure | Before | After |", "| --- | ---: | ---: |",
    ]
    for label, key in (("Candidates", "candidates"), ("Accepted", "accepted"),
                       ("Rejected", "rejected"), ("Evidence matches", "matched")):
        lines.append(f"| {label} | {before[key]} | {after[key]} |")
    lines.extend([
        "", "## Candidate decisions", "",
        "| Dataset line | Candidate | Before evidence | Before decision | After evidence | After decision |",
        "| ---: | --- | --- | --- | --- | --- |",
    ])
    for row in rows:
        span = row["after"]["evidence_span"]
        old_match = "Exact" if row["before"]["evidence_text_matched"] else "Missing"
        new_match = f"{span['kind']} [{span['start']}, {span['end']})" if span else "Missing"
        lines.append(
            f"| {row['line']} | {_edge(row)} | {old_match} | {_decision(row['before'])} | "
            f"{new_match} | {_decision(row['after'])} |"
        )
    lines.extend(["", "## Newly accepted relationships", ""])
    lines.extend([f"- {_edge(row)} (line {row['line']})." for row in new] or ["None."])
    lines.extend(["", "## Relationships requiring review", ""])
    lines.extend([
        f"- {_edge(row)} (line {row['line']}). {_decision(row['after'])}."
        for row in remaining
    ] or ["None."])
    reasons = Counter(reason for row in remaining for reason in row["after"]["reasons"])
    lines.extend(["", "## Rejection reason counts", ""])
    lines.extend([f"- {reason} ({count})" for reason, count in sorted(reasons.items())] or ["None."])
    lines.extend(["", "The JSON audit includes each original quote and the verified raw Markdown "
                  "for each recovered span. Offsets are zero-based, end-exclusive character "
                  "indices within the original chunk. [Candidate audit](candidates.json)", ""])
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (output / "candidates.json").write_text(
        json.dumps({"gemini_calls": 0, "before": before, "after": after, "candidates": rows},
                   indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = replay(args.chunks, args.pilot, args.cache)
    write_report(rows, args.output_dir)


if __name__ == "__main__":
    main()
