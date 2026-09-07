"""Enemies, pickups and the two set pieces.

Split from ``test_physics.py`` because the concerns are different: that file
pins the numbers the levels are designed against, this one pins behaviour that
would otherwise only be discovered by playing.

The smoke test comes first on purpose. Everything else here places a body next
to a specific thing and checks one interaction, which is precise but proves
nothing about the code paths a real run takes; six hundred frames of every
level is what catches an exception in a branch nobody aimed at.
"""

from __future__ import annotations

import math
import random

import pytest

from tron import config as C
from tron.entities import Entities
from tron.levels import LEVELS
from tron.player import Intent, Player
from tron.tilemap import Tilemap


def level(i=0):
    m = Tilemap(LEVELS[i])
    p = Player(m)
    e = Entities(m, random.Random(7))
    return m, p, e


def step(p, e, intent=None, frames=1, dt=1.0):
    intent = intent or Intent()
    for _ in range(frames):
        p.update(intent, dt)
        e.update(p, intent, dt)


# ── Smoke ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("index", range(len(LEVELS)))
def test_a_long_run_of_every_level_raises_nothing(index):
    """Six hundred frames of walking right, which is most of a level."""
    m, p, e = level(index)
    step(p, e, Intent(right=True), frames=600)
    assert p.box.x >= m.spawn.x - 1
    # Nothing should have leaked: shots expire, particles expire.
    assert len(e.particles) < 400
    assert all(s.life > 0 for s in e.shots)


@pytest.mark.parametrize("index", range(len(LEVELS)))
def test_an_idle_run_leaves_the_player_where_he_spawned(index):
    """Enemies move; a player pressing nothing does not wander."""
    _, p, e = level(index)
    x0 = p.box.x
    step(p, e, frames=120)
    assert p.box.x == pytest.approx(x0, abs=1.0)


# ── Enemies ─────────────────────────────────────────────────────────


def test_gargoyles_stay_on_their_own_rooftop():
    """They turn at a ledge, which is what the footing probe is for.

    Without it they march off within seconds of the level starting, and a
    level's enemies are all in the pit before the player reaches them.
    """
    m, p, e = level(0)
    p.box.y = -999  # out of the way; this is about the gargoyles alone
    gargoyles = [g for g in e.enemies if g.kind == "gargoyle"]
    assert gargoyles, "level 1 should have gargoyles"
    for _ in range(1200):
        e.update_enemies(p, 1.0)
    for g in gargoyles:
        assert m.has_footing(g.x, g.y, g.w, g.h), f"a gargoyle walked off at {g.x}"


def test_a_note_fells_a_gargoyle():
    m, p, e = level(0)
    g = next(g for g in e.enemies if g.kind == "gargoyle")
    before = len(e.enemies)
    p.box.x, p.box.y = g.x - 40, g.y
    p.facing = 1
    e.fire(p)
    for _ in range(40):
        e.update_shots(1.0)
        if g.dead:
            break
    assert g.dead, "the note passed straight through"
    assert any(ev["type"] == "kill" for ev in e.events)
    # damage() only marks it; update_enemies is what removes it from the list.
    assert len(e.enemies) == before
    e.update_enemies(p, 1.0)
    assert len(e.enemies) == before - 1


def test_a_statue_shrugs_off_three_notes_and_falls_to_the_fourth():
    _, p, e = level(0)
    s = next(x for x in e.enemies if x.kind == "statue")
    assert s.hp == C.STATUE_HP
    for _ in range(C.STATUE_HP - 1):
        assert e.damage(s, 1) is False
    assert e.damage(s, 1) is True


def test_stomping_a_statue_bounces_without_killing_it():
    _, p, e = level(0)
    s = next(x for x in e.enemies if x.kind == "statue")
    p.box.x, p.box.y = s.x, s.y - p.box.h + 2  # overlapping, not merely flush
    p.vy = 3.0
    e.update_enemies(p, 1.0)
    assert p.vy == C.STOMP_BOUNCE, "should have bounced"
    assert not s.dead, "a statue is too heavy to flatten"


def test_stomping_a_gargoyle_kills_it_and_bounces():
    _, p, e = level(0)
    g = next(x for x in e.enemies if x.kind == "gargoyle")
    p.box.x, p.box.y = g.x, g.y - p.box.h + 2
    p.vy = 3.0
    e.update_enemies(p, 1.0)
    assert p.vy < 0, "no bounce off the stomp"
    assert any(ev["type"] == "kill" for ev in e.events)


def test_a_higher_bounce_is_available_by_pressing_jump_on_contact():
    """The terminal's stand-in for holding jump: the live jump buffer."""
    _, p, e = level(0)
    g = next(x for x in e.enemies if x.kind == "gargoyle")
    p.box.x, p.box.y = g.x, g.y - p.box.h + 2
    p.vy = 3.0
    p.jump_buffer = C.JUMP_BUFFER_FRAMES
    e.update_enemies(p, 1.0)
    assert p.vy == C.STOMP_BOUNCE_HELD


