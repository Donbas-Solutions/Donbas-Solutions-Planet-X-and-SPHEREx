import { lazy, Suspense, useState, type KeyboardEvent } from 'react'

const SpectrumPanel = lazy(() => import('./charts/SpectrumPanel'))
const LightCurvePanel = lazy(() => import('./charts/LightCurvePanel'))
const ContextPanel = lazy(() => import('./context/ContextPanel'))

const TABS = [
  { id: 'spectrum', label: 'Spectrum', Panel: SpectrumPanel },
  { id: 'lightcurve', label: 'Light curve', Panel: LightCurvePanel },
  { id: 'context', label: 'Context', Panel: ContextPanel },
] as const

type TabId = (typeof TABS)[number]['id']

export default function BottomTabs() {
  const [active, setActive] = useState<TabId>('spectrum')
  const current = TABS.find((t) => t.id === active) ?? TABS[0]

  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    const i = TABS.findIndex((t) => t.id === active)
    const next = TABS[(i + (e.key === 'ArrowRight' ? 1 : -1) + TABS.length) % TABS.length]
    if (!next) return
    e.preventDefault()
    setActive(next.id)
    document.getElementById(`tab-${next.id}`)?.focus()
  }

  return (
    <section className="tabs">
      <div role="tablist" aria-label="Analysis">
        {TABS.map((t) => (
          <button
            key={t.id}
            id={`tab-${t.id}`}
            type="button"
            role="tab"
            aria-selected={t.id === active}
            aria-controls={`panel-${t.id}`}
            tabIndex={t.id === active ? 0 : -1}
            onClick={() => setActive(t.id)}
            onKeyDown={handleKeyDown}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div id={`panel-${current.id}`} role="tabpanel" aria-labelledby={`tab-${current.id}`} className="tabpanel">
        <Suspense fallback={<p className="muted">Loading…</p>}>
          <current.Panel />
        </Suspense>
      </div>
    </section>
  )
}
