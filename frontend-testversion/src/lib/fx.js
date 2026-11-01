// Alert effects: buzz + chime when a new alert arrives.
// Browsers only allow sound after the person has tapped the page once, so the first tap
// anywhere unlocks audio (main.jsx calls installAudioUnlock).
let audioCtx = null;

export function unlockAudio() {
  if (audioCtx) return;
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) audioCtx = new AC();
  } catch {
    audioCtx = null;
  }
}

export function installAudioUnlock() {
  document.addEventListener("pointerdown", unlockAudio, { once: true });
}

export const soundReady = () => !!audioCtx;

function chime() {
  if (!audioCtx) return;
  try {
    const t = audioCtx.currentTime;
    [[880, 0], [1320, 0.16]].forEach(([f, d]) => {
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      o.type = "sine";
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t + d);
      g.gain.exponentialRampToValueAtTime(0.25, t + d + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + d + 0.45);
      o.connect(g);
      g.connect(audioCtx.destination);
      o.start(t + d);
      o.stop(t + d + 0.5);
    });
  } catch {
    /* ignore */
  }
}

// Turn off with VITE_SOUND=off at build time.
const SOUND = import.meta.env.VITE_SOUND !== "off";

export function alertFx() {
  if (!SOUND) return;
  try {
    if (navigator.vibrate && (!navigator.userActivation || navigator.userActivation.hasBeenActive)) {
      navigator.vibrate([220, 120, 220]);
    }
  } catch {
    /* ignore */
  }
  chime();
}

export const soundEnabled = SOUND;
