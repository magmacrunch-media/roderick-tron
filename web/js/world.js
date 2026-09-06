// world.js — Roderick Tron | MagmaCrunch Media © 2026
// Camera, parallax backdrop, and drawing the tilemap.

/**
 * A camera that leads the player and ignores small movements.
 *
 * The dead zone is what stops every hop shoving the view around; the lookahead
 * is what buys reaction time at speed, by showing more of the direction being
 * travelled than the one behind.
 */
function Camera(map) {
    this.map = map;
    this.x = 0;
    this.y = 0;
}

Camera.prototype.snapTo = function (player) {
    this.x = player.box.x - CONFIG.CANVAS_W / 2;
    this.y = player.box.y - CONFIG.CANVAS_H / 2;
    this.clamp();
};

Camera.prototype.update = function (player, dt) {
    const px = player.box.x + player.box.w / 2 + player.facing * CONFIG.CAM_LOOKAHEAD;
    const py = player.box.y + player.box.h / 2;

    const wantX = px - CONFIG.CANVAS_W / 2;
    const wantY = py - CONFIG.CANVAS_H / 2;

    if (Math.abs(wantX - this.x) > CONFIG.CAM_DEADZONE_X) {
        const target = wantX - Math.sign(wantX - this.x) * CONFIG.CAM_DEADZONE_X;
        this.x += (target - this.x) * Math.min(1, CONFIG.CAM_LERP * dt);
    }
    if (Math.abs(wantY - this.y) > CONFIG.CAM_DEADZONE_Y) {
        const target = wantY - Math.sign(wantY - this.y) * CONFIG.CAM_DEADZONE_Y;
        this.y += (target - this.y) * Math.min(1, CONFIG.CAM_LERP * dt);
    }
    this.clamp();
};

/** Never show past the edges of the level. */
Camera.prototype.clamp = function () {
    this.x = Math.max(0, Math.min(this.map.w - CONFIG.CANVAS_W, this.x));
    this.y = Math.max(0, Math.min(this.map.h - CONFIG.CANVAS_H, this.y));
    if (this.map.w < CONFIG.CANVAS_W) this.x = 0;
    if (this.map.h < CONFIG.CANVAS_H) this.y = 0;
};

// ── World rendering ───────────────────────────────────────

function World(map) {
    this.map = map;
    this.tick = 0;      // drives the rising specks in an updraft
}

World.prototype.draw = function (ctx, cam) {
    this.tick++;
    this.drawSky(ctx);
    this.drawMoon(ctx, cam);
    this.drawFar(ctx, cam);
    this.drawMid(ctx, cam);
    this.drawHaze(ctx);
    this.drawTiles(ctx, cam);
    this.drawPickups(ctx, cam);
    this.drawExit(ctx, cam);
};

World.prototype.drawSky = function (ctx) {
    const C = CONFIG.COLORS;
    const g = ctx.createLinearGradient(0, 0, 0, CONFIG.CANVAS_H);
    g.addColorStop(0, C.sky);
    g.addColorStop(0.7, C.skyHorizon);
    g.addColorStop(1, C.canalBlue);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, CONFIG.CANVAS_W, CONFIG.CANVAS_H);
};

