"""Regenerate ``tron/levels.py`` from ``web/js/levels.js``.

Run from anywhere:  python tools/gen_levels.py

The web build owns the level art. Transcribing sixty rows of it by hand is
exactly the kind of thing that looks right and is wrong by one character
somewhere in the middle, and a level that differs between the two versions is a
level whose reachability proof no longer transfers -- so it is lifted
mechanically and round-tripped before being written.

Writes LF explicitly. core.autocrlf is true in these repos and does not
normalise on the way in, so a CRLF .py stages as a whole-file rewrite that
buries the real change.
"""

from __future__ import annotations

import pathlib
import re

TUI = pathlib.Path(__file__).resolve().parent.parent
SOURCE = TUI.parent / "web" / "js" / "levels.js"
DEST = TUI / "tron" / "levels.py"

HEADER = '''"""The three levels, lifted verbatim from ``web/js/levels.js``.

Generated rather than retyped -- see ``tools/gen_levels.py``. The web build is
the source of truth for level art, and a level that differs by one character
between the two versions is a level whose reachability proof no longer
transfers.

Legend
  .  air                 #  solid brick
  =  one-way platform    ~  canal water (fatal)
  S  spawn               E  exit
  o  note (collect: ammo, points, and 100 is a life)
  T R O N  letters       g  gargoyle (walks, stompable)
  f  flyer (bobs)        s  statue (heavy: stomp bounces off, notes fell it)
  b  bell cannon         ^  chimney updraft (a column of rising air)
  -  rail                c  coal trolley (board it; then jump is the only verb)

A jump clears 3.7 tiles. Anything higher than that needs a draught or a bell,
and ``tests/test_physics.py`` is what proves the levels obey it.
"""

from __future__ import annotations

LEVELS: tuple[dict[str, object], ...] = (
'''


def main() -> int:
    with open(SOURCE, encoding="utf-8", newline="") as fh:
        src = fh.read()
    blocks = re.findall(
        r"name: '([^']+)',\s*subtitle: '([^']*)',\s*rows: \[(.*?)\],\s*\},",
        src,
        re.S,
    )
    if len(blocks) != 3:
        raise SystemExit(
            f"expected 3 levels, parsed {len(blocks)} -- has levels.js moved?"
        )

    out = [HEADER.rstrip("\n")]
    for name, subtitle, body in blocks:
        rows = re.findall(r"'([^']*)'", body)
        width = max(len(r) for r in rows)
        out.append("    {")
        out.append(f'        "name": "{name}",')
        out.append(f'        "subtitle": "{subtitle}",')
        out.append(f'        "rows": (  # {width} x {len(rows)} tiles')
        out.extend(f'            "{r}",' for r in rows)
        out.append("        ),")
        out.append("    },")
    out.append(")")
    out.append("")
    out.append('__all__ = ["LEVELS"]')
    out.append("")

    DEST.parent.mkdir(parents=True, exist_ok=True)
    with open(DEST, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))

    # Round-trip: parse what was just written and compare it back to the JS, so
    # a quoting slip cannot pass silently.
    ns: dict = {}
    exec(compile(DEST.read_bytes(), str(DEST), "exec"), ns)  # noqa: S102
    for (name, _, body), level in zip(blocks, ns["LEVELS"], strict=True):
        js_rows = re.findall(r"'([^']*)'", body)
        if level["name"] != name or list(level["rows"]) != js_rows:
            raise SystemExit(f"round-trip mismatch in {name}")
        cols = max(len(r) for r in js_rows)
        print(f"  {name:18} {len(js_rows)} rows x {cols} cols  OK")

    print(f"wrote {DEST.relative_to(TUI)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
