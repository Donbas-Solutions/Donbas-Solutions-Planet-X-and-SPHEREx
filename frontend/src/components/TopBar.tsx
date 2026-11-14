import { useAppState } from '../hooks/useAppState'
import { routeHref } from '../lib/route'

export default function TopBar() {
  const { target, sequence } = useAppState()
  const search = window.location.search
  return (
    <header className="topbar">
      <h1>
        <a href={routeHref('main', search)}>SPHEREx Blink</a>
      </h1>
      <div className="topbar-search" />
      {target && (
        <span className="muted">
          {target.name ?? `${target.ra.toFixed(4)}, ${target.dec.toFixed(4)}`}
          {sequence?.meta.mock && <span className="badge">mock data</span>}
        </span>
      )}
      <nav aria-label="Pages">
        <a href={routeHref('about', search)}>About &amp; limitations</a>
      </nav>
    </header>
  )
}
