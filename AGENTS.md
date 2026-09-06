# AGENTS.md — Roderick Tron

A side-scrolling platformer. One repo, every version of the game; today that is
just the browser build in `web/`.

## Commit identity

Commit and push as `magmacrunchmedia <magmacrunchmedia@gmail.com>`. The
conditional include in `~/.gitconfig` already handles this for anything under
`C:\magma\dev\magmacrunch\`; do not set `user.email` locally.

**No AI attribution.** Do not append `Co-Authored-By:`, "Generated with …", or
any similar trailer to a commit message, PR body or release note. These are
Jake's own published projects under his own name.

## The browser build is not standalone

`web/index.html` refers to `../shared/` for the adenosine bundles and
`../../music/jukebox/songs/` for the music, so opening it from this repo gets a
page with no engine and no track. It is meant to be copied into
magmacrunch.com's `arcade/roderick-tron/`, which is what `make
sync-roderick-tron` does over there.

That means **the website's `arcade/roderick-tron/` is generated**. Editing it
there is pointless: the sync deletes the folder and recopies it. Edit `web/`
here, run the target there, commit both.

The tests have no such dependency:

```
node web/tests/test-simulation.js
```

## What the tests actually guarantee

Read `web/tests/reachability.js` before changing any level or any physics
constant. For every level it proves, with the real `Player.update`, that the
exit is reachable, that every note and letter can be collected on a run the
player survives, and that every trolley run can be survived.

It has caught: shelves placed higher than a jump reaches, a chimney draught
whose lift was weaker than gravity, a platform a resting body sank through, and
a gap wider than any technique could cross.

Two things about it are worth keeping in mind:

- **Bells are exhaustive; trolley rides are a sweep.** Firing a bell samples the
  whole swing, so that is a proof. A trolley ride is simulated under a sweep of
  jump timings and passes if any survives — for a cart at constant speed the
  timing is the only degree of freedom, so the sweep covers it, but it is not a
  search over every frame. That distinction is written into the file; keep it
  written down rather than letting the comment drift into claiming more.
- **Every new set piece has to be taught to the search.** A device the search
  does not understand makes the levels using it look unreachable, and the
  tempting fix — relaxing the assertion — silently ends the guarantee. Bells and
  trolleys are graph nodes; the draught needed no physics case but did need the
  search to learn to let go of the stick and ride.

## The numbers the levels are designed against

| | |
|---|---|
| Jump height | 52px, three tiles |
| Running jump | four tiles |
| Roll-jump | seven tiles |
| Bell cannon | about fourteen tiles at its best angle |
| Chimney draught | the only way past three tiles of height |

Changing `GRAVITY`, `JUMP_FORCE`, `ROLL_MAX` or `BELL_LAUNCH` changes what every
existing level demands. The suite will tell you; run it.

`UPDRAFT_LIFT` must exceed `GRAVITY`, or a draught pushes down. It shipped once
at 0.42 against a gravity of 0.44 and lifted nobody.

## Levels are ASCII on purpose

Editable, reviewable, and they diff line by line. The legend is at the top of
`js/levels.js`. Rows shorter than the widest are padded, so trailing air can be
trimmed without shifting anything.

## Frame-rate independence

Every per-frame quantity is multiplied by `dt`, which is 1.0 at 60fps. The
runner this game grew out of applied `dt` to gravity but not to the position
step and ran at double speed on a 120Hz display. There are assertions at 60,
120 and 30fps, including an explicit speed-cap check — the failure there was
unbounded speed rather than drift, and a tolerance test would not have caught
it.
