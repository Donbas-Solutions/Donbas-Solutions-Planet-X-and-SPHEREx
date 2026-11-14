interface Props {
  measured: number
  saturated: number
  flagged: number
  nonpositive: number
}

const R = 4

export default function StatusLegend({ measured, saturated, flagged, nonpositive }: Props) {
  return (
    <ul className="chart-legend" aria-label="Point types">
      <li>
        {measured} measured, with 1σ error bars
      </li>
      {saturated > 0 && (
        <li>
          <svg width={10} height={10} aria-hidden="true">
            <circle cx={5} cy={5} r={R} className="hollow" />
          </svg>
          {saturated} saturated (no value)
        </li>
      )}
      {flagged > 0 && (
        <li>
          <svg width={10} height={10} aria-hidden="true">
            <path d={`M1 1L9 9M1 9L9 1`} className="cross" />
          </svg>
          {flagged} masked by flags (no value)
        </li>
      )}
      {nonpositive > 0 && (
        <li>
          <svg width={10} height={10} aria-hidden="true">
            <path d="M1 1L9 1L5 9Z" className="hollow" />
          </svg>
          {nonpositive} at ≤ 0 µJy, not shown on the log axis
        </li>
      )}
    </ul>
  )
}
