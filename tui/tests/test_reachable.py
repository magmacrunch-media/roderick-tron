"""Is every level still finishable with the verbs a terminal has?

This is the fairness test for the two rules the port changed. ``test_oracle.py``
holds the shared physics to the browser frame by frame, but it deliberately
runs both sides under conditions where the fixed-height jump and the earned
run agree -- so on its own it says nothing about whether *losing* those verbs
cost the player anything.

``reachability.py`` answers that. It searches the surface graph with the
terminal's smaller move vocabulary: no short hop, because that is a key
release, and no instantly-selectable run, because speed has to be earned by
travelling. If the exit and every pickup are still reachable, the reduction
cost nothing.

The strongest check here is the last one, which compares that verdict against
the browser's own search over its *larger* move set. Two independent searches
with different vocabularies agreeing on which surfaces are reachable is a much
better guarantee than pinning today's numbers as literals, which would go
stale the first time a level was edited.
"""

from __future__ import annotations

import pytest
from reachability import Env, analyse

from tron.levels import LEVELS

NAMES = [level["name"] for level in LEVELS]


@pytest.fixture(scope="module", params=range(len(LEVELS)), ids=NAMES)
def report(request):
    env = Env.build(LEVELS[request.param])
    return env, analyse(env)


def test_the_spawn_lands_on_a_real_surface(report):
    """A spawn drawn a little above its rooftop should not be its own island."""
    env, r = report
    assert r.start >= 0, f"{env.map.name}: the spawn settles on nothing"


def test_the_exit_is_reachable_from_the_spawn(report):
    env, r = report
    assert r.exit_reached, (
        f"{env.map.name}: the exit cannot be reached — "
        f"{len(r.reached)} of {len(r.surfaces)} surfaces are"
    )


def test_every_note_and_letter_is_reachable(report):
    """A letter you cannot get to is as much a bug as an exit you cannot."""
    env, r = report
    assert not r.unreachable_pickups, (
        f"{env.map.name}: {len(r.unreachable_pickups)} out of reach — "
        + "; ".join(r.unreachable_pickups[:6])
    )


def test_every_trolley_run_can_be_survived(report):
    """A ride that only ever ends in a hole is a level you cannot finish."""
    env, r = report
    assert r.survivable_rides, f"{env.map.name}: a trolley ride cannot be survived"


def test_the_search_actually_explored_something(report):
    """Guards the guard.

    If the search silently found nothing to try — a surface list that came back
    empty, a spawn that never settled — every assertion above would pass
    vacuously.
    """
    env, r = report
    assert len(r.surfaces) >= 4, f"{env.map.name}: only {len(r.surfaces)} surfaces"
    assert len(r.reached) >= 4, f"{env.map.name}: only {len(r.reached)} reached"
    assert r.edges, f"{env.map.name}: no connections between surfaces"


# ── Against the browser's own verdict ───────────────────────────────


def test_the_reduced_move_set_reaches_everything_the_browser_does(trace):
    """Losing the short hop and the SHIFT modifier cost no reachability.

    The browser searches with a strictly larger vocabulary: it can release the
    jump key early for a short hop, and it can select a run at any instant. The
    terminal has neither. If its search still reaches every surface the
    browser's does, the reduction is free — and if a future level ever needs a
    clipped jump to get somewhere, this is what says so.
    """
    worse = []
    for index, level in enumerate(LEVELS):
        env = Env.build(level)
        mine = analyse(env)
        theirs = trace["levels"][index]["reach"]

        assert len(mine.surfaces) == len(theirs["surfaces"]), (
            f"{env.map.name}: the two searches disagree on the surface graph "
            f"itself — {len(mine.surfaces)} here vs {len(theirs['surfaces'])}"
        )
        missing = set(theirs["reached"]) - mine.reached
        if missing:
            worse.append((env.map.name, sorted(missing)))
        assert mine.exit_reached == theirs["exitReached"], env.map.name
        assert not set(mine.unreachable_pickups) - set(theirs["unreachablePickups"]), (
            f"{env.map.name}: pickups the browser can collect and this cannot"
        )
    assert not worse, f"surfaces the browser reaches and the terminal cannot: {worse}"


def test_the_two_searches_agree_on_the_surface_graph(trace):
    """Not just the counts: the same rows and spans, in the same order.

    find_surfaces is small enough to look obviously right and subtle enough to
    be wrong at the edges — the ``above != SOLID`` headroom rule, and whether
    rail counts as standable.
    """
    for index, level in enumerate(LEVELS):
        env = Env.build(level)
        theirs = trace["levels"][index]["reach"]["surfaces"]
        mine = [[s.ty, s.tx0, s.tx1] for s in env.surfaces]
        assert mine == theirs, f"{env.map.name}: surface graphs differ"
