import { useAppState } from '../hooks/useAppState'
import { bitsInGroup, countFlagged, flagMask, GROUP_COLOR, GROUP_LABEL, OVERLAY_GROUPS } from '../lib/flags'
import type { OverlayGroup } from '../lib/urlState'

export default function FlagsPanel() {
  const { sequence, currentFrame, params, setParams } = useAppState()
  if (!sequence) return null
  const bits = sequence.flag_bits
  const isDiff = params.view === 'diff'

  const toggle = (group: OverlayGroup, on: boolean) => {
    const next = on ? [...params.flags, group] : params.flags.filter((g) => g !== group)
    setParams({ flags: OVERLAY_GROUPS.filter((g) => next.includes(g)) })
  }

  return (
    <section className="flags-panel" aria-labelledby="flags-heading">
      <h2 id="flags-heading">Flags overlay</h2>
      <ul className="flag-groups">
        {OVERLAY_GROUPS.map((g) => {
          const mask = flagMask(bits, [g])
          const count = !isDiff && currentFrame ? countFlagged(currentFrame.flags, mask) : null
          const [r, gr, b] = GROUP_COLOR[g]
          return (
            <li key={g}>
              <label>
                <input
                  type="checkbox"
                  checked={params.flags.includes(g)}
                  disabled={mask === 0}
                  onChange={(e) => toggle(g, e.target.checked)}
                />
                <span className="swatch" style={{ background: `rgb(${r} ${gr} ${b})` }} aria-hidden="true" />
                {GROUP_LABEL[g]}
                {count !== null && <span className="muted"> · {count} px</span>}
              </label>
            </li>
          )
        })}
      </ul>
      <p className="muted small">The overlay only tints pixels; the image values are unchanged.</p>
      <details>
        <summary>Flag bits</summary>
        {(['saturation', 'bad', 'artifact', 'info'] as const).map((g) => {
          const groupBits = bitsInGroup(bits, g)
          if (groupBits.length === 0) return null
          return (
            <div key={g} className="bit-group">
              <h3>{GROUP_LABEL[g]}</h3>
              {g === 'info' && (
                <p className="muted small">Not shown and never treated as bad: SOURCE marks every known star.</p>
              )}
              <dl className="meta">
                {groupBits.map((b) => (
                  <div key={b.bit} className="meta-row">
                    <dt>
                      {b.name} <span className="muted">(bit {b.bit})</span>
                    </dt>
                    <dd>{b.description}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )
        })}
      </details>
    </section>
  )
}