World.prototype.drawMoon = function (ctx, cam) {
    const mx = 372 - cam.x * 0.03;
    const my = 46 - cam.y * 0.05;
    Renderer.glow(ctx, mx, my, 30, '240,234,216', 0.10);
    ctx.fillStyle = CONFIG.COLORS.moonDisc;
    ctx.beginPath(); ctx.arc(mx, my, 13, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = CONFIG.COLORS.sky;
    ctx.beginPath(); ctx.arc(mx - 6, my - 4, 11, 0, Math.PI * 2); ctx.fill();
};

// Both backdrop layers are indexed by WORLD position, not by a slot on
// screen, and the loop covers the view rather than a fixed count.
//
// They used to walk ten and twelve buildings leftward from a modulo and never
// replenish on the right, so the whole row slid off the screen: past an offset
// of about 285 the mid layer left the right-hand side of the frame as bare sky
// and haze. At 96-tile levels that is the last 40% of every level. The far
// layer escaped only because its 0.18 factor never drove the offset high
// enough -- it would have gone the same way past roughly 124 tiles, which a
// longer level would have found.
//
// Anchoring to the world also gives a building a stable identity: its size and
// its lit windows follow it rather than following the slot it happens to
// occupy, so nothing about it changes as it crosses the screen.
const spanIndices = function (off, spacing, width) {
    const first = Math.floor(off / spacing) - 1;
    const last = Math.ceil((off + width) / spacing) + 1;
    return { first: first, last: last };
};

// A positive remainder. `i` is now a world index and goes negative to the left
// of the origin, where the % operator would hand back a negative and pick the
// wrong building out of the pattern.
const cycle = function (i, n) { return ((i % n) + n) % n; };

World.prototype.drawFar = function (ctx, cam) {
    const off = cam.x * 0.18;
    const base = CONFIG.CANVAS_H - 20 + cam.y * 0.06;
    const range = spanIndices(off, 90, CONFIG.CANVAS_W);
    ctx.fillStyle = CONFIG.COLORS.farBuilding;
    for (let i = range.first; i <= range.last; i++) {
        const bx = Math.round((i * 90) - off);
        const bw = 30 + cycle(i, 3) * 15;
        const bh = 40 + cycle(i, 4) * 20;
        ctx.fillRect(bx, base - bh, bw, bh);
        if (cycle(i, 3) === 0) {
            ctx.fillRect(bx + bw / 2 - 3, base - bh - 20, 6, 20);
            ctx.fillRect(bx + bw / 2 - 1, base - bh - 28, 2, 8);
        }
    }
    const wx = Math.round(200 - (off % 700));
    ctx.fillStyle = CONFIG.COLORS.farWindmill;
    ctx.fillRect(wx, base - 60, 8, 40);
    ctx.fillRect(wx - 15, base - 60, 38, 3);
    ctx.fillRect(wx + 3, base - 75, 3, 33);
};

World.prototype.drawMid = function (ctx, cam) {
    const off = cam.x * 0.45;
    const base = CONFIG.CANVAS_H - 10 + cam.y * 0.12;
    const range = spanIndices(off, 70, CONFIG.CANVAS_W);
    for (let i = range.first; i <= range.last; i++) {
        const bx = Math.round((i * 70) - off);
        const bw = 40 + cycle(i, 3) * 12;
        const bh = 50 + cycle(i, 4) * 15;
        const by = base - bh;

        ctx.fillStyle = CONFIG.COLORS.midBuilding;
        ctx.fillRect(bx, by, bw, bh);

        // Stepped gable (trapgevel) — a silhouette on this layer, where it can
        // never be mistaken for something to stand on.
        const tread = Math.max(3, Math.floor(bw / 8));
        for (let s = 0; s < 4; s++) {
            const w = bw - s * tread * 2;
            if (w <= 0) break;
            ctx.fillStyle = CONFIG.COLORS.midGable;
            ctx.fillRect(bx + s * tread, by - (s + 1) * 4, w, 5);
            ctx.fillStyle = CONFIG.COLORS.midGableLip;
            ctx.fillRect(bx + s * tread, by - (s + 1) * 4, w, 1);
        }
        for (let wy = 0; wy < 3; wy++) {
            for (let wx = 0; wx < 2; wx++) {
                const on = cycle(i * 7 + wy * 3 + wx, 5) === 0;
                ctx.fillStyle = on ? CONFIG.COLORS.midWindowLit : CONFIG.COLORS.midWindowOff;
                ctx.fillRect(bx + 6 + wx * 16, by + 8 + wy * 14, 6, 8);
            }
        }
    }
};

/**
 * The playfield itself.
 *
 * Only the tiles on screen are visited — a level is far wider than the view,
 * and drawing all of it would scale with level length rather than screen size.
 */
/**
 * Haze over the backdrop, under the playfield.
 *
 * Without it the canal houses read as geometry at the same depth as the
 * rooftops — their gables sat at play-surface height and looked landable. A
 * wash of the sky colour pushes them back where they belong.
 */
World.prototype.drawHaze = function (ctx) {
    const g = ctx.createLinearGradient(0, 0, 0, CONFIG.CANVAS_H);
    g.addColorStop(0, CONFIG.COLORS.hazeTop);
    g.addColorStop(0.55, CONFIG.COLORS.hazeMid);
    g.addColorStop(1, CONFIG.COLORS.hazeLow);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, CONFIG.CANVAS_W, CONFIG.CANVAS_H);
};

