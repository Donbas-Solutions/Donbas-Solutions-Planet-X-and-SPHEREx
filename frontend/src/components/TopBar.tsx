import { useAppState } from '../hooks/useAppState'
import { formatDegrees } from '../lib/coords'
import { routeHref } from '../lib/route'
import CopyLinkButton from './CopyLinkButton'
import Presets from './Presets'
import SearchBar from './SearchBar'

export default function TopBar() {
  const { target, sequence } = useAppState()
  const search = window.location.search
  return (
    <header className="topbar">
      <div className="topbar-row">
        <h1>
          <a href={routeHref('main')}>SPHEREx Blink</a>
        </h1>
        {target && (
          <span className="muted">
            {target.name ?? `RA ${formatDegrees(target.ra)}°, Dec ${formatDegrees(target.dec)}°`}
            {sequence?.meta.mock && <span className="badge">mock data</span>}
          </span>
        )}
        <span className="spacer" />
        <CopyLinkButton />
        <a href={routeHref('about', search)}>About &amp; limitations</a>
      </div>
      <SearchBar />
      <Presets />
    </header>
  )
}
