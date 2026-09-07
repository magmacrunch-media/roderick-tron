"""Can this level still be played, with the verbs a terminal has?

A port of ``web/tests/reachability.js``. Not named ``test_*`` on purpose:
pytest collects those, and this is a library. ``test_reachable.py`` is the
suite.

── Why a search and not a bot ──

The web build's notes explain this and it applies here twice over: a scripted
bot proves level 1 finishable and goes on proving it forever, because level 1
is a straight line along the ground. Give it a level that goes upward, or one
where the route doubles back, and it fails -- not because the level is broken
but because the bot only knows one shape.

So this searches. It builds the graph of standable surfaces, works out which
connect to which by flying the real :class:`~tron.player.Player` between them,
and asks whether the exit is in the component containing the spawn.

── What changed in the port, and why this file matters ──

The web search plans a jump as ``{speed, hold}`` -- how fast, and how many
frames to hold the button. Neither survives a terminal:

``hold`` is ``JUMP_CUT``, which reads a key release. Every jump here is full
height, so the web's "short hop" plan simply does not exist. The move set is
strictly smaller than the one the levels were authored against, and this is
the file that answers whether that cost anything.

``speed`` was the SHIFT modifier, chosen freely at any moment. Here it is
earned: holding a direction ramps the cap over ``RUN_CHARGE_FRAMES``. So a
plan cannot ask to run -- it can only ask for a longer run-up and see what
speed that buys. That is modelled honestly rather than by pinning the cap,
because pinning it would test a game nobody can play.

Enemies are ignored, as in the web build. Reachability is a question about
geometry; whether a gargoyle is in the way is a question about difficulty, and
the two should not fail together.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from tron import config as C
from tron.entities import Entities
from tron.player import Intent, Player
from tron.tilemap import Tilemap

SOLID = "#"
PLATFORM = "="
RAIL = "-"


@dataclass
class _Rect:
    """A bare box, for the overlap checks that have no Box to hand."""

    x: float
    y: float
    w: float
    h: float


def _rect(x: float, y: float, w: float, h: float) -> _Rect:
    return _Rect(x, y, w, h)


@dataclass
class Surface:
    """A horizontally contiguous run of standable tile-tops.

    ``ty`` is the row of the *surface*, not of the tile beneath it, so a body
    standing on it has its feet at ``ty * TILE``.
    """

    ty: int
    tx0: int
    tx1: int
    id: int = -1


@dataclass
class Plan:
    """One thing a player could try from a launch point.

    ``run_up`` is frames of held direction before the jump, and is the only
    way to ask for speed -- see the module docstring. ``ride`` is frames of no
    horizontal input first, which is how a chimney draught is taken.
    """

    dir: int
    run_up: int
    roll: bool = False
    jump: bool = True
    ride: int = 0


@dataclass
class Outcome:
    to: int = -1
    hit_exit: bool = False
    fell: bool = False
    touched: set[int] = field(default_factory=set)
    bell: int = -1
    trolley: int = -1
    crashed: bool = False


@dataclass
class Env:
    map: Tilemap
    surfaces: list[Surface]
    pickups: list[tuple[object, str]]

    @classmethod
    def build(cls, level: dict) -> Env:
        m = Tilemap(level)
        pickups: list[tuple[object, str]] = [
            (letter, f"letter {letter.ch} at tile "
                     f"{round(letter.x / C.TILE)},{round(letter.y / C.TILE)}")
            for letter in m.letters
        ] + [
            (n, f"note at tile {round(n.x / C.TILE)},{round(n.y / C.TILE)}")
            for n in m.notes
        ]
        return cls(m, find_surfaces(m), pickups)


def find_surfaces(m: Tilemap) -> list[Surface]:
    out: list[Surface] = []
    for ty in range(m.rows):
        run: Surface | None = None
        for tx in range(m.cols):
            here = m.tile_at(tx, ty)
            above = m.tile_at(tx, ty - 1)
            # Standable if this tile is footing and there is room to stand.
            # Rail counts: you can walk a rail as well as ride it.
            standable = here in (SOLID, PLATFORM, RAIL) and above != SOLID
            if standable:
                if run is not None:
                    run.tx1 = tx
                else:
                    run = Surface(ty, tx, tx)
                    out.append(run)
            else:
                run = None
    for i, s in enumerate(out):
        s.id = i
    return out


def surface_under(surfaces: list[Surface], box) -> int:
    """Which surface is this box standing on, or -1."""
    feet = box.y + box.h
    for s in surfaces:
        if abs(feet - s.ty * C.TILE) > 1.5:
            continue
        if box.x + box.w > s.tx0 * C.TILE and box.x < (s.tx1 + 1) * C.TILE:
            return s.id
    return -1


def overlaps(box, r) -> bool:
    return (
        box.x < r.x + r.w
        and box.x + box.w > r.x
        and box.y < r.y + r.h
        and box.y + box.h > r.y
    )


def _sweep(env: Env, box, touched: set[int]) -> None:
    """Pickups are swept, not stood next to.

    The letter over the roll gap is taken in mid-air, and only flying the arc
    can show that -- an earlier web version asked whether a pickup lay within a
    jump's apex of a reachable surface, which is a decent guess on flat ground
    and wrong everywhere interesting.
    """
    for k, (item, _) in enumerate(env.pickups):
        if k not in touched and overlaps(box, item):
            touched.add(k)


def attempt(env: Env, start_x: float, start_ty: int, plan: Plan) -> Outcome:
    """Fly one attempt with the real physics and report where it ends up."""
    m = env.map
    p = Player(m)
    p.box.x = start_x
    p.box.y = start_ty * C.TILE - p.box.h
    p.vx = p.vy = 0.0
    p.grounded = True
    p.coyote = C.COYOTE_FRAMES

    frm = surface_under(env.surfaces, p.box)
    out = Outcome()
    rolled = False
    jumped = False

    for i in range(200):
        steering = plan.dir if i >= plan.ride else 0
        intent = Intent(left=steering < 0, right=steering > 0)

        if plan.roll and not rolled and i >= plan.run_up - 12 and p.grounded:
            intent.roll = True
            rolled = True
        if plan.jump and not jumped and i >= plan.run_up:
            intent.jump = True
            jumped = True

        p.update(intent, 1.0)

        if m.exit is not None and overlaps(p.box, m.exit):
            out.hit_exit = True

        for k, t in enumerate(m.trolleys):
            if overlaps(p.box, _rect(t.x, t.y, C.TROLLEY_W, C.TROLLEY_H)):
                out.trolley = k
                return out
        # A bell ends the attempt: it catches you, and where you go next is a
        # question about the bell rather than about this jump.
        for k, b in enumerate(m.bells):
            if overlaps(p.box, _rect(b.x, b.y, C.BELL_W, C.BELL_H)):
                out.bell = k
                return out

        _sweep(env, p.box, out.touched)

        if p.box.y > m.h + C.FALL_KILL_MARGIN:
            out.fell = True
            return out

        if p.grounded and i > plan.run_up + 2:
            to = surface_under(env.surfaces, p.box)
            if to >= 0 and (to != frm or i > plan.run_up + 20):
                out.to = to
                return out

    out.to = surface_under(env.surfaces, p.box)
    return out


def fire(env: Env, bell_index: int, angle: float) -> Outcome:
    """Fly out of a bell at one angle.

    The bell's aim sweeps, so the player chooses the angle by choosing when to
    press. Sampling the whole arc is the honest question: is there ANY moment
    at which firing gets you somewhere useful?
    """
    m = env.map
    b = m.bells[bell_index]
    p = Player(m)
    p.box.x = b.x + (C.BELL_W - p.box.w) / 2
    p.box.y = b.y + (C.BELL_H - p.box.h) / 2
    p.launch(angle)

    # Held forward, as a player steering the arc would.
    steer = 1 if p.vx >= 0 else -1
    intent = Intent(left=steer < 0, right=steer > 0)

    out = Outcome()
    for i in range(260):
        p.update(intent, 1.0)
        if m.exit is not None and overlaps(p.box, m.exit):
            out.hit_exit = True
        _sweep(env, p.box, out.touched)
        if p.box.y > m.h + C.FALL_KILL_MARGIN:
            out.fell = True
            return out
        if p.grounded and i > 3:
            out.to = surface_under(env.surfaces, p.box)
            return out
    return out


def ride(env: Env, trolley_index: int, lookahead: int) -> Outcome:
    """Ride a trolley to wherever it ends up, under one jump policy.

    The real :class:`~tron.entities.Entities` drives it, so this is the
    shipped trolley rather than a model of one. ``lookahead`` is the whole
    policy: jump when the rail runs out within that many pixels. Sweeping it
    from 0 upward sweeps the jump from as late as possible to as early as
    possible, and for a cart at constant speed the timing of each jump is the
    only degree of freedom there is.
    """
    m = env.map
    p = Player(m)
    ents = Entities(m)
    t0 = m.trolleys[trolley_index]

    # Put him on the trolley by standing him in it.
    p.box.x = t0.x + (C.TROLLEY_W - p.box.w) / 2
    p.box.y = t0.y - p.box.h
    p.grounded = True

    out = Outcome()
    for i in range(900):
        t = ents.trolleys[trolley_index]
        want_jump = False
        if t is not None and t.riding and t.grounded:
            # Distance to the first missing footing ahead -- the hole, not the
            # track. Scanning for track instead finds it under the wheels at
            # distance zero and jumps every single frame.
            gap_at = lookahead + 8
            for d in range(0, lookahead + 1, 2):
                probe = t.x + t.w + d
                footing = m.overlaps_rail(probe, t.y + t.h, 2, 4) or m.overlaps_solid(
                    probe, t.y + t.h, 2, 4
                )
                if not footing:
                    gap_at = d
                    break
            want_jump = gap_at <= lookahead

        intent = Intent(jump=want_jump)
        p.update(intent, 1.0)
        ents.update(p, intent, 1.0)
        for ev in ents.events:
            if ev["type"] == "crash":
                out.crashed = True

        if m.exit is not None and overlaps(p.box, m.exit):
            out.hit_exit = True
        _sweep(env, p.box, out.touched)

        if p.box.y > m.h + C.FALL_KILL_MARGIN:
            out.fell = True
            return out
        if p.riding is None and p.grounded and i > 5:
            out.to = surface_under(env.surfaces, p.box)
            return out
    return out


def swing_angles(n: int) -> list[float]:
    """Angles the swing actually passes through, sampled evenly."""
    frm = math.radians(C.BELL_SWING_FROM)
    to = math.radians(C.BELL_SWING_TO)
    return [frm + (to - frm) * (i / (n - 1)) for i in range(n)]


def plans(direction: int, run_up: int) -> list[Plan]:
    """The moves worth trying from a launch point.

    Deliberately small: every extra technique multiplies the search. Note what
    is *not* here. The web build offers ``hold: 5`` -- a short hop, made by
    releasing the jump key early -- and the terminal cannot express it. The
    two "speeds" it offers are gone too, replaced by the run-up itself.
    """
    return [
        Plan(direction, run_up, jump=False),               # step off the edge
        Plan(direction, run_up),                           # jump
        Plan(direction, run_up, roll=True),                # roll-jump
        # Ride a draught up, then steer off the top. Two ride lengths: a short
        # column and a tall one.
        Plan(direction, run_up, jump=False, ride=45),
        Plan(direction, run_up, jump=False, ride=90),
    ]


@dataclass
class Report:
    start: int
    reached: set[int]
    exit_reached: bool
    surfaces: list[Surface]
    edges: list[tuple]
    unreachable_pickups: list[str]
    survivable_rides: bool = True


def analyse(env: Env) -> Report:
    """Search outward from the spawn."""
    m = env.map
    surfaces = env.surfaces

    # Where the spawn settles. A spawn drawn a little above its rooftop should
    # not count as its own island.
    p = Player(m)
    p.box.x, p.box.y = m.spawn.x, m.spawn.y
    p.vx = p.vy = 0.0
    p.grounded = False
    for _ in range(200):
        if p.grounded:
            break
        p.update(Intent(), 1.0)
    start = surface_under(surfaces, p.box)

    reached: set[int] = set()
    collected: set[int] = set()
    edges: list[tuple] = []
    exit_reached = False
    survivable = True
    if start < 0:
        return Report(start, reached, False, surfaces, edges, [])

    reached.add(start)
    queue = [start]
    bells_seen: set[int] = set()
    trolleys_seen: set[int] = set()
    angles = swing_angles(13)

    def expand_trolley(k: int) -> None:
        nonlocal exit_reached, survivable
        if k in trolleys_seen:
            return
        trolleys_seen.add(k)
        any_survived = False
        for look in range(0, 71, 5):
            r = ride(env, k, look)
            if r.fell:
                continue
            any_survived = True
            if r.hit_exit:
                exit_reached = True
            collected.update(r.touched)
            if r.to >= 0 and r.to not in reached:
                reached.add(r.to)
                edges.append((f"trolley{k}", r.to))
                queue.append(r.to)
        if not any_survived:
            survivable = False

    def expand_bell(k: int) -> None:
        nonlocal exit_reached
        if k in bells_seen:
            return
        bells_seen.add(k)
        for angle in angles:
            r = fire(env, k, angle)
            if r.hit_exit:
                exit_reached = True
            if not r.fell:
                collected.update(r.touched)
            if r.to >= 0 and r.to not in reached:
                reached.add(r.to)
                edges.append((f"bell{k}", r.to))
                queue.append(r.to)

    while queue:
        sid = queue.pop(0)
        s = surfaces[sid]

        # Launch from both ends and a few points between: where you leave a
        # rooftop from changes what you can reach off it.
        points = {s.tx0, s.tx1}
        points.update(range(s.tx0, s.tx1 + 1, 3))

        for tx in sorted(points):
            for direction in (1, -1):
                # Run-up is capped by how much of the surface lies behind you.
                room = (tx - s.tx0) if direction > 0 else (s.tx1 - tx)
                # Three lengths rather than the web's two: nothing, a short
                # one, and long enough for the earned-speed ramp to fill. The
                # last is what replaces the SHIFT modifier, so leaving it out
                # would test a game with no run at all.
                lengths = {
                    0,
                    min(24, room * 6),
                    min(C.RUN_CHARGE_FRAMES + 16, room * 8),
                }
                for run_up in lengths:
                    for plan in plans(direction, int(run_up)):
                        r = attempt(env, tx * C.TILE, s.ty, plan)
                        if r.hit_exit:
                            exit_reached = True
                        # Only a survived attempt counts. Grabbing a letter on
                        # the way into a pit is not a way of getting it.
                        if not r.fell:
                            collected.update(r.touched)
                        if r.bell >= 0:
                            edges.append((sid, f"bell{r.bell}"))
                            expand_bell(r.bell)
                        if r.trolley >= 0:
                            edges.append((sid, f"trolley{r.trolley}"))
                            expand_trolley(r.trolley)
                        if r.to >= 0 and r.to not in reached:
                            reached.add(r.to)
                            edges.append((sid, r.to))
                            queue.append(r.to)

    unreachable = [
        label for k, (_, label) in enumerate(env.pickups) if k not in collected
    ]
    return Report(
        start, reached, exit_reached, surfaces, edges, unreachable, survivable
    )