World.prototype.drawTiles = function (ctx, cam) {
    const C = CONFIG.COLORS;
    const T = CONFIG.TILE;
    const tx0 = Math.max(0, Math.floor(cam.x / T));
    const ty0 = Math.max(0, Math.floor(cam.y / T));
    const tx1 = Math.min(this.map.cols - 1, Math.floor((cam.x + CONFIG.CANVAS_W) / T));
    const ty1 = Math.min(this.map.rows - 1, Math.floor((cam.y + CONFIG.CANVAS_H) / T));

    for (let ty = ty0; ty <= ty1; ty++) {
        for (let tx = tx0; tx <= tx1; tx++) {
            const ch = this.map.tileAt(tx, ty);
            const x = Math.round(tx * T - cam.x);
            const y = Math.round(ty * T - cam.y);

            if (ch === TILE_SOLID) {
                // Tone varies per tile from a fixed hash, so the mass has
                // grain without shimmering as the camera moves.
                const v = ((tx * 73 + ty * 151) % 5) - 2;
                ctx.fillStyle = v > 0 ? C.brickLit : v < 0 ? C.brickDark : C.brickRed;
                ctx.fillRect(x, y, T, T);
                ctx.fillStyle = C.brickRed;
                ctx.fillRect(x, y + 2, T, T - 4);

                // Courses of brick. Derived from tile coordinates, so the
                // pattern is fixed to the world and does not crawl as it scrolls.
                ctx.fillStyle = C.brickDark;
                for (let r = 0; r < T; r += 5) {
                    const stagger = ((ty * T + r) / 5 + tx) % 2 === 0 ? 0 : 5;
                    for (let c = stagger; c < T; c += 10) ctx.fillRect(x + c, y + r, 1, 1);
                }

                // A lit roof cap wherever this tile is exposed to the sky.
                if (this.map.tileAt(tx, ty - 1) !== TILE_SOLID) {
                    ctx.fillStyle = C.roofTile;
                    ctx.fillRect(x, y, T, 4);
                    ctx.fillStyle = C.roofTileDark;
                    ctx.fillRect(x, y, T, 2);
                    ctx.fillStyle = CONFIG.COLORS.roofTileLip;
                    ctx.fillRect(x, y + 4, T, 1);
                    ctx.fillStyle = CONFIG.COLORS.roofTileSheen;
                    ctx.fillRect(x, y + 5, T, 2);
                }

                // A lit window, on a fixed one-in-seven of the buried tiles.
                if (this.map.tileAt(tx, ty - 1) === TILE_SOLID && ((tx * 7 + ty * 13) % 7) === 0) {
                    ctx.fillStyle = C.windowLit;
                    ctx.fillRect(x + 5, y + 5, 6, 7);
                    ctx.fillStyle = CONFIG.COLORS.windowGlow;
                    ctx.fillRect(x + 2, y + 2, 12, 13);
                }
            } else if (ch === TILE_PLATFORM) {
                // Read as a plank walkway: solid on top, open underneath.
                ctx.fillStyle = C.gableStone;
                ctx.fillRect(x, y, T, 4);
                ctx.fillStyle = C.gableWhite;
                ctx.fillRect(x, y, T, 1);
                ctx.fillStyle = C.brickDark;
                ctx.fillRect(x + 2, y + 4, 2, 2);
                ctx.fillRect(x + 12, y + 4, 2, 2);
            } else if (ch === TILE_UPDRAFT) {
                // Deliberately NOT a filled tile. Filling it drew a solid
                // lighter column that reads as a tower you would walk into,
                // which is the opposite of what it is. Edges and moving specks
                // only, so the eye sees flow rather than substance.
                ctx.fillStyle = CONFIG.COLORS.draughtEdge;
                ctx.fillRect(x + 2, y, T - 4, T);
                ctx.fillStyle = CONFIG.COLORS.draughtSpeck;
                ctx.fillRect(x + 1, y, 1, T);
                ctx.fillRect(x + T - 2, y, 1, T);
                for (let k = 0; k < 3; k++) {
                    const seed = (tx * 31 + ty * 17 + k * 53);
                    const sx = x + 3 + ((seed * 7) % (T - 6));
                    // Rising: subtracting the tick makes the specks travel up,
                    // wrapped into the tile so the column looks continuous.
                    const sy = (((seed * 5) - this.tick * 1.9) % T + T) % T;
                    ctx.fillStyle = 'rgba(255, 244, 214, ' + (0.30 + 0.3 * (k / 3)) + ')';
                    ctx.fillRect(Math.round(sx), Math.round(y + sy), 1, 3);
                }
            } else if (ch === TILE_RAIL) {
                // Iron on sleepers. Deliberately unlike the pale plank of a
                // one-way platform: a rail means a trolley is coming, and a
                // player should be able to see that a section is a rail run
                // before boarding rather than after.
                ctx.fillStyle = C.railTie;
                for (let k = 0; k < T; k += 5) ctx.fillRect(x + k, y + 3, 3, 4);
                ctx.fillStyle = C.railIron;
                ctx.fillRect(x, y, T, 2);
                ctx.fillStyle = CONFIG.COLORS.railIronLit;
                ctx.fillRect(x, y, T, 1);
                ctx.fillStyle = C.railTie;
                ctx.fillRect(x, y + 7, T, 1);
            } else if (ch === TILE_WATER) {
                ctx.fillStyle = C.canalBlue;
                ctx.fillRect(x, y, T, T);
                ctx.fillStyle = CONFIG.COLORS.canalSheen;
                ctx.fillRect(x, y + 1, T, 1);
            }
        }
    }
};

