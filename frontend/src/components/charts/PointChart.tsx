import { useMemo, useRef, useState, type PointerEvent } from 'react'
import { extent, formatTick, makeScale, pad, type ScaleKind } from '../../lib/chart'
import type { PointStatus } from '../../lib/spectrum'
import { useElementWidth } from './useElementWidth'
import './charts.css'

export interface ChartPoint {
  key: string
  x: number
  /** null = no value (saturated or masked): drawn in the strip under the plot, never on the flux axis. */
  y: number | null
  err: number | null
  status: PointStatus
  /** Palette slot 0–2; null = not a coloured series. */
  slot: number | null
  tooltip: readonly string[]
}

export interface ChartBand {
  from: number
  to: number
  label: string
}

interface Props {
  points: readonly ChartPoint[]
  xDomain: readonly [number, number]
  xLabel: string
  yLabel: string
  yScale: ScaleKind
  bands?: readonly ChartBand[]
  ariaLabel: string
  formatX?: (v: number) => string
}

type Marker = 'series' | 'saturated' | 'flagged' | 'nonpositive'

interface Drawn {
  key: string
  cx: number
  cy: number
  marker: Marker
  slot: number | null
  errTop: number | null
  errBottom: number | null
  tooltip: readonly string[]
}

const HEIGHT = 320
const MARGIN = { left: 64, right: 16, top: 24 }
const PLOT_BOTTOM = HEIGHT - 72
const STRIP_Y = HEIGHT - 52
const HIT_RADIUS = 14

function yDomain(points: readonly ChartPoint[], kind: ScaleKind): [number, number] | null {
  if (kind === 'log') {
    const lows = extent(points.flatMap((p) => (p.y !== null && p.y > 0 ? [p.y] : [])))
    const highs = extent(points.flatMap((p) => (p.y !== null && p.y > 0 ? [p.y + (p.err ?? 0)] : [])))
    return lows && highs ? [lows[0] / 1.5, highs[1] * 1.5] : null
  }
  const ends = extent(points.flatMap((p) => (p.y === null ? [] : [p.y - (p.err ?? 0), p.y + (p.err ?? 0), 0])))
  return ends ? pad(ends, 0.05) : null
}

