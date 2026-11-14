import { useAppState } from '../../hooks/useAppState'

export default function LightCurvePanel() {
  const { selectedPixel } = useAppState()
  return (
    <p className="muted">
      Light curve (FR-17) — not available yet.
      {selectedPixel ? ` Selected pixel: x ${selectedPixel.x}, y ${selectedPixel.y}.` : ' Click a source in the image.'}
    </p>
  )
}