World.prototype.drawPickups = function (ctx, cam) {
    const C = CONFIG.COLORS;

    for (let i = 0; i < this.map.notes.length; i++) {
        const n = this.map.notes[i];
        if (n.taken) continue;
        const x = Math.round(n.x - cam.x);
        const y = Math.round(n.y - cam.y);
        if (x < -16 || x > CONFIG.CANVAS_W + 16) continue;
        Renderer.glow(ctx, x + 3, y + 4, 8, '240,234,216', 0.22);
        ctx.fillStyle = C.noteWhite;
        ctx.fillRect(x, y + 4, 4, 4);
        ctx.fillRect(x + 4, y, 1, 5);
        ctx.fillRect(x + 5, y, 2, 1);
    }

    for (let i = 0; i < this.map.letters.length; i++) {
        const l = this.map.letters[i];
        if (l.taken) continue;
        const x = Math.round(l.x - cam.x);
        const y = Math.round(l.y - cam.y);
        if (x < -24 || x > CONFIG.CANVAS_W + 24) continue;
        Renderer.glow(ctx, x + 6, y + 6, 14, '255,210,74', 0.28);
        ctx.fillStyle = C.letterGold;
        ctx.font = '10px "Press Start 2P", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(l.ch, x + 6, y + 10);
        ctx.textAlign = 'left';
    }
};

World.prototype.drawExit = function (ctx, cam) {
    const e = this.map.exit;
    if (!e) return;
    const x = Math.round(e.x - cam.x);
    const y = Math.round(e.y - cam.y);
    if (x < -40 || x > CONFIG.CANVAS_W + 40) return;

    // A lit doorway in a gable end: the one warm thing on the screen.
    Renderer.glow(ctx, x + 8, y + 16, 26, '122,255,200', 0.26);
    ctx.fillStyle = CONFIG.COLORS.exitDoor;
    ctx.fillRect(x, y, 16, 32);
    ctx.fillStyle = CONFIG.COLORS.exitGlow;
    ctx.fillRect(x + 3, y + 6, 10, 26);
    ctx.fillStyle = CONFIG.COLORS.exitDoorDeep;
    ctx.fillRect(x + 5, y + 10, 6, 22);
    ctx.fillStyle = CONFIG.COLORS.gableStone;
    ctx.fillRect(x - 1, y + 2, 18, 4);
};
