import { useEffect, useEffectEvent } from 'react'

export interface PlayerKeyHandlers {
  onTogglePlay: () => void
  onStep: (delta: number) => void
  onToggleAb: () => void
}

/**
 * Global shortcuts: Space, ←/→, B. Keys that the focused control uses itself are left to it
 * (typing in a field, Space on a button, arrows on a slider or tab).
 */
export function usePlayerKeys({ onTogglePlay, onStep, onToggleAb }: PlayerKeyHandlers): void {
  const handleKeyDown = useEffectEvent((e: KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return
    const el = e.target instanceof Element ? e.target : null
    if (el?.closest('input:not([type=range]):not([type=checkbox]), select, textarea, [contenteditable="true"]')) return
    const isSlider = el?.matches('input[type=range]') ?? false
    const isActivatable = el?.closest('button, a, input[type=checkbox], [role=tab]') !== null && el !== null

    switch (e.key) {
      case ' ':
        if (isSlider || isActivatable) return
        e.preventDefault()
        onTogglePlay()
        return
      case 'ArrowLeft':
      case 'ArrowRight':
        if (isSlider || el?.closest('[role=tab]')) return
        e.preventDefault()
        onStep(e.key === 'ArrowRight' ? 1 : -1)
        return
      case 'b':
      case 'B':
        onToggleAb()
        return
    }
  })

  useEffect(() => {
    const listener = (e: KeyboardEvent) => handleKeyDown(e)
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  }, [])
}
