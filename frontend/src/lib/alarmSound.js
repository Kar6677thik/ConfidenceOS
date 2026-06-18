let _ctx = null;

function getCtx() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;
  if (!_ctx) _ctx = new Ctx();
  if (_ctx.state === 'suspended') _ctx.resume();
  return _ctx;
}

const MUTE_KEY = 'cos_alarm_mute';
const _listeners = new Set();

export function isMuted() {
  return localStorage.getItem(MUTE_KEY) === '1';
}

export function setMuted(muted) {
  localStorage.setItem(MUTE_KEY, muted ? '1' : '0');
  _listeners.forEach((fn) => fn(muted));
}

export function onMuteChange(fn) {
  _listeners.add(fn);
  return () => _listeners.delete(fn);
}

export function beepCritical() {
  if (isMuted()) return;
  try {
    const ctx = getCtx();
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.35);
  } catch {
    // Autoplay policy or no Web Audio — silent fail.
  }
}
