"""`paperpulse run --format json` and `paperpulse export` end to end, against
a synthetic offline batch (same pattern as tests/test_diff.py)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import paperpulse.pipeline as pipeline_mod
from paperpulse.cli import build_parser
from paperpulse.models import Paper

_PAPER = Paper(
    id="2401.00001",
    title="A Study of Momentum",
    abstract="We study momentum strategies applied to international equity markets.",
    authors=["A. Researcher"],
    url="https://arxiv.org/abs/2401.00001",
)


def _run_with(batch, argv, tmp):
    original = pipeline_mod._fetch
    pipeline_mod._fetch = lambda cfg: batch
    parser = build_parser()
    args = parser.parse_args(["-c", str(Path(tmp) / "paperpulse.yaml")] + argv)
    try:
        return args.func(args)
    finally:
        pipeline_mod._fetch = original


def _config_file(tmp) -> Path:
    from paperpulse.config import Config

    path = Path(tmp) / "paperpulse.yaml"
    Config(
        embedding_backend="hashing",
        interests="equity factor research",
        state_path=str(Path(tmp) / "state.json"),
        output_dir=str(Path(tmp) / "digests"),
        min_score=-10.0,
        contradictions=False,
    ).save(path)
    return path


def test_run_format_json_prints_parseable_digest(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        _config_file(tmp)
        code = _run_with(
            [_PAPER], ["run", "--format", "json", "--dry-run"], tmp
        )
        assert code == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["papers"][0]["id"] == "2401.00001"
        assert data["papers"][0]["title"] == "A Study of Momentum"
        assert "contradictions" in data


def test_export_writes_bibtex_to_file(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        _config_file(tmp)
        bib_path = Path(tmp) / "out.bib"
        code = _run_with(
            [_PAPER], ["export", "--quiet", "-o", str(bib_path)], tmp
        )
        assert code == 0
        content = bib_path.read_text(encoding="utf-8")
        assert "@misc{researcher" in content
        assert "eprint = {2401.00001}," in content