def test_a_roll_goes_through_anything_soft_but_not_a_statue():
    _, p, e = level(0)
    p.rolling = True
    g = next(x for x in e.enemies if x.kind == "gargoyle")
    p.box.x, p.box.y = g.x, g.y
    p.vy = 0.0
    e.update_enemies(p, 1.0)
    assert any(ev["type"] == "kill" for ev in e.events)

    _, p2, e2 = level(0)
    p2.rolling = True
    s = next(x for x in e2.enemies if x.kind == "statue")
    p2.box.x, p2.box.y = s.x, s.y
    p2.vy = 0.0
    e2.update_enemies(p2, 1.0)
    assert not s.dead, "a roll should not fell a statue"


def test_walking_into_an_enemy_hurts_rather_than_stomping_it():
    _, p, e = level(0)
    g = next(x for x in e.enemies if x.kind == "gargoyle")
    p.box.x, p.box.y = g.x - 2, g.y  # level with it, not above it
    p.vy = 0.0
    e.update_enemies(p, 1.0)
    assert any(ev["type"] == "hurt" for ev in e.events)


# ── Pickups ─────────────────────────────────────────────────────────


def test_a_note_is_collected_once():
    m, p, e = level(0)
    n = m.notes[0]
    p.box.x, p.box.y = n.x, n.y
    e.update_pickups(p)
    assert n.taken
    assert sum(1 for ev in e.events if ev["type"] == "note") == 1
    e.events.clear()
    e.update_pickups(p)
    assert not any(ev["type"] == "note" for ev in e.events), "collected twice"


def test_a_letter_reports_which_letter_it_was():
    m, p, e = level(0)
    letter = m.letters[0]
    p.box.x, p.box.y = letter.x, letter.y
    e.update_pickups(p)
    ev = next(ev for ev in e.events if ev["type"] == "letter")
    assert ev["ch"] in "TRON"


def test_reset_restores_the_pickups():
    m, p, e = level(0)
    for n in m.notes:
        n.taken = True
    e.reset()
    assert all(not n.taken for n in m.notes)


def test_a_hundred_notes_buys_a_life():
    _, p, _ = level(0)
    lives = p.lives
    bought = any(p.collect(1) for _ in range(C.NOTES_PER_LIFE))
    assert bought
    assert p.lives == lives + 1


def test_ammo_is_capped():
    _, p, _ = level(0)
    for _ in range(500):
        p.collect(1)
    assert p.ammo == C.NOTE_AMMO_MAX


# ── The set pieces ──────────────────────────────────────────────────


def test_boarding_a_trolley_makes_jump_the_only_verb():
    m, p, e = level(2)  # THE COAL RUN
    t = e.trolleys[0]
    p.box.x, p.box.y = t.x, t.y
    e.update_trolleys(p, Intent(), 1.0)
    assert p.riding is t
    assert any(ev["type"] == "board" for ev in e.events)

    # Steering is ignored while aboard: the player's own update returns early.
    x0 = p.box.x
    p.update(Intent(left=True), 1.0)
    assert p.box.x == x0
    assert p.vx == 0


def test_a_boarded_trolley_carries_him_along_the_rail():
    m, p, e = level(2)
    t = e.trolleys[0]
    p.box.x, p.box.y = t.x, t.y
    x0 = t.x
    for _ in range(120):
        p.update(Intent(), 1.0)
        e.update_trolleys(p, Intent(), 1.0)
    assert t.x > x0 + 100, "the trolley did not roll"
    if not t.spent:
        assert abs(p.box.x - (t.x + (t.w - p.box.w) / 2)) < 0.001


def test_a_bell_catches_him_and_fires_him_on_jump():
    m, p, e = level(1)  # THE BELFRY has the only bell
    b = e.bells[0]
    p.box.x, p.box.y = b.x, b.y
    e.update_bells(p, Intent(), 1.0)
    assert p.captured is b
    assert any(ev["type"] == "caught" for ev in e.events)

    e.update_bells(p, Intent(jump=True), 1.0)
    assert p.captured is None
    assert b.cooldown == C.BELL_RECAPTURE
    speed = (p.vx**2 + p.vy**2) ** 0.5
    assert speed == pytest.approx(C.BELL_LAUNCH, abs=1e-6)


def test_the_bell_swings_through_its_configured_arc():
    m, _, e = level(1)
    b = e.bells[0]
    seen = []
    for _ in range(600):
        e.update_bells(_dead_player(m), Intent(), 1.0)
        seen.append(b.angle)
    lo, hi = min(seen), max(seen)
    assert lo == pytest.approx(math.radians(C.BELL_SWING_FROM), abs=0.05)
    assert hi == pytest.approx(math.radians(C.BELL_SWING_TO), abs=0.05)


def _dead_player(m):
    p = Player(m)
    p.alive = False
    return p


def test_the_bird_trails_rather_than_tracks():
    m, p, e = level(0)
    p.box.x = 400
    e.update_bird(p, 1.0)
    assert e.bird is not None
    start = e.bird.x
    p.box.x = 800  # teleport him
    e.update_bird(p, 1.0)
    assert start < e.bird.x < 800, "the bird should lag, not snap"


def test_losing_the_bird_costs_no_life():
    _, p, _ = level(0)
    lives = p.lives
    assert p.hurt(p.box.x + 50) == "bird"
    assert p.lives == lives
    p.invincible = 0
    assert p.hurt(p.box.x + 50) == "life"
    assert p.lives == lives - 1


def test_invincibility_refuses_a_second_hit():
    _, p, _ = level(0)
    p.hurt(p.box.x + 50)
    assert p.hurt(p.box.x + 50) is None
