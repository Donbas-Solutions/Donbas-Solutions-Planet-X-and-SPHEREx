import type { Frame, FrameWarning, WarningCode } from '../api/types'

/** Codes that mean a frame's data is incomplete; `saturated` describes the source, not missing data. */
const PARTIAL_DATA_CODES: ReadonlySet<WarningCode> = new Set<WarningCode>(['few_exposures', 'incomplete_lambda'])

export function isPartialData(warning: FrameWarning): boolean {
  return PARTIAL_DATA_CODES.has(warning.code)
}

export function hasPartialData(frame: Frame): boolean {
  return frame.warnings.some(isPartialData)
}
