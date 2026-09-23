"""Run the browser-native match-batch scoring tests under pytest."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


HERE = Path(__file__).resolve().parent


def test_match_score_node_suite() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    result = subprocess.run(
        [node, "--test", str(HERE / "test_match_score.mjs")],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout
