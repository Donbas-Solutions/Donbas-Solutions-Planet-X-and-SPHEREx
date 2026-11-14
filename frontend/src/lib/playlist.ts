import type { Frame } from '../api/types'
import type { LoadedFrame } from './frames'
import type { DetectorChoice } from './urlState'

const ALL_DETECTORS = '1,2,3,4,5,6'
const BLINKABLE: readonly Frame['kind'][] = ['visit_stack', 'exposure']

export function detectorKey(detectors: readonly number[]): string {
  return [...detectors].sort((a, b) => a - b).join(',')
}

export function detectorLabel(key: string): string {
  return key === ALL_DETECTORS ? 'all detectors' : key.split(',').map((d) => `D${d}`).join('+')
}

export interface Playlist {
  frames: readonly LoadedFrame[]
  /** Detector set of every frame in the playlist. */
  key: string
  /** False when the requested detectors are not in this sequence and another set is shown instead. */
  isRequested: boolean
  availableKeys: readonly string[]
}

/**
 * Frames that may be blinked together: one detector set, in time order. Mixing detectors would show
 * λ differences as fake brightness changes (CLAUDE.md → Science rules).
 */
export function buildPlaylist(all: readonly LoadedFrame[], det: DetectorChoice): Playlist {
  const blinkable = all.filter((f) => BLINKABLE.includes(f.frame.kind))
  const availableKeys = [...new Set(blinkable.map((f) => detectorKey(f.frame.detectors)))]
  const wanted = det === 'all' ? ALL_DETECTORS : detectorKey(det)
  const isRequested = availableKeys.includes(wanted)
  const key = isRequested ? wanted : (availableKeys.find((k) => k === ALL_DETECTORS) ?? availableKeys[0] ?? wanted)
  const frames = blinkable
    .filter((f) => detectorKey(f.frame.detectors) === key)
    .sort((a, b) => a.frame.mjd_mid - b.frame.mjd_mid)
  return { frames, key, isRequested, availableKeys }
}
