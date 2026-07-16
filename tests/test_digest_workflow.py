"""Regression coverage for the scheduled digest workflow."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_digest_workflow_installs_semantic_extra_for_its_configured_backend() -> None:
    """The scheduled config selects sentence-transformers, an optional extra."""
    config = yaml.safe_load((ROOT / "paperpulse.yaml").read_text(encoding="utf-8"))
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "digest.yml").read_text(encoding="utf-8")
    )

    assert config["embedding_backend"] == "sentence-transformers"
    install_step = next(step for step in workflow["jobs"]["digest"]["steps"] if "run" in step)
    assert ".[semantic]" in install_step["run"]
