import { useMemo, useState, type ReactNode } from 'react'
import type { PixelPos } from '../api/types'
import type { LoadedFrame } from '../lib/frames'
import { AppStateContext, type AppState } from '../hooks/useAppState'
import { useSequence } from '../hooks/useSequence'

interface Props {
  manifestUrl: string
  children: ReactNode
}

const NO_FRAMES: readonly LoadedFrame[] = []

export default function AppStateProvider({ manifestUrl, children }: Props) {
  const { load, retry } = useSequence(manifestUrl)
  const [frameIndex, setFrameIndex] = useState(0)
  const [selectedPixel, setSelectedPixel] = useState<PixelPos | null>(null)

  const value = useMemo<AppState>(() => {
    const sequence = load.status === 'ready' ? load.seq : null
    const frames = load.status === 'ready' ? load.frames : NO_FRAMES
    const index = Math.min(Math.max(frameIndex, 0), Math.max(frames.length - 1, 0))
    return {
      manifestUrl,
      load,
      retry,
      sequence,
      frames,
      target: sequence
        ? { name: sequence.meta.target_name, ra: sequence.grid.ra, dec: sequence.grid.dec }
        : null,
      frameIndex: index,
      currentFrame: frames[index] ?? null,
      selectedPixel,
      setFrameIndex,
      setSelectedPixel,
    }
  }, [manifestUrl, load, retry, frameIndex, selectedPixel])

  return <AppStateContext value={value}>{children}</AppStateContext>
}
