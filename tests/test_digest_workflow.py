"""Regression coverage for the scheduled digest workflow.

Only reads tracked files. An earlier version read `paperpulse.yaml`, which is
gitignored (.gitignore) -- so it passed on the author's machine and failed in
CI with FileNotFoundError. The scheduled run has no `paperpulse.yaml` either;
`paperpulse run` there falls back to config defaults.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_digest_workflow_installs_the_semantic_extra() -> None:
    """The daily digest wants real embeddings, so its install must pull the
    optional `semantic` extra -- guard against someone dropping it and silently
    downgrading the scheduled digest to the hashing fallback."""
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "digest.yml").read_text(encoding="utf-8")
    )
    runs = " ".join(
        step["run"] for step in workflow["jobs"]["digest"]["steps"] if "run" in step
    )
    assert ".[semantic]" in runs
