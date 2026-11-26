let context: AudioContext | null = null

/** Browsers only allow audio after a user gesture: call this from the click that starts the wait. */
export function unlockSound() {
  context ??= new AudioContext()
  void context.resume()
}

/** A short rising two-note chime. */
export function playDone() {
  const ctx = context
  if (!ctx) return
  const now = ctx.currentTime
  for (const [frequency, at] of [
    [880, 0],
    [1318.5, 0.13],
  ]) {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = "sine"
    osc.frequency.value = frequency
    gain.gain.setValueAtTime(0.0001, now + at)
    gain.gain.exponentialRampToValueAtTime(0.3, now + at + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, now + at + 0.7)
    osc.connect(gain).connect(ctx.destination)
    osc.start(now + at)
    osc.stop(now + at + 0.75)
  }
}
