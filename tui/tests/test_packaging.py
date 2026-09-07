"""What the package says about itself.

Its own file, not a section of ``test_app.py``, because that suite opens with
``importorskip("textual")`` and this check needs nothing installed — the whole
point of a hand-kept literal is that it is readable from a bare checkout. CI's
no-engine job runs it, so it gates every push.

The other cabinets grew this file the same way and for the same reason: their
``__version__`` sat at 0.1.0 through four releases, because the release
workflow compares the git tag against pyproject and never looks at the module.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    """The packaging metadata, read from source.

    ``tomllib`` is 3.11; this package supports 3.10. Skipping there rather than
    taking a ``tomli`` dependency for one test is the cheaper trade — CI runs
    3.12, so the check still gates every push.
    """
    if sys.version_info < (3, 11):
        pytest.skip("tomllib is 3.11+")
    import tomllib

    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_version_is_the_one_the_package_declares():
    import tron

    assert tron.__version__ == _pyproject()["project"]["version"]


def test_the_engine_pin_is_high_enough_for_the_glyphs_it_uses():
    """0.7.1, not 0.7.0.

    0.7.0 shipped the glyph fallback without the box-drawing set. This cabinet
    leans on that table harder than any other — the playfield itself is drawn
    from block and box characters, sixty columns of it every frame — so a pin
    one release too low installs cleanly and then draws the game as mojibake on
    exactly the terminal the fallback exists for.
    """
    deps = _pyproject()["project"]["dependencies"]
    assert any(d.replace(" ", "") == "magmacrunch>=0.7.1" for d in deps), deps


def test_the_entry_point_names_something_that_exists():
    """An entry point is metadata nothing validates at install time, so a typo
    installs cleanly and only surfaces as a cabinet the arcade cannot load.

    Checked by reading the file rather than importing it, so this suite keeps
    its promise of needing no engine — importing ``tron.arcade`` would drag in
    ``magmacrunch.engine.arcade`` and pass locally while failing in CI's
    engine-free job.
    """
    entries = _pyproject()["project"]["entry-points"]["magmacrunch.games"]
    assert entries == {"roderick-tron": "tron.arcade:GAME"}

    module, _, attr = entries["roderick-tron"].partition(":")
    path = ROOT / (module.replace(".", "/") + ".py")
    assert path.exists(), f"{module} does not exist"
    assert f"\n{attr} = " in path.read_text(encoding="utf-8"), (
        f"{module} defines no {attr}"
    )


def test_the_command_names_something_that_exists():
    scripts = _pyproject()["project"]["scripts"]
    module, _, attr = scripts["roderick-tron"].partition(":")
    path = ROOT / (module.replace(".", "/") + ".py")
    assert path.exists(), f"{module} does not exist"
    assert f"def {attr}(" in path.read_text(encoding="utf-8")


def test_the_licence_travels_with_the_package():
    """PolyForm requires the notice to travel with the distribution.

    The licence lives at the repo root, where it also covers ``web/``; these
    are copies kept so that hatchling puts them in the wheel. The release
    workflow asserts they arrived, but a missing *source* file would fail that
    late and confusingly, so it is checked here too.
    """
    for name in ("LICENSE", "NOTICE"):
        assert (ROOT / name).exists(), f"tui/{name} is missing"
    assert _pyproject()["project"]["license"] == "PolyForm-Noncommercial-1.0.0"


def test_the_readme_exists_because_pyproject_promises_it():
    """A missing readme fails at build time, which is after the tag."""
    assert (ROOT / _pyproject()["project"]["readme"]).exists()
