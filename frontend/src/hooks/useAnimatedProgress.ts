import { useEffect, useRef, useState } from "react";
import { advance } from "../lib/animation";

type Options = { playing: boolean; speed: number; durationSeconds: number; loop: boolean };

export function useAnimatedProgress({ playing, speed, durationSeconds, loop }: Options) {
  const [progress, setProgress] = useState(0);
  const lastFrame = useRef<number | null>(null);

  useEffect(() => {
    if (!playing) {
      lastFrame.current = null;
      return;
    }
    let frame = 0;
    const tick = (now: number) => {
      if (lastFrame.current !== null) {
        const elapsed = Math.min((now - lastFrame.current) / 1000, 0.1);
        setProgress((current) => advance(current, elapsed, speed, durationSeconds, loop).progress);
      }
      lastFrame.current = now;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, durationSeconds, loop]);

  return [progress, setProgress] as const;
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
