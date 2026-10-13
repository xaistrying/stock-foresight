"""The brief's copy of the disclaimer against docs/DISCLAIMER.md "Brief version", and its tie to the model's
coverage (spec: "Fixed sentences, footer and the brief disclaimer are guarded")."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.ml import volatility as vol_mod
from app.services.brief import wording
from app.services.range import coverage_phrase

from .test_brief_support import REPO_ROOT, brief_isolation, write_artifact  # noqa: F401

DISCLAIMER_MD = REPO_ROOT / "docs" / "DISCLAIMER.md"
REAL_MODEL = vol_mod.MODEL_PATH  # read at import, before the isolation fixture redirects it


def _brief_section(path: Path) -> str:
    """The blockquote under `## Brief version`, normalised as test_debate_export_api.py does."""
    lines = path.read_text(encoding="utf-8").splitlines()
    rest = lines[lines.index("## Brief version") + 1:]
    quote = []
    for line in (l for l in rest if l.strip()):
        if not line.startswith(">"):
            break
        quote.append(line[1:])
    return re.sub(r"\s+", " ", " ".join(quote)).strip()


def test_the_copy_equals_the_brief_version_blockquote():
    assert wording.BRIEF_DISCLAIMER == _brief_section(DISCLAIMER_MD)


def test_editing_the_source_text_fails_the_comparison(tmp_path):
    edited = tmp_path / "DISCLAIMER.md"
    edited.write_text(DISCLAIMER_MD.read_text(encoding="utf-8").replace("Figures can be wrong", "Figures may be wrong"))

    assert wording.BRIEF_DISCLAIMER != _brief_section(edited)


def test_the_copy_says_about_2_weeks_in_3():
    assert "About 2 weeks in 3" in wording.BRIEF_DISCLAIMER


def test_the_real_model_serves_the_coverage_the_copy_names(monkeypatch):
    if not REAL_MODEL.exists():
        pytest.skip("the trained model artifact is absent from this checkout: nothing to compare the copy with")
    monkeypatch.setattr(vol_mod, "MODEL_PATH", REAL_MODEL)
    model = vol_mod.load_model()

    assert model is not None
    if "About 2 weeks in 3" in wording.BRIEF_DISCLAIMER:
        assert coverage_phrase(model.range_coverage) == "about 2 in 3"
    assert wording.disclaimer_for(model.range_coverage) == wording.BRIEF_DISCLAIMER


def test_a_model_at_another_coverage_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(vol_mod, "MODEL_PATH", write_artifact(tmp_path / "m.json", range_coverage=0.80))
    model = vol_mod.load_model()

    with pytest.raises(wording.DisclaimerCoverageMismatch, match="0.8"):
        wording.disclaimer_for(model.range_coverage)


def test_disclaimer_for_080_raises():
    with pytest.raises(wording.DisclaimerCoverageMismatch):
        wording.disclaimer_for(0.80)
