import { routeHref } from '../../lib/route'
import LoadStatus from '../LoadStatus'
import Player from '../Player'

export default function EmbedView() {
  const search = window.location.search
  return (
    <main className="embed">
      <LoadStatus />
      <Player overlayMask={0} isCompact />
      <p className="embed-links">
        <a href={routeHref('main', search)} target="_blank" rel="noopener noreferrer">
          Open in SPHEREx Blink
        </a>
        {' · '}
        <a href={routeHref('about')} target="_blank" rel="noopener noreferrer">
          Limitations
        </a>
      </p>
    </main>
  )
}
