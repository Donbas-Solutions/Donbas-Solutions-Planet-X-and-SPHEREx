import { useId, useState, type FormEvent } from 'react'
import { useAppState } from '../hooks/useAppState'
import { formatDegrees, looksLikeCoordinates, parseCoordinates } from '../lib/coords'
import { clampFov, DETECTOR_IDS, FOV_MAX_ARCMIN, FOV_MIN_ARCMIN, parseViewParams, type ViewParams } from '../lib/urlState'

const NEW_TARGET: Partial<ViewParams> = { target: null, manifest: null, pm: null, a: null, b: null }

export default function SearchBar() {
  const { params, setParams } = useAppState()
  const [message, setMessage] = useState<{ kind: 'error' | 'note'; text: string } | null>(null)
  const messageId = useId()

  const initialQuery =
    params.name ?? (params.ra !== null && params.dec !== null ? `${formatDegrees(params.ra)} ${formatDegrees(params.dec)}` : '')
  const detValue = params.det === 'all' ? 'all' : params.det.length === 1 ? String(params.det[0]) : 'custom'

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    const query = String(form.get('q') ?? '').trim()
    const fovInput = Number(form.get('fov'))
    if (!query) return setMessage({ kind: 'error', text: 'Enter an object name or RA Dec coordinates.' })
    if (!Number.isFinite(fovInput)) return setMessage({ kind: 'error', text: 'Field of view must be a number.' })

    const fovArcmin = clampFov(fovInput)
    const fovNote =
      fovArcmin === fovInput ? null : `Field of view limited to ${FOV_MIN_ARCMIN}–${FOV_MAX_ARCMIN}′; using ${fovArcmin}′.`

    const coords = looksLikeCoordinates(query) ? parseCoordinates(query) : null
    if (coords?.ok) {
      setParams({ ...NEW_TARGET, name: null, ra: coords.value.ra, dec: coords.value.dec, fovArcmin }, 'push')
    } else if (/\p{L}/u.test(query)) {
      setParams({ ...NEW_TARGET, name: query, ra: null, dec: null, fovArcmin }, 'push')
    } else {
      return setMessage({ kind: 'error', text: coords?.error ?? 'Enter an object name or RA Dec coordinates.' })
    }
    setMessage(fovNote ? { kind: 'note', text: fovNote } : null)
  }

  const handleDetChange = (value: string) => {
    if (value === 'custom') return
    setParams({ det: parseViewParams(`?det=${value}`).params.det, a: null, b: null })
  }

  return (
    <form className="search" onSubmit={handleSubmit} noValidate>
      <label className="search-query">
        <span className="visually-hidden">Object name or RA Dec</span>
        <input
          name="q"
          type="search"
          defaultValue={initialQuery}
          placeholder="Name or RA Dec, e.g. 17 57 48.5 +04 41 36"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={message?.kind === 'error'}
          aria-describedby={messageId}
        />
      </label>
      <label>
        FOV
        <input
          name="fov"
          type="number"
          min={FOV_MIN_ARCMIN}
          max={FOV_MAX_ARCMIN}
          step={1}
          defaultValue={params.fovArcmin}
          className="fov"
        />
        ′
      </label>
      <label>
        Detectors
        <select value={detValue} onChange={(e) => handleDetChange(e.target.value)}>
          <option value="all">All combined</option>
          {DETECTOR_IDS.map((d) => (
            <option key={d} value={d}>
              D{d}
            </option>
          ))}
          {detValue === 'custom' && params.det !== 'all' && (
            <option value="custom">{params.det.map((d) => `D${d}`).join('+')}</option>
          )}
        </select>
      </label>
      <button type="submit">Show</button>
      <p id={messageId} className={message?.kind === 'error' ? 'error search-message' : 'muted search-message'} aria-live="polite">
        {message?.text}
      </p>
    </form>
  )
}
