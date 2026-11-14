import { useEffect, useEffectEvent } from 'react'

/** Calls `onTick` every 1/fps seconds while `isRunning`. A setTimeout chain, so a changed fps applies at once. */
export function usePlayback(isRunning: boolean, fps: number, onTick: () => void): void {
  const tick = useEffectEvent(onTick)
  useEffect(() => {
    if (!isRunning || !(fps > 0)) return
    const intervalMs = 1000 / fps
    let id = window.setTimeout(function run() {
      tick()
      id = window.setTimeout(run, intervalMs)
    }, intervalMs)
    return () => window.clearTimeout(id)
  }, [isRunning, fps])
}

export function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}
