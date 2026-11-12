"""Run auditable, resumable extraction over section chunk JSONL without graph writes."""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from collections.abc import Iterable
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter

from pydantic import ValidationError

from .chunking import SectionChunk
from .extraction import (
    GROUNDING_VERSION, PROMPT_VERSION, SCHEMA_VERSION, SYSTEM_PROMPT, ExtractionError,
    GroundedExtraction, StructuredExtractor, extraction_skip_reasons,
)
from .models import ExtractionResult, GraphPolicy, stable_id
from .provider import GeminiProvider, GeminiSettings, ProviderError, StructuredProvider


@dataclass
class ChunkRun:
    record: dict
    extraction: GroundedExtraction | None = None


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _read_chunks(path: Path) -> tuple[list[tuple[int, SectionChunk]], list[ChunkRun]]:
    chunks = []
    failures = []
    seen = set()
    with path.open("rb") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line.decode("utf-8-sig"))
                if not isinstance(row, dict):
                    raise ValueError("Expected a chunk object")
                supplied_hash = row.pop("content_hash", None)
                # Reject non-finite numbers and unpaired Unicode surrogates before
                # this row can affect a cache key or report.
                json.dumps(row, ensure_ascii=False, allow_nan=False).encode("utf-8")
                chunk = SectionChunk.model_validate(row, strict=True)
                content_hash = chunk.content_hash
            except ValueError:
                failures.append(ChunkRun({"line": number, "status": "invalid_input",
                                          "reason": "malformed_chunk"}))
                continue
            if supplied_hash is not None and supplied_hash != content_hash:
                reason = "chunk_hash_mismatch"
            elif chunk.chunk_id in seen:
                reason = "duplicate_chunk_id"
            else:
                seen.add(chunk.chunk_id)
                chunks.append((number, chunk))
                continue
            failures.append(ChunkRun({"line": number, "status": "invalid_input", "reason": reason,
                                      "chunk_id": chunk.chunk_id, "document_id": chunk.document_id,
                                      "source_url": chunk.url}))
    return chunks, failures


def _cache_key(chunk: SectionChunk, revision: str) -> str:
    return stable_id(
        "extraction", chunk.project_id, chunk.chunk_id, chunk.content_hash,
        chunk.document_title, chunk.section_title,
        json.dumps(chunk.heading_path, ensure_ascii=False), revision,
    )


@contextmanager
def _report_file(path: Path):
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            yield stream
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_rows(path: Path, rows: Iterable[dict]) -> None:
    with _report_file(path) as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def _relationship_rows(runs: list[ChunkRun], *, accepted: bool) -> Iterable[dict]:
    for run in runs:
        if run.extraction is None:
            continue
        relations = iter(run.extraction.result.relationships)
        for check in run.extraction.relationship_checks:
            if check.accepted != accepted:
                continue
            fields = (next(relations).model_dump(mode="json", exclude={"chunk_id"})
                      if accepted else {"candidate": check.candidate})
            yield {**run.record, **fields, **check.model_dump(mode="json", exclude={"candidate"})}


def _statistics(runs: list[ChunkRun], eligible: int, elapsed: float) -> dict:
    complete = [run for run in runs if run.extraction is not None]
    checks = [check for run in complete for check in run.extraction.relationship_checks]
    fresh_metrics = [run.record["metrics"] for run in runs
                     if run.record.get("metrics") and not run.record.get("cached")]

    def measured_sum(field: str):
        values = [metrics[field] for metrics in fresh_metrics if metrics[field] is not None]
        return sum(values) if values else None

    accepted = sum(check.accepted for check in checks)
    failed = sum(run.record["status"] == "failed" for run in runs)
    return {
        "processed_chunks": len(complete) + failed, "eligible_chunks": eligible,
        "skipped_chunks": sum(run.record["status"] == "skipped" for run in runs),
        "successful_chunks": len(complete), "failed_chunks": failed,
        "invalid_input_rows": sum(run.record["status"] == "invalid_input" for run in runs),
        "cached_chunks": sum(bool(run.record.get("cached")) for run in complete),
        "raw_entities": sum(run.extraction.raw_entities for run in complete),
        "raw_relationships": len(checks), "accepted_relationships": accepted,
        "rejected_relationships": len(checks) - accepted,
        "evidence_match_rate": (sum(check.evidence_text_matched for check in checks) / len(checks)
                                if checks else None),
        "provider_requests": sum(metrics["attempts"] for metrics in fresh_metrics),
        "input_tokens": measured_sum("input_tokens"),
        "output_tokens": measured_sum("output_tokens"),
        "chunks_with_input_token_usage": sum(m["input_tokens"] is not None for m in fresh_metrics),
        "chunks_with_output_token_usage": sum(
            m["output_tokens"] is not None for m in fresh_metrics
        ),
        "provider_latency_ms": measured_sum("latency_ms"),
        "total_execution_seconds": elapsed,
    }


