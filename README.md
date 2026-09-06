# Roderick Tron

A robot composer on the rooftops of an 1810s Dutch city. Run, roll, stomp and
fire musical notes; find T-R-O-N; get to the lit door.

One repo, every version of the game.

| Version | Folder | Engine | Where it runs |
|---------|--------|--------|---------------|
| Browser | [`web/`](web/) | [adenosine](https://github.com/magmacrunch-media/adenosine) | [magmacrunch.com/arcade/roderick-tron](https://magmacrunch.com/arcade/roderick-tron/) |

The browser build is the only version so far. This repository exists ahead of
the others so that when one arrives it has somewhere to live beside this one,
rather than being bolted on afterwards.

## Layout

```
web/            the browser game
  index.html    page, HUD, script order
  js/
    config.js   every constant, and the physics the levels are designed against
    levels.js   the levels, as ASCII
    tilemap.js  level parsing and collision
    player.js   momentum, roll, stomp, damage
    entities.js enemies, pickups, bells, trolleys, the companion
    world.js    camera, parallax, tile rendering
    sfx.js      synthesised sound
    main.js     loop, state machine, level lifecycle
  tests/        headless simulation tests (node tests/test-simulation.js)
```

## It was a runner

Until recently this was an endless auto-runner. It is now a hand-authored
side-scrolling platformer, in the Donkey Kong Country tradition: authored levels
with a beginning and an end, momentum in the movement, and set pieces.

That change was not incremental. An auto-runner's identity is that no two runs
are alike; a platformer's is that every placement is deliberate. Nothing
procedural puts a trail of notes over a gap so that following it teaches the
jump underneath — and that trail is how these levels explain themselves.

## Levels are ASCII

```
'..............................T.........=====...................'
'..................................ooo.................====......'
'....................ooo.........................................'
'..S.....o.o.o..............g.................g..................'
'####################...###########...################......#####'
```

Because ASCII is editable, reviewable, and diffs line by line. The legend is at
the top of `js/levels.js`.

The numbers the levels are designed against, all measured rather than assumed:

| | |
|---|---|
| Jump height | 52px, three tiles |
| Running jump | four tiles across |
| Roll-jump | seven tiles across |
| Bell cannon | about fourteen tiles, at its best angle |
| Chimney draught | the only way up past three tiles |

A shelf higher than a jump and a gap wider than a roll are both level bugs, and
the test suite is what catches them.

## The tests prove the levels, not just the code

`web/tests/test-simulation.js` loads the shipped files into a `vm` context and
runs them — nothing there reimplements game logic, because a test that did could
pass while the game was broken.

The part worth knowing about is `tests/reachability.js`. For every level it
finds each standable surface, flies the real `Player.update` between them across
a vocabulary of moves, rides every trolley, fires every bell at every angle its
swing reaches, and asks:

- can the exit be reached from the spawn?
- is every note and letter collectable, on a run the player survives?
- can every trolley run be survived?

It has already found things nobody would have: shelves placed higher than a jump
can reach, a chimney draught whose lift was *weaker than gravity*, and a
platform that a body resting on it slowly sank through.

An earlier version of that check was a scripted bot — hold right, jump at gaps —
which proved level 1 finishable and would have gone on proving it forever, while
quietly ceasing to apply to any level that climbed. A guarantee that lapses as
content grows is worse than none, because nobody notices.

## The browser build runs from inside the website

`web/index.html` refers to `../shared/` for the adenosine bundles and to
`../../music/jukebox/songs/` for the music, so it does not open standalone from
this repo. It is meant to be copied into
[magmacrunch.com](https://github.com/magmacrunch-media/magmacrunch.com)'s
`arcade/roderick-tron/`, which is what `make sync-roderick-tron` does over
there. This matches the other multi-version games.

The tests have no such dependency and run from anywhere:

```
node web/tests/test-simulation.js
```

## Controls

| | |
|---|---|
| ← → | walk |
| Shift | run |
| Space / ↑ | jump — hold for height |
| X | roll — and roll off a ledge, then jump, for the long gaps |
| Z | fire a note |
| M | music and effects on/off |

## Licence

PolyForm Noncommercial 1.0.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
