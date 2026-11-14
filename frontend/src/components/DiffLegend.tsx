import { BLUE_ORANGE, colormapCss } from '../lib/colormap'
import type { DiffImage } from '../lib/diff'

interface Props {
  diff: DiffImage
  range: number
}

const GRADIENT = colormapCss(BLUE_ORANGE)

export default function DiffLegend({ diff, range }: Props) {
  const r = range.toPrecision(2)
  return (
    <div className="diff-legend">
      <p>
        <strong>{diff.later.frame.label}</strong> minus <strong>{diff.earlier.frame.label}</strong>
      </p>
      <div className="legend-bar" style={{ background: GRADIENT }} aria-hidden="true" />
      <div className="legend-ticks muted" aria-hidden="true">
        <span>−{r}</span>
        <span>0</span>
        <span>+{r}</span>
      </div>
      <p className="muted">
        Orange: brighter in the later frame ({diff.later.frame.date_range[0]}). Blue: brighter in the earlier frame (
        {diff.earlier.frame.date_range[0]}). A blue–orange pair (dipole) is a source that moved; a single blob is a
        source that changed brightness.
      </p>
      {diff.warnings.length > 0 && (
        <ul className="warnings">
          {diff.warnings.map((w) => (
            <li key={w} className="warn">
              {w}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
