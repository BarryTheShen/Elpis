"""Deployment safety checks for unsupported storage targets."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_firebase_deploy_refuses_unsafe_sqlite_target() -> None:
    firebase_config = json.loads((ROOT / "firebase.json").read_text())
    rewrites = firebase_config["hosting"]["rewrites"]
    assert not any(rule.get("source") == "/api/**" for rule in rewrites)
    result = subprocess.run(
        ["bash", "scripts/firebase-deploy.sh", "--skip-build"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "deployment is disabled" in result.stderr
    assert "SQLite WAL" in result.stderr
    assert "transactional managed database" in result.stderr
