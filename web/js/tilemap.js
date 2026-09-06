// tilemap.js — Roderick Tron | MagmaCrunch Media © 2026
// Level parsing, and the collision the whole game stands on.

const TILE_AIR = '.';
const TILE_SOLID = '#';
const TILE_PLATFORM = '=';
const TILE_WATER = '~';
const TILE_UPDRAFT = '^';
const TILE_RAIL = '-';

function isSolidTile(ch) { return ch === TILE_SOLID; }
function isPlatformTile(ch) { return ch === TILE_PLATFORM || ch === TILE_RAIL; }
function isRailTile(ch) { return ch === TILE_RAIL; }
function isWaterTile(ch) { return ch === TILE_WATER; }
function isUpdraftTile(ch) { return ch === TILE_UPDRAFT; }

/**
 * A parsed level: a grid of terrain, plus the things that were sitting in it.
 *
 * Entity characters are lifted out at parse time and their cells become air, so
 * collision never has to know what a gargoyle is.
 */
function Tilemap(def) {
    this.name = def.name;
    this.subtitle = def.subtitle || '';

    const width = Math.max.apply(null, def.rows.map(function (r) { return r.length; }));
    this.cols = width;
    this.rows = def.rows.length;
    this.w = this.cols * CONFIG.TILE;
    this.h = this.rows * CONFIG.TILE;

    this.spawn = { x: CONFIG.TILE, y: CONFIG.TILE };
    this.exit = null;
    this.notes = [];
    this.letters = [];
    this.enemies = [];
    this.bells = [];
    this.trolleys = [];

    this.grid = [];
    for (let ty = 0; ty < this.rows; ty++) {
        // Short rows are padded rather than rejected: trimming trailing air
        // from a line should not shift the rest of the level sideways.
        const row = def.rows[ty].padEnd(width, TILE_AIR).split('');
        for (let tx = 0; tx < width; tx++) {
            const ch = row[tx];
            const px = tx * CONFIG.TILE;
            const py = ty * CONFIG.TILE;
            let consumed = true;

            if (ch === 'S') {
                // Bottom-aligned in its tile, so a spawn marker drawn sitting
                // on the ground puts his feet on that ground.
                this.spawn = { x: px + 1, y: py + CONFIG.TILE - CONFIG.PLAYER_H };
            } else if (ch === 'E') {
                this.exit = { x: px, y: py - CONFIG.TILE, w: CONFIG.TILE, h: CONFIG.TILE * 2 };
            } else if (ch === 'o') {
                this.notes.push({ x: px + 4, y: py + 4, w: 8, h: 8, taken: false });
            } else if (ch === 'T' || ch === 'R' || ch === 'O' || ch === 'N') {
                this.letters.push({
                    ch: ch, x: px + 2, y: py + 2,
                    w: CONFIG.TILE - 4, h: CONFIG.TILE - 4, taken: false,
                });
            } else if (ch === 'g') {
                this.enemies.push({ kind: 'gargoyle', x: px, y: py + CONFIG.TILE - CONFIG.GARGOYLE_H });
            } else if (ch === 'f') {
                this.enemies.push({ kind: 'flyer', x: px, y: py });
            } else if (ch === 'b') {
                this.bells.push({
                    x: px + (CONFIG.TILE - CONFIG.BELL_W) / 2,
                    y: py + (CONFIG.TILE - CONFIG.BELL_H) / 2,
                });
            } else if (ch === 'c') {
                this.trolleys.push({ x: px, y: py + CONFIG.TILE - CONFIG.TROLLEY_H });
            } else if (ch === 's') {
                this.enemies.push({ kind: 'statue', x: px, y: py + CONFIG.TILE - CONFIG.GARGOYLE_H });
            } else {
                consumed = false;
            }

            if (consumed) row[tx] = TILE_AIR;
        }
        this.grid.push(row);
    }
}

/**
 * The character at a tile.
 *
 * Off the left and right edges reads as solid, so a level is walled rather than
 * open to an endless sideways fall. Above and below read as air: dropping out
 * of the bottom is how a pit kills you.
 */
Tilemap.prototype.tileAt = function (tx, ty) {
    if (tx < 0 || tx >= this.cols) return TILE_SOLID;
    if (ty < 0 || ty >= this.rows) return TILE_AIR;
    return this.grid[ty][tx];
};

/** Every tile a pixel-space box touches, as [tx0, ty0, tx1, ty1]. */
Tilemap.prototype.tileRange = function (x, y, w, h) {
    return [
        Math.floor(x / CONFIG.TILE),
        Math.floor(y / CONFIG.TILE),
        Math.floor((x + w - 1) / CONFIG.TILE),
        Math.floor((y + h - 1) / CONFIG.TILE),
    ];
};

Tilemap.prototype.overlaps = function (x, y, w, h, test) {
    const r = this.tileRange(x, y, w, h);
    for (let ty = r[1]; ty <= r[3]; ty++) {
        for (let tx = r[0]; tx <= r[2]; tx++) {
            if (test(this.tileAt(tx, ty))) return true;
        }
    }
    return false;
};

/** Does this box overlap brick? One-way platforms are not solid here. */
Tilemap.prototype.overlapsSolid = function (x, y, w, h) {
    return this.overlaps(x, y, w, h, isSolidTile);
};

