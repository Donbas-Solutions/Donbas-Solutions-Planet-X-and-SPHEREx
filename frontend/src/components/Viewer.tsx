import { useEffect, useRef, type CSSProperties, type MouseEvent } from 'react'
import type { PixelPos, Stretch } from '../api/types'
import { useAppState } from '../hooks/useAppState'
import type { Colormap } from '../lib/colormap'
import type { OverlayLayer } from '../lib/flags'
import { displayToPixel, pixelToDisplay, type DisplayFraction } from '../lib/pixels'
import { renderImage, type GridImage } from '../lib/render'

export type Zoom = 'fit' | number
export const MAX_ZOOM = 8

export interface Marker {
  id: string
  px: PixelPos
  variant: 'expected' | 'earlier' | 'later' | 'gaia' | 'gaia-mover' | 'gaia-earlier'
  title: string
}

interface Props {
  image: GridImage
  stretch: Stretch
  colormap: Colormap
  overlays: readonly OverlayLayer[]
  zoom: Zoom
  markers: readonly Marker[]
  ariaLabel: string
}

function percent(f: DisplayFraction): CSSProperties {
  return { left: `${f.left * 100}%`, top: `${f.top * 100}%` }
}

export default function Viewer({ image, stretch, colormap, overlays, zoom, markers, ariaLabel }: Props) {
  const { selectedPixel, setSelectedPixel } = useAppState()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [ny, nx] = image.shape

  useEffect(() => {
    const ctx = canvasRef.current?.getContext('2d')
    if (ctx) renderImage(ctx, image, stretch, colormap, { overlays })
  }, [image, stretch, colormap, overlays])

  const handleClick = (e: MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const fraction = { left: (e.clientX - rect.left) / rect.width, top: (e.clientY - rect.top) / rect.height }
    setSelectedPixel(displayToPixel(fraction, image.shape))
  }

  const size: CSSProperties =
    zoom === 'fit'
      ? { width: '100%', maxWidth: `min(${nx * MAX_ZOOM}px, calc(70vh * ${nx / ny}))` }
      : { width: nx * zoom, flex: 'none' }

  return (
    <div className="viewport">
      <div className="viewer" style={{ ...size, aspectRatio: `${nx} / ${ny}` }}>
        <canvas
          ref={canvasRef}
          width={nx}
          height={ny}
          // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- the image is drawn on a canvas, which needs an explicit role
          role="img"
          aria-label={ariaLabel}
          onClick={handleClick}
        />
        {markers.map((m) => (
          <div
            key={m.id}
            className={`marker marker-${m.variant}`}
            title={m.title}
            style={percent(pixelToDisplay(m.px, image.shape))}
          />
        ))}
        {selectedPixel && <div className="crosshair" style={percent(pixelToDisplay(selectedPixel, image.shape))} />}
      </div>
    </div>
  )
}
