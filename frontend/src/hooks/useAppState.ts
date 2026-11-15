import { createContext, useContext, type Dispatch, type SetStateAction } from 'react'
import type { PixelPos, Sequence } from '../api/types'
import type { LoadedFrame } from '../lib/frames'
import type { Playlist } from '../lib/playlist'
import type { ProperMotion, SequenceSource, ViewParams } from '../lib/urlState'
import type { SequenceLoad } from './useSequence'
import type { SetViewParams } from './useViewParams'

export interface TargetInfo {
  name: string | null
  /** ICRS degrees */
  ra: number
  dec: number
  pm: ProperMotion | null
}

/** App-wide state shared by the player (Track B) and the tab panels (Track D). Read it with `useAppState()`. */
export interface AppState {
  /** View params mirrored in the page URL (docs/spec.md §5.3). */
  params: ViewParams
  setParams: SetViewParams
  /** Shows one notice in the page banner. */
  notify: (text: string) => void
  source: SequenceSource
  load: SequenceLoad
  retry: () => void
  /** Stops a running live request (polling ends; there is no server-side cancel). */
  cancel: () => void
  /** The ready sequence; null while loading or on error. */
  sequence: Sequence | null
  /** Every frame of the sequence, in manifest order. */
  frames: readonly LoadedFrame[]
  /** The frames being blinked: one detector set (from `params.det`), in time order. */
  playlist: Playlist
  target: TargetInfo | null
  /** Index into `playlist.frames`. */
  frameIndex: number
  currentFrame: LoadedFrame | null
  /** A/B blink and difference operands (`params.a` / `params.b`, default first / last of the playlist). */
  frameA: LoadedFrame | null
  frameB: LoadedFrame | null
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
