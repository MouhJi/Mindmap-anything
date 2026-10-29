"""Integration checks against the actual, unmodified crawler output."""

import json
from pathlib import Path

import pytest

from scripts.verify_cleaning import verify_document

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", [f"page{index:04d}.json" for index in range(1, 7)])
def test_real_crawler_page(name: str) -> None:
    path = ROOT / "output" / name
    raw = json.loads(path.read_text(encoding="utf-8"))
    cleaned, report = verify_document(raw)
    assert all(report["checks"].values())
    assert cleaned["metadata"] == raw["metadata"]
    if name == "page0006.json":
        assert raw["url"] == "https://fastapi.tiangolo.com/async/"
        assert all(counts["before"] > 0 for counts in report["entities"].values())
        assert "[¶](" not in cleaned["markdown"]
        assert "Back to top" not in cleaned["markdown"]
