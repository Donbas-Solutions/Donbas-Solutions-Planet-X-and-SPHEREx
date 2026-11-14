import { useEffect, useRef, type MouseEvent } from 'react'
import { useAppState } from '../hooks/useAppState'
import { renderFrame } from '../lib/frames'
import { displayToPixel, pixelToDisplay, type DisplayFraction } from '../lib/pixels'

interface Props {
  zoom: number
  overlayMask: number
}

function percent(f: DisplayFraction) {
  return { left: `${f.left * 100}%`, top: `${f.top * 100}%` }
}

export default function Viewer({ zoom, overlayMask }: Props) {
  const { sequence, currentFrame, selectedPixel, setSelectedPixel } = useAppState()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const ctx = canvasRef.current?.getContext('2d')
    if (!ctx || !sequence || !currentFrame) return
    renderFrame(ctx, currentFrame, sequence.stretch, { overlayMask })
  }, [sequence, currentFrame, overlayMask])

  if (!sequence || !currentFrame) return null

  const { frame } = currentFrame
  const [ny, nx] = frame.shape

  const handleClick = (e: MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = displayToPixel(
      { left: (e.clientX - rect.left) / rect.width, top: (e.clientY - rect.top) / rect.height },
      frame.shape,
    )
    setSelectedPixel(px)
  }

  return (
    <div className="viewer" style={{ width: nx * zoom, aspectRatio: `${nx} / ${ny}` }}>
      <canvas
        ref={canvasRef}
        width={nx}
        height={ny}
        // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- the image is drawn on a canvas, which needs an explicit role
        role="img"
        aria-label={`${sequence.meta.target_name ?? 'Field'}: ${frame.label}, ${frame.date_range.join(' to ')} UTC`}
        onClick={handleClick}
      />
      {frame.expected_px && (
        <div
          className="marker"
          title="Expected position from proper motion (not a detection)"
          style={percent(pixelToDisplay(frame.expected_px, frame.shape))}
        />
      )}
      {selectedPixel && (
        <div className="crosshair" style={percent(pixelToDisplay(selectedPixel, frame.shape))} />
      )}
    </div>
  )
}