export default function PointChart({
  points,
  xDomain,
  xLabel,
  yLabel,
  yScale,
  bands = [],
  ariaLabel,
  formatX = formatTick,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const width = Math.max(useElementWidth(wrapRef, 640), 280)
  const [hoverKey, setHoverKey] = useState<string | null>(null)

  const { x, y, drawn } = useMemo(() => {
    const x = makeScale('linear', xDomain, [MARGIN.left, width - MARGIN.right], Math.max(Math.floor(width / 90), 3))
    const yd = yDomain(points, yScale)
    const y = yd ? makeScale(yScale, yd, [PLOT_BOTTOM, MARGIN.top]) : null
    const clampY = (v: number) => Math.min(Math.max(v, MARGIN.top), PLOT_BOTTOM)
    const drawn: Drawn[] = points.map((p) => {
      const cx = x.map(p.x)
      const plottable = y !== null && p.y !== null && (yScale === 'linear' || p.y > 0)
      if (!plottable || p.y === null || y === null) {
        const marker: Marker = p.status === 'measured' ? 'nonpositive' : p.status
        return { key: p.key, cx, cy: STRIP_Y, marker, slot: null, errTop: null, errBottom: null, tooltip: p.tooltip }
      }
      const err = p.err ?? 0
      const low = p.y - err
      return {
        key: p.key,
        cx,
        cy: y.map(p.y),
        marker: 'series',
        slot: p.slot,
        errTop: err > 0 ? clampY(y.map(p.y + err)) : null,
        errBottom: err > 0 ? (yScale === 'log' && low <= 0 ? PLOT_BOTTOM : clampY(y.map(low))) : null,
        tooltip: p.tooltip,
      }
    })
    return { x, y, drawn }
  }, [points, xDomain, yScale, width])

  const hovered = drawn.find((d) => d.key === hoverKey) ?? null

  const handlePointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const k = box.width > 0 ? width / box.width : 1
    const px = (e.clientX - box.left) * k
    const py = (e.clientY - box.top) * k
    let best: Drawn | null = null
    let bestDist = HIT_RADIUS
    for (const d of drawn) {
      const dist = Math.hypot(d.cx - px, d.cy - py)
      if (dist < bestDist) {
        best = d
        bestDist = dist
      }
    }
    setHoverKey(best?.key ?? null)
  }

  const plotRight = width - MARGIN.right
  const hasStrip = drawn.some((d) => d.marker !== 'series')

  return (
    <div ref={wrapRef} className="point-chart">
      <svg
        viewBox={`0 0 ${width} ${HEIGHT}`}
        // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- an inline SVG chart needs an explicit role to be announced as one image
        role="img"
        aria-label={ariaLabel}
        onPointerMove={handlePointerMove}
        onPointerLeave={() => setHoverKey(null)}
      >
        {bands.map((b, i) => (
          <g key={`${b.from}:${i}`} className={i % 2 === 0 ? 'band band-even' : 'band'}>
            <rect x={x.map(b.from)} y={MARGIN.top} width={Math.max(x.map(b.to) - x.map(b.from), 1)} height={PLOT_BOTTOM - MARGIN.top} />
            {b.label && (
              <text x={(x.map(b.from) + x.map(b.to)) / 2} y={MARGIN.top - 8} textAnchor="middle">
                {b.label}
              </text>
            )}
          </g>
        ))}

        {y?.ticks.map((t) => (
          <g key={t} className="tick">
            <line x1={MARGIN.left} x2={plotRight} y1={y.map(t)} y2={y.map(t)} className={t === 0 ? 'zero' : 'grid'} />
            <text x={MARGIN.left - 6} y={y.map(t)} textAnchor="end" dominantBaseline="middle">
              {formatTick(t)}
            </text>
          </g>
        ))}
        {!y && (
          <text x={(MARGIN.left + plotRight) / 2} y={(MARGIN.top + PLOT_BOTTOM) / 2} textAnchor="middle" className="empty">
            No measured fluxes to plot
          </text>
        )}

        <line x1={MARGIN.left} x2={plotRight} y1={PLOT_BOTTOM} y2={PLOT_BOTTOM} className="axis" />
        {x.ticks.map((t) => (
          <text key={t} x={x.map(t)} y={HEIGHT - 26} textAnchor="middle" className="tick-label">
            {formatX(t)}
          </text>
        ))}
        <text x={(MARGIN.left + plotRight) / 2} y={HEIGHT - 6} textAnchor="middle" className="axis-title">
          {xLabel}
        </text>
        <text
          transform={`translate(14 ${(MARGIN.top + PLOT_BOTTOM) / 2}) rotate(-90)`}
          textAnchor="middle"
          className="axis-title"
        >
          {yLabel}
        </text>
        {hasStrip && (
          <text x={MARGIN.left - 6} y={STRIP_Y} textAnchor="end" dominantBaseline="middle" className="tick-label">
            no value
          </text>
        )}

        {drawn.map((d) => (
          <g key={d.key} className={d.slot === null ? 'mark' : `mark series-${d.slot + 1}`}>
            {d.errTop !== null && d.errBottom !== null && (
              <line x1={d.cx} x2={d.cx} y1={d.errTop} y2={d.errBottom} className="err" />
            )}
            <MarkerShape d={d} isHovered={d.key === hoverKey} />
          </g>
        ))}
      </svg>
      {hovered && (
        <div
          className="chart-tooltip"
          style={{ left: Math.min(hovered.cx + 12, width - 200), top: Math.max(hovered.cy - 12, 0) }}
          aria-hidden="true"
        >
          {hovered.tooltip.map((line) => (
            <div key={line}>{line}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function MarkerShape({ d, isHovered }: { d: Drawn; isHovered: boolean }) {
  const r = isHovered ? 6 : 4
  switch (d.marker) {
    case 'series':
      return <circle cx={d.cx} cy={d.cy} r={r} className="dot" />
    case 'saturated':
      return <circle cx={d.cx} cy={d.cy} r={r} className="hollow" />
    case 'flagged':
      return <path d={`M${d.cx - r} ${d.cy - r}L${d.cx + r} ${d.cy + r}M${d.cx - r} ${d.cy + r}L${d.cx + r} ${d.cy - r}`} className="cross" />
    case 'nonpositive':
      return <path d={`M${d.cx - r} ${d.cy - r}L${d.cx + r} ${d.cy - r}L${d.cx} ${d.cy + r}Z`} className="hollow" />
  }
}
