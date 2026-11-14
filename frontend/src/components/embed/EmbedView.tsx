import { routeHref } from '../../lib/route'
import LoadStatus from '../LoadStatus'
import PlayerControls from '../PlayerControls'
import Viewer from '../Viewer'

export default function EmbedView() {
  const search = window.location.search
  return (
    <main className="embed">
      <LoadStatus />
      <Viewer zoom={4} overlayMask={0} />
      <PlayerControls />
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
