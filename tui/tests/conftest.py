"""Shared fixtures.

Both the oracle and the reachability suite want the browser's own answers, and
generating them twice would double the node runs for no benefit. The trace is
regenerated once per session rather than committed, so it cannot go stale
against a web build that has moved on.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

TUI = Path(__file__).resolve().parents[1]
ORACLE = TUI / "tools" / "js_oracle.mjs"
WEB = TUI.parent / "web"


def node_available() -> bool:
    return shutil.which("node") is not None and (WEB / "js").exists()


@pytest.fixture(scope="session")
def trace(tmp_path_factory):
    """Everything the browser did, as JSON. Skips when node or web/ is absent.

    web/ is absent from an installed wheel, which is the case that matters:
    these tests are a development guarantee, not something a player's machine
    should have to satisfy.
    """
    if not node_available():
        pytest.skip("needs node and web/js (absent from an installed wheel)")
    out = tmp_path_factory.mktemp("oracle") / "oracle.json"
    proc = subprocess.run(
        [shutil.which("node"), str(ORACLE), str(out)],
        capture_output=True,
        text=True,
        cwd=TUI,
    )
    if proc.returncode != 0:
        pytest.fail(f"js_oracle.mjs failed:\n{proc.stderr}")
    return json.loads(out.read_text(encoding="utf-8"))
