import { useAppState } from '../../hooks/useAppState'

export default function SpectrumPanel() {
  const { selectedPixel } = useAppState()
  return (
    <p className="muted">
      Spectrum (FR-16) — not available yet.
      {selectedPixel ? ` Selected pixel: x ${selectedPixel.x}, y ${selectedPixel.y}.` : ' Click a source in the image.'}
    </p>
  )
}
