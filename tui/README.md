# Roderick Tron — terminal version

The second version, alongside `web/` (browser). Runs on the
[magmacrunch.engine](https://pypi.org/project/magmacrunch/) terminal backend.

A clockwork gentleman crossing the rooftops of an 1810s Dutch city: three
hand-authored levels, a roll that carries further than a run, a chimney
draught, a bell cannon and a coal trolley.

```
pip install magmacrunch-roderick-tron
roderick-tron
```

It also appears in the arcade menu automatically — `pip install magmacrunch`
brings it along with every other cabinet.

## The screen

Sixty columns, which is the widest floor of any cabinet in the arcade and is
not arbitrary: the browser's viewport is thirty tiles, a tile is drawn two
cells wide so that it comes out square at a terminal's aspect, and thirty times
two is sixty. Below that the camera would show less of the level than the
browser does, and the levels were authored against what the browser shows — a
gap you cannot see the far side of is a leap of faith rather than a jump.

## Controls

| | |
|---|---|
| `←` `→` | walk; hold to build speed |
| `Space` `W` `↑` | jump |
| `X` | roll |
| `Z` | fire a note |
| `P` | pause |
| `R` | restart the level |
| `Esc` | back to the title |

Two verbs from the browser are missing, and both because a terminal reports
key presses and never releases. There is no variable jump height, and the run
is earned by travelling rather than selected with `Shift`. Neither costs any
level its solution — `tests/test_reachable.py` searches all three with the
smaller move set and agrees with the browser's own search, surface for surface.

## Tests

```
pip install -e ".[dev]"
python -m pytest -q
```

Most of it needs nothing but pytest: `tron/` imports no engine, and
`test_physics.py` proves it in a subprocess. Two suites want `node` as well,
and skip themselves without it — `test_oracle.py` runs the shipped browser
modules in a vm and compares the port frame by frame, and
`test_reachable.py` compares the two level searches. CI makes a skip fatal.

The level art in `tron/levels.py` is generated from `web/js/levels.js` by
`tools/gen_levels.py` and checked in CI, so the two versions cannot drift.