Tilemap.prototype.overlapsWater = function (x, y, w, h) {
    return this.overlaps(x, y, w, h, isWaterTile);
};

/** Is any part of this box in rising air? Updraft tiles are not solid. */
Tilemap.prototype.overlapsUpdraft = function (x, y, w, h) {
    return this.overlaps(x, y, w, h, isUpdraftTile);
};

/** Horizontal centre of the updraft column this box is in, or null. */
Tilemap.prototype.updraftCentre = function (x, y, w, h) {
    const r = this.tileRange(x, y, w, h);
    for (let ty = r[1]; ty <= r[3]; ty++) {
        for (let tx = r[0]; tx <= r[2]; tx++) {
            if (isUpdraftTile(this.tileAt(tx, ty))) return tx * CONFIG.TILE + CONFIG.TILE / 2;
        }
    }
    return null;
};

/**
 * Top of the highest one-way platform this box has just landed on, or null.
 *
 * `prevBottom` is the whole of what makes it one-way: a platform only stops a
 * body that was already above it, so you rise through the same tile you later
 * stand on.
 */
Tilemap.prototype.platformTop = function (x, y, w, h, prevBottom) {
    const r = this.tileRange(x, y, w, h);
    // Scan one row further down than the body occupies. tileRange stops at
    // (y + h - 1), so a body resting EXACTLY on a platform — bottom flush with
    // the tile top — never sees the tile holding it up, and sinks: the first
    // frame the tile is out of range, and by the second the playhead has passed
    // it and the came-from-above guard rejects it. Landing from a height hides
    // this, because a fast step crosses the boundary in one move.
    const bottomRow = Math.floor((y + h) / CONFIG.TILE);
    let best = null;
    for (let ty = r[1]; ty <= Math.max(r[3], bottomRow); ty++) {
        const top = ty * CONFIG.TILE;
        if (prevBottom > top + 0.001) continue;        // came from below, or inside
        for (let tx = r[0]; tx <= r[2]; tx++) {
            if (isPlatformTile(this.tileAt(tx, ty)) && (best === null || top < best)) best = top;
        }
    }
    return best;
};

/**
 * Move a body horizontally, stopping flush against brick.
 *
 * Stepped under a tile at a time so nothing can tunnel through a wall. Normal
 * running never needs it — 4.2px a frame at most — but a stomp bounce plus
 * knockback can exceed a tile in one step, and passing through a wall is the
 * one bug that makes a platformer feel broken rather than merely hard.
 */
Tilemap.prototype.moveX = function (box, dx) {
    if (!dx) return false;
    const cap = CONFIG.TILE - 1;
    const step = Math.sign(dx) * Math.min(Math.abs(dx), cap);
    let remaining = dx;
    let hit = false;

    while (Math.abs(remaining) > 0.0001) {
        const move = Math.abs(remaining) < Math.abs(step) ? remaining : step;
        const next = box.x + move;
        if (this.overlapsSolid(next, box.y, box.w, box.h)) {
            box.x = move > 0
                ? Math.floor((next + box.w) / CONFIG.TILE) * CONFIG.TILE - box.w
                : (Math.floor(next / CONFIG.TILE) + 1) * CONFIG.TILE;
            hit = true;
            break;
        }
        box.x = next;
        remaining -= move;
    }
    return hit;
};

/**
 * Move a body vertically. Reports which surface stopped it.
 *
 * `dropping` suppresses one-way platforms, for a body deliberately dropping
 * through one.
 */
Tilemap.prototype.moveY = function (box, dy, dropping) {
    const result = { ground: false, ceiling: false, platform: false };
    if (!dy) return result;

    const cap = CONFIG.TILE - 1;
    const step = Math.sign(dy) * Math.min(Math.abs(dy), cap);
    let remaining = dy;

    while (Math.abs(remaining) > 0.0001) {
        const move = Math.abs(remaining) < Math.abs(step) ? remaining : step;
        const prevBottom = box.y + box.h;
        const next = box.y + move;

        if (this.overlapsSolid(box.x, next, box.w, box.h)) {
            if (move > 0) {
                box.y = Math.floor((next + box.h) / CONFIG.TILE) * CONFIG.TILE - box.h;
                result.ground = true;
            } else {
                box.y = (Math.floor(next / CONFIG.TILE) + 1) * CONFIG.TILE;
                result.ceiling = true;
            }
            break;
        }

        if (move > 0 && !dropping) {
            const top = this.platformTop(box.x, next, box.w, box.h, prevBottom);
            if (top !== null) {
                box.y = top - box.h;
                result.ground = true;
                result.platform = true;
                break;
            }
        }

        box.y = next;
        remaining -= move;
    }
    return result;
};

/** Is this box sitting over rail? The trolley only rolls where there is track. */
Tilemap.prototype.overlapsRail = function (x, y, w, h) {
    return this.overlaps(x, y, w, h, isRailTile);
};

/** Is there footing directly under this box? Used by enemy ledge-turning. */
Tilemap.prototype.hasFooting = function (x, y, w, h) {
    return this.overlapsSolid(x, y + h, w, 1)
        || this.overlaps(x, y + h, w, 1, isPlatformTile);
};
