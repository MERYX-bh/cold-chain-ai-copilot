export type Advance = { progress: number; finished: boolean };

export function advance(progress: number, dtSeconds: number, speed: number, durationSeconds: number, loop: boolean): Advance {
  const next = progress + (dtSeconds * speed) / durationSeconds;
  if (next < 1) return { progress: Math.max(0, next), finished: false };
  return loop ? { progress: next % 1, finished: false } : { progress: 1, finished: true };
}
