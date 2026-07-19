// Decorative "waveform" used by the audio preview player and the recorder. It is not a
// real FFT of the clip (decoding every clip just to draw it isn't worth it here) — it's a
// stable pseudo-random bar pattern that fills left-to-right with playback progress, which
// reads exactly like the mockup's "Nghe thử" scrubber.

// Deterministic 0.35–1 height for bar `i` from a cheap hash, so the pattern is stable
// across renders (no Math.random re-shuffling the bars every frame).
function barHeight(i: number): number {
  const wave = Math.sin(i * 12.9898) * 43758.5453;
  const frac = wave - Math.floor(wave); // 0–1
  return 0.35 + frac * 0.65;
}

export default function WaveBars({
  count = 40,
  progress = 0,
  live = 0,
  className = "",
}: {
  count?: number;
  progress?: number; // 0–1 playback position; bars up to here render "played"
  live?: number; // 0–1 live mic level; when > 0, animates the tail bars while recording
  className?: string;
}) {
  const filledUpTo = Math.round(progress * count);

  return (
    <div className={`flex h-9 items-center gap-[3px] ${className}`} aria-hidden>
      {Array.from({ length: count }, (_, i) => {
        const base = barHeight(i);
        // While recording, ripple the height by the live level so it visibly reacts.
        const height = live > 0 ? Math.min(1, base * (0.5 + live)) : base;
        const played = i < filledUpTo;
        return (
          <span
            key={i}
            className={`w-[3px] shrink-0 rounded-full transition-[height,background-color] duration-100 ${
              played ? "bg-[#4f46e5]" : live > 0 ? "bg-[#818cf8]" : "bg-[#cbd5e1]"
            }`}
            style={{ height: `${Math.round(height * 100)}%` }}
          />
        );
      })}
    </div>
  );
}
