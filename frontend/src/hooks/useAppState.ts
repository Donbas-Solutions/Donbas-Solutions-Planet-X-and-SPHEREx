import { createContext, useContext, type Dispatch, type SetStateAction } from 'react'
import type { PixelPos, Sequence } from '../api/types'
import type { LoadedFrame } from '../lib/frames'
import type { SequenceLoad } from './useSequence'

export interface TargetInfo {
  name: string | null
  /** ICRS degrees */
  ra: number
  dec: number
}

/** App-wide state shared by the player (Track B) and the tab panels (Track D). Read it with `useAppState()`. */
export interface AppState {
  manifestUrl: string
  load: SequenceLoad
  retry: () => void
  /** The ready sequence; null while loading or on error. */
  sequence: Sequence | null
  frames: readonly LoadedFrame[]
  target: TargetInfo | null
  frameIndex: number
  currentFrame: LoadedFrame | null
  /** Pixel the user clicked, in data coordinates of the common grid (row 0 = south). */
  selectedPixel: PixelPos | null
  setFrameIndex: Dispatch<SetStateAction<number>>
  setSelectedPixel: Dispatch<SetStateAction<PixelPos | null>>
}

export const AppStateContext = createContext<AppState | null>(null)

export function useAppState(): AppState {
  const state = useContext(AppStateContext)
  if (!state) throw new Error('useAppState must be used inside <AppStateProvider>')
  return state
}
