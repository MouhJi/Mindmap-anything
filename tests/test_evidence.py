import pytest

from knowledge.evidence import EvidenceMatcher
from knowledge.extraction import CandidateExtraction, validate_candidates
from knowledge.ingestion import KnowledgePipeline
from knowledge.models import ExtractionResult, SourceChunk
from knowledge.repository import InMemoryRepository


def chunk(text):
    return SourceChunk(
        project_id="p", chunk_id="c", document_id="d", url="https://example.test/docs", text=text,
    )


def check(text, quote, edges, names=("FastAPI", "Pydantic", "Starlette", "Litestar", "AnyIO")):
    envelope = CandidateExtraction(
        entities=[{"name": name, "type": "Library"} for name in names],
        relationships=[
            {"chunk_id": "c", "source": source, "target": target,
             "relation_type": "DEPENDS_ON", "evidence": quote}
            for source, target in edges
        ],
    )
    return validate_candidates(envelope, chunk(text))


@pytest.mark.parametrize(("text", "edges"), [
    ("FastAPI depends on Pydantic and Starlette.",
     [("FastAPI", "Pydantic"), ("FastAPI", "Starlette")]),
    ("FastAPI and Litestar depend on Starlette.",
     [("FastAPI", "Starlette"), ("Litestar", "Starlette")]),
    ("FastAPI depends on Pydantic, Starlette, and AnyIO.",
     [("FastAPI", "Pydantic"), ("FastAPI", "Starlette"), ("FastAPI", "AnyIO")]),
])
def test_named_coordination_preserves_direction(text, edges):
    reverse = [(target, source) for source, target in edges]
    result = check(text, text, edges + reverse)
    assert [(r.source, r.target) for r in result.result.relationships] == edges
    assert all(item.evidence_text_matched for item in result.relationship_checks)
    assert not any(item.accepted for item in result.relationship_checks[len(edges):])


@pytest.mark.parametrize("text", [
    "FastAPI does not depend on Pydantic and Starlette.",
    "FastAPI may depend on Pydantic and Starlette.",
    "FastAPI and Litestar might depend on Starlette.",
    "If FastAPI depends on Pydantic and Starlette, check its license.",
    "FastAPI depends on Pydantic or Starlette.",
    "FastAPI depends on Pydantic and Litestar depends on Starlette.",
    "FastAPI and Litestar depend on Pydantic and Starlette, respectively.",
    "FastAPI and Starlette are discussed.",
])
def test_coordination_does_not_imply_an_unsupported_dependency(text):
    result = check(text, text, [("FastAPI", "Starlette")])
    assert result.relationship_checks[0].evidence_text_matched
    assert not result.relationship_checks[0].accepted


def test_projected_evidence_returns_raw_markdown_and_character_offsets():
    prefix = "Résumé 🙂.\n\n"
    raw = "**FastAPI** depends on *Pydantic* and [Starlette](https://example.test/)."
    quote = "FastAPI depends on Pydantic and Starlette."
    text = prefix + raw + " More details follow."
    result = check(text, quote, [("FastAPI", "Starlette")])
    span = result.relationship_checks[0].evidence_span
    assert span.kind == "markdown"
    assert (span.start, span.end) == (len(prefix), len(prefix) + len(raw))
    assert span.text == text[span.start:span.end] == raw
    assert result.result.relationships[0].evidence == raw


def test_literal_quote_has_priority_and_raw_span_is_persisted():
    raw = "FastAPI depends on [Starlette](https://example.test)."
    quote = "FastAPI depends on Starlette."
    match = EvidenceMatcher(raw + " " + quote).find(quote)
    assert match.span.kind == "exact" and match.span.start == len(raw) + 1

    store = InMemoryRepository()
    result = ExtractionResult(
        entities=[{"name": name, "type": "Library"} for name in ("FastAPI", "Starlette")],
        relationships=[{"chunk_id": "c", "source": "FastAPI", "target": "Starlette",
                        "relation_type": "DEPENDS_ON", "evidence": quote}],
    )
    report = KnowledgePipeline(store).ingest_chunk(chunk(raw), result)
    assert report.accepted_relationships == 1
    assert next(iter(store.evidence.values())).text == raw


@pytest.mark.parametrize("text", [
    "FastAPI depends on `Starlette`.",
    "FastAPI depends on Starlette-extra.",
    "FastAPI depends on [another library](https://example.test/Starlette).",
    "FastAPI depends on **Pydantic**.",
    "FastAPI does **not** depend on [Starlette](https://example.test).",
    r"FastAPI depends on \*Starlette\*.",
    "Example `Run this. **FastAPI** depends on [Starlette](https://example.test).`",
    "FastAPI depends on [Starlette](https://example.test) plugins.",
])
def test_markdown_matching_does_not_remove_code_or_change_words(text):
    result = check(text, "FastAPI depends on Starlette.", [("FastAPI", "Starlette")])
    assert not result.relationship_checks[0].evidence_text_matched
    assert not result.result.relationships


def test_code_syntax_is_preserved_in_markdown_projection():
    raw = "**FastAPI** depends on `Starlette`."
    quote = "FastAPI depends on `Starlette`."
    result = check(raw, quote, [("FastAPI", "Starlette")])
    assert result.relationship_checks[0].evidence_span.text == raw
    assert len(result.result.relationships) == 1


def test_projected_list_quote_is_a_match_but_not_a_top_level_assertion():
    raw = "**FastAPI** depends on [Starlette](https://example.test)."
    result = check("- " + raw, "FastAPI depends on Starlette.", [("FastAPI", "Starlette")])
    audit = result.relationship_checks[0]
    assert audit.evidence_span.text == raw and audit.evidence_span.start == 2
    assert not audit.accepted


def test_markdown_aware_matching_preserves_contradictory_context():
    raw = "FastAPI depends on Starlette."
    text = raw + "\n\n**FastAPI** does not depend on [Starlette](https://example.test)."
    result = check(text, raw, [("FastAPI", "Starlette")])
    assert "contradictory_source_context" in result.relationship_checks[0].reasons


def test_whole_sentence_wrapped_in_emphasis_recovers_full_raw_span():
    quote = "FastAPI depends on Starlette."
    raw = f"**{quote}**"
    result = check(raw, quote, [("FastAPI", "Starlette")])
    assert result.result.relationships[0].evidence == raw
    assert result.relationship_checks[0].evidence_span.kind == "markdown"


def test_crlf_evidence_keeps_original_offsets_and_newlines():
    text = "Background.\r\n**FastAPI** depends on\r\nStarlette."
    raw = "**FastAPI** depends on\r\nStarlette."
    result = check(text, "FastAPI depends on\r\nStarlette.", [("FastAPI", "Starlette")])
    span = result.relationship_checks[0].evidence_span
    assert span.text == text[span.start:span.end] == raw
    assert result.result.relationships[0].evidence == raw


def test_matching_rejects_an_altered_link_destination():
    raw = "FastAPI depends on [Starlette](https://example.test)."
    altered = raw.replace("example.test", "different.test")
    assert EvidenceMatcher(raw).find(altered) is None
