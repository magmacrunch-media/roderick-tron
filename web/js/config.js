// config.js — Roderick Tron | MagmaCrunch Media © 2026
// Constants, palette, physics tuning.
//
// This was an endless auto-runner. It is now a side-scrolling platformer, so
// the numbers below are in tiles-and-gravity terms rather than scroll speed:
// the player drives the camera instead of the camera driving the player.

const CONFIG = {
    CANVAS_W: 480,
    CANVAS_H: 270,
    TILE: 16,                 // 30 x 16.9 tiles on screen

    // ── Player body ───────────────────────────────────────
    // 14 wide fits a one-tile gap with room to spare; 22 tall is taller than a
    // tile and shorter than two, so a two-tile opening is passable and a
    // one-tile one is not. Every level's geometry reads off that.
    PLAYER_W: 14,
    PLAYER_H: 22,

    // ── Ground movement ───────────────────────────────────
    // Acceleration and friction rather than instant velocity: the weight is
    // most of what separates this from the runner it replaced.
    WALK_MAX: 1.55,
    RUN_MAX: 2.85,
    ROLL_MAX: 4.20,
    ACCEL: 0.30,
    AIR_ACCEL: 0.17,          // less authority in the air, so commitment matters
    FRICTION: 0.34,
    AIR_FRICTION: 0.06,
    TURN_BOOST: 1.7,          // reversing bites harder than accelerating

    // ── Jump ──────────────────────────────────────────────
    // Airtime is 2*|v|/g frames and height v^2/(2g) px. Height is what the
    // level's vertical geometry reads off; AIRTIME is what its gaps read off,
    // and it is the one worth tuning for. A stiffer 0.55/-7.9 gave the same
    // 56px apex in only 28.7 frames, which left a roll-jump reaching barely
    // one tile further than a running one — no distance to design with.
    GRAVITY: 0.44,
    JUMP_FORCE: -7.0,
    MAX_FALL: 7.2,
    JUMP_CUT: 0.45,           // releasing early clips the climb
    COYOTE_FRAMES: 6,
    JUMP_BUFFER_FRAMES: 8,
    STOMP_BOUNCE: -5.6,       // the hop you get off a flattened enemy
    STOMP_BOUNCE_HELD: -7.4,  // ...higher if you were holding jump, as in DKC

    get JUMP_AIRTIME() { return 2 * Math.abs(this.JUMP_FORCE) / this.GRAVITY; },
    get JUMP_HEIGHT() { return (this.JUMP_FORCE * this.JUMP_FORCE) / (2 * this.GRAVITY); },

    // ── Roll ──────────────────────────────────────────────
    // The skill move. It kills on contact, and rolling off a ledge carries the
    // speed into the jump — which is how DKC's longest gaps are meant to be
    // crossed, and the reason a roll has to be committal rather than free.
    ROLL_FRAMES: 34,
    ROLL_COOLDOWN: 14,
    ROLL_H: 14,               // shorter while rolling: fits a one-tile gap

    // ── Bell cannon ───────────────────────────────────────
    // The barrel cannon of this rooftop. It catches you, swings through an arc
    // overhead, and fires along whatever angle it is pointing when you press
    // jump — so the timing is the skill, and no extra level syntax is needed to
    // encode an aim.
    BELL_W: 20,
    BELL_H: 20,
    BELL_SWING_FROM: -155,      // degrees; -90 is straight up
    BELL_SWING_TO: -25,
    BELL_SWING_RATE: 0.030,     // radians of phase per frame
    BELL_LAUNCH: 10.0,          // px/frame; at 45 degrees that flies v^2/g = 227px
    BELL_RECAPTURE: 26,         // frames before the same bell can catch you again
    BELL_AIM_LEN: 22,           // how far the aiming line is drawn

    // ── Chimney updraft ───────────────────────────────────
    // Warm air off a chimney. Not a jump: it is a sustained climb, which is how
    // a level gets to reach upward at all when a jump only clears 52px.
    // Must exceed GRAVITY, or the column pushes DOWN. At 0.42 against a
    // gravity of 0.44 it did exactly that, by 0.02px a frame — a draught that
    // looked right, read right in the level file, and lifted nobody.
    UPDRAFT_LIFT: 0.98,
    UPDRAFT_MAX_RISE: 2.6,      // terminal upward speed inside a column
    UPDRAFT_DRIFT: 0.06,        // gentle sideways settling toward the centre

    // ── Coal trolley ──────────────────────────────────────
    // The mine cart of this rooftop. A sub-mode rather than a device: while you
    // are aboard, the only verb is jump, and the level is a rail with holes in
    // it. Speed is constant on purpose — a cart you can slow down is a cart you
    // can wait out, and then the section stops being about commitment.
    TROLLEY_W: 22,
    TROLLEY_H: 14,
    TROLLEY_SPEED: 3.4,
    TROLLEY_JUMP: -7.6,         // a shade stronger than his own: it carries load
    TROLLEY_DECEL: 0.10,        // once off the rails, it rolls to a halt
    TROLLEY_DISMOUNT: 1.0,      // ...and below this speed he steps off

    // ── Combat ────────────────────────────────────────────
    NOTE_SPEED: 4.4,
    NOTE_W: 6,
    NOTE_H: 8,
    NOTE_LIFE: 70,
    FIRE_RATE: 14,
    NOTE_AMMO_START: 5,
    NOTE_AMMO_MAX: 20,
    // Collecting is what reloads you, so exploring for notes and fighting are
    // the same activity rather than two unrelated ones.
    AMMO_PER_PICKUP: 1,

    // ── Enemies ───────────────────────────────────────────
    GARGOYLE_W: 14,
    GARGOYLE_H: 14,
    GARGOYLE_SPEED: 0.42,
    GARGOYLE_HP: 1,
    FLYER_SPEED: 0.55,
    FLYER_BOB_AMP: 18,
    FLYER_BOB_RATE: 0.045,
    FLYER_HP: 1,
    STATUE_HP: 3,             // the heavy one: stomp bounces off, notes needed

    // ── Damage ────────────────────────────────────────────
    INVINCIBLE_FRAMES: 96,
    KNOCKBACK_X: 2.2,
    KNOCKBACK_Y: -3.4,
    MAX_LIVES: 3,
    FALL_KILL_MARGIN: 40,     // px below the level before it counts as a fall

    // ── Companion ─────────────────────────────────────────
    // The Diddy slot. Having it is one free hit; losing it is visible and
    // recoverable, which is a gentler failure curve than spending a life.
    BIRD_FOLLOW_LAG: 0.12,
    BIRD_BOB_RATE: 0.09,
    BIRD_BOB_AMP: 3,

    // ── Collectibles ──────────────────────────────────────
    NOTES_PER_LIFE: 100,
    NOTE_POINTS: 10,
    LETTER_POINTS: 200,
    KILL_POINTS: 50,
    EXIT_POINTS: 500,

    // ── Music ─────────────────────────────────────────────
    // The jukebox's copy rather than a second one under this game: identical
    // audio, and a local copy would be 937KB of duplication.
    MUSIC: {
        URL: '../../music/jukebox/songs/'
             + encodeURIComponent('Jimmi - JIMMI - 04 Roderick Tron.ogg'),
        VOLUME: 0.38,
        FADE_IN: 1.5,
        FADE_OUT: 0.9,
    },

    // ── Camera ────────────────────────────────────────────
    // A dead zone, so small hops do not shove the view around. It leads in the
    // direction of travel, which is what buys reaction time at speed.
    CAM_DEADZONE_X: 40,
    CAM_DEADZONE_Y: 28,
    CAM_LOOKAHEAD: 46,
    CAM_LERP: 0.10,

    // ── Palette — 1810s Dutch city, unchanged from the runner ──
    COLORS: {
        sky:          '#1a1028',
        skyHorizon:   '#3a1830',
        canalBlue:    '#0d2a4a',
        brickRed:     '#6a2820',
        brickDark:    '#4a1810',
        brickLit:     '#8a3a2c',
        roofTile:     '#8a4020',
        roofTileDark: '#6a3018',
        gableWhite:   '#e8dcc8',
        gableStone:   '#7a5a48',
        windowLit:    '#ffcf6a',
        gasLamp:      '#ffe03a',
        gasLampGlow:  'rgba(255,224,58,0.15)',
        robotCyan:    '#00f5ff',
        robotSteel:   '#8899aa',
        robotCoat:    '#1a1828',
        muttonChops:  '#cc6620',
        gargoyleStone:'#6a6a80',
        gargoyleDark: '#2a2a3a',
        gargoyleEye:  '#ff3d6e',
        flyerWing:    '#3a3a52',
        statueStone:  '#8a8a9c',
        noteWhite:    '#f0ead8',
        letterGold:   '#ffd24a',
        birdBrass:    '#c8a24a',
        particleStone:'#7a7a8a',
        particleDust: '#5a4a3a',
        hudText:      '#f0ead8',
        lifeHeart:    '#ff3d6e',
        exitGlow:     '#7affc8',
        bellBrass:    '#c9a227',
        bellShadow:   '#7a5f14',
        updraft:      'rgba(255, 224, 160, 0.10)',
        railIron:     '#5b5f70',
        railTie:      '#3a2a22',
        trolleyBody:  '#4a3428',
        trolleyIron:  '#8892a4',
        trolleyCoal:  '#1a1620',

        // ── Backdrop ──
        // The parallax layers, which used to be hex literals scattered
        // through world.js's draw functions. They live here because they
        // are what gets tuned: the far and mid layers currently separate
        // by about two luminance steps out of 255, which is the right
        // direction and far too small a margin to read as two depths.
        moonDisc:     '#d8d0bc',
        farBuilding:  '#161022',
        farWindmill:  '#151020',
        midBuilding:  '#1c1016',
        midGable:     '#241519',
        midGableLip:  '#2d1b20',
        midWindowOff: '#140809',
        midWindowLit: 'rgba(255, 207, 106, 0.22)',
        hazeTop:      'rgba(26, 16, 40, 0.0)',
        hazeMid:      'rgba(26, 16, 40, 0.35)',
        hazeLow:      'rgba(13, 42, 74, 0.55)',
    },
};