async def run_batch(
    chunks_path: Path, output: Path, *, provider: StructuredProvider, batch_size: int = 10,
    concurrency: int = 2, limit: int | None = None, chunk_ids: Iterable[str] = (),
    cache_path: Path | None = None,
) -> dict:
    if min(batch_size, concurrency) < 1 or (limit is not None and limit < 1):
        raise ValueError("Batch size, concurrency and limit must be positive")
    started = perf_counter()
    chunks, runs = _read_chunks(chunks_path)
    selection = set(chunk_ids)
    if selection - {chunk.chunk_id for _, chunk in chunks}:
        raise ValueError("One or more selected chunk IDs are absent from the input")

    extractor = StructuredExtractor(provider, provider_version=provider.version)
    policy = GraphPolicy()
    revision = stable_id(
        "extraction_config", provider.model, extractor.version, SYSTEM_PROMPT, SCHEMA_VERSION,
        GROUNDING_VERSION, policy.fingerprint,
        json.dumps(ExtractionResult.model_json_schema(), sort_keys=True),
        json.dumps(extractor.generation_schema, sort_keys=True),
    )
    common = {"model": provider.model, "provider_version": provider.version,
              "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION,
              "grounding_version": GROUNDING_VERSION, "quality_policy": policy.version}
    for run in runs:
        run.record.update(common, completed_at=_timestamp())

    pending = []
    eligible = 0
    for line, chunk in chunks:
        record = {
            **common, "line": line, "project_id": chunk.project_id, "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id, "source_url": chunk.url,
            "document_title": chunk.document_title, "heading_path": chunk.heading_path,
            "content_hash": chunk.content_hash,
        }
        reasons = extraction_skip_reasons(chunk)
        if reasons:
            runs.append(ChunkRun(dict(record, status="skipped", reasons=reasons,
                                      completed_at=_timestamp())))
            continue
        eligible += 1
        if not selection or chunk.chunk_id in selection:
            pending.append((record, chunk))

    output.mkdir(parents=True, exist_ok=True)
    cache_path = cache_path or output / "extraction_cache.sqlite3"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    slots = asyncio.Semaphore(concurrency)

    with closing(sqlite3.connect(cache_path)) as cache:
        cache.execute("CREATE TABLE IF NOT EXISTS extractions ("
                      "key TEXT PRIMARY KEY, completed_at TEXT NOT NULL, outcome TEXT NOT NULL)")

        async def process(record: dict, chunk: SectionChunk) -> ChunkRun:
            key = _cache_key(chunk, revision)
            row = cache.execute("SELECT completed_at, outcome FROM extractions WHERE key = ?",
                                (key,)).fetchone()
            if row:
                completed_at, payload = row
                try:
                    outcome = GroundedExtraction.model_validate_json(payload)
                except ValidationError:
                    row = None
                else:
                    metrics = outcome.metrics
                    if metrics is None or not metrics.success or outcome.skip_reasons:
                        row = None
            if not row:
                try:
                    async with slots:
                        outcome = await extractor.extract_async(chunk)
                except (ProviderError, ExtractionError) as error:
                    metrics = getattr(error, "metrics", None)
                    return ChunkRun(dict(record, status="failed", error_type=type(error).__name__,
                                         metrics=metrics.model_dump() if metrics else None,
                                         completed_at=_timestamp()))
                completed_at = _timestamp()
                with cache:
                    cache.execute("INSERT OR REPLACE INTO extractions VALUES (?, ?, ?)",
                                  (key, completed_at, outcome.model_dump_json()))
            return ChunkRun(dict(record, status="success", cached=bool(row),
                                 completed_at=completed_at, metrics=outcome.metrics.model_dump(),
                                 raw_entities=outcome.raw_entities,
                                 raw_relationships=len(outcome.relationship_checks)), outcome)

        selected = pending[:limit]
        for offset in range(0, len(selected), batch_size):
            runs.extend(await asyncio.gather(*(
                process(record, chunk) for record, chunk in selected[offset:offset + batch_size]
            )))

    runs.sort(key=lambda run: run.record["line"])
    _write_rows(output / "chunk_status.jsonl", (run.record for run in runs))
    _write_rows(output / "extracted_entities.jsonl", (
        {**run.record, **entity.model_dump(mode="json")}
        for run in runs if run.extraction is not None
        for entity in run.extraction.result.entities
    ))
    _write_rows(output / "extracted_relationships.jsonl", _relationship_rows(runs, accepted=True))
    _write_rows(output / "rejected_relationships.jsonl", _relationship_rows(runs, accepted=False))
    _write_rows(output / "extraction_failures.jsonl", (
        run.record for run in runs if run.record["status"] in {"failed", "invalid_input"}
    ))
    stats = _statistics(runs, eligible, perf_counter() - started)
    with _report_file(output / "extraction_statistics.json") as stream:
        json.dump(stats, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return stats


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chunks", type=Path, help="Section chunk JSONL export")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache", type=Path, help="SQLite checkpoint path (default: output dir)")
    parser.add_argument("--batch-size", type=_positive_int, default=10)
    parser.add_argument("--concurrency", type=_positive_int, help="Defaults to Gemini concurrency")
    select = parser.add_mutually_exclusive_group(required=True)
    select.add_argument("--limit", type=_positive_int, help="First N eligible chunks in input order")
    select.add_argument("--chunk-id", action="append", help="Select one chunk ID (repeatable)")
    select.add_argument("--all", action="store_true", help="Process every eligible chunk")
    args = parser.parse_args()

    async def run(settings: GeminiSettings) -> dict:
        async with GeminiProvider(settings) as provider:
            return await run_batch(
                args.chunks, args.output_dir, provider=provider, cache_path=args.cache,
                batch_size=args.batch_size,
                concurrency=args.concurrency or settings.max_concurrent_requests,
                limit=args.limit, chunk_ids=args.chunk_id or (),
            )

    try:
        settings = GeminiSettings.from_env()
        stats = asyncio.run(run(settings))
    except (ProviderError, ValueError, OSError, sqlite3.Error) as error:
        print(f"Extraction could not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(stats, indent=2))
    return int(bool(stats["failed_chunks"] or stats["invalid_input_rows"]))


if __name__ == "__main__":
    raise SystemExit(main())
