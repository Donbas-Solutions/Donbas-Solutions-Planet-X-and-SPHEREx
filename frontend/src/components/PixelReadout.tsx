import type { FlagBit, PixelPos } from '../api/types'
import { useAppState } from '../hooks/useAppState'
import { flagMask, flagNames } from '../lib/flags'
import type { LoadedFrame } from '../lib/frames'

interface ValueProps {
  lf: LoadedFrame
  px: PixelPos
  bits: readonly FlagBit[]
  saturationMask: number
}

function PixelValue({ lf, px, bits, saturationMask }: ValueProps) {
  const [, nx] = lf.frame.shape
  const i = px.y * nx + px.x
  const value = lf.data[i] ?? Number.NaN
  const flags = lf.flags?.[i] ?? 0
  const shown = flagNames(bits, flags).filter((b) => b.group !== 'info')

  let text: string
  if ((flags & saturationMask) !== 0) text = 'saturated (no value)'
  else if (!Number.isFinite(value)) text = 'no data'
  else text = value.toPrecision(4)

  return (
    <>
      <dt>{lf.frame.label}</dt>
      <dd>
        {text}
        {shown.length > 0 && <span className="muted"> · {shown.map((b) => b.name).join(', ')}</span>}
      </dd>
    </>
  )
}

/** Values at the clicked pixel; a saturated pixel shows "saturated", never a number. */
export default function PixelReadout() {
  const { sequence, selectedPixel, setSelectedPixel, currentFrame, frameA, frameB, params } = useAppState()
  if (!sequence) return null
  if (!selectedPixel) return <p className="muted small">Click the image to read pixel values.</p>

  const bits = sequence.flag_bits
  const saturationMask = flagMask(bits, ['saturation'])
  const shown = params.view === 'diff' ? [frameA, frameB] : [currentFrame]
  const frames = shown.filter((f): f is LoadedFrame => f !== null)

  return (
    <section className="pixel-readout" aria-label="Selected pixel">
      <h3>
        Pixel x {selectedPixel.x}, y {selectedPixel.y}{' '}
        <button type="button" className="link-button" onClick={() => setSelectedPixel(null)}>
          clear
        </button>
      </h3>
      <dl className="meta">
        {frames.map((lf) => (
          <PixelValue key={lf.frame.id} lf={lf} px={selectedPixel} bits={bits} saturationMask={saturationMask} />
        ))}
      </dl>
    </section>
  )
}
