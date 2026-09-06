// input.js — Roderick Tron | MagmaCrunch Media © 2026
// Keyboard state.

const Input = {
    keys: {},
    justPressed: {},

    init() {
        document.addEventListener('keydown', (e) => {
            if (e.repeat) return;
            if (!this.keys[e.code]) this.justPressed[e.code] = true;
            this.keys[e.code] = true;
            if (this.SWALLOW.includes(e.code)) e.preventDefault();
        });
        document.addEventListener('keyup', (e) => { this.keys[e.code] = false; });
        // A tabbed-away window never delivers the keyup, so a held key would
        // read as held forever and the next jump would be cut on frame one.
        window.addEventListener('blur', () => { this.keys = {}; this.justPressed = {}; });
    },

    SWALLOW: [
        'Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
        'KeyZ', 'KeyX', 'ShiftLeft', 'ShiftRight',
    ],

    isDown(code) { return !!this.keys[code]; },

    wasPressed(code) {
        if (this.justPressed[code]) { this.justPressed[code] = false; return true; }
        return false;
    },

    clearJustPressed() { this.justPressed = {}; },

    left()     { return this.isDown('ArrowLeft') || this.isDown('KeyA'); },
    right()    { return this.isDown('ArrowRight') || this.isDown('KeyD'); },
    down()     { return this.isDown('ArrowDown') || this.isDown('KeyS'); },
    run()      { return this.isDown('ShiftLeft') || this.isDown('ShiftRight'); },
    jump()     { return this.wasPressed('Space') || this.wasPressed('ArrowUp') || this.wasPressed('KeyW'); },
    jumpHeld() { return this.isDown('Space') || this.isDown('ArrowUp') || this.isDown('KeyW'); },
    roll()     { return this.wasPressed('KeyX'); },
    shoot()    { return this.wasPressed('KeyZ'); },
};
