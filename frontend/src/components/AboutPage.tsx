import { routeHref } from '../lib/route'

export default function AboutPage() {
  return (
    <main className="about">
      <p>
        <a href={routeHref('main', window.location.search)}>← Back to the viewer</a>
      </p>
      <h1>About SPHEREx Blink</h1>
      <p>
        The viewer shows NASA SPHEREx images of one sky patch in time order. Objects that move or change brightness
        stand out when the frames are blinked.
      </p>
      <h2>Limitations</h2>
      <ul>
        <li>The pixel is 6.2″: motion of less than about one pixel per year is hard to see by eye.</li>
        <li>Saturated stars are marked as saturated and are not measured.</li>
        <li>
          WISE 0855−0714: its motion is seen in D5–D6, but its aperture is blended with a field star, so the flux
          we measure there is only an upper bound, not WISE 0855's own flux.
        </li>
        <li>This tool makes no claims about Planet Nine or Planet X.</li>
        <li>The expected-position marker uses catalog proper motion; parallax (≤ 0.55″) is ignored.</li>
      </ul>
      <h2>Data credits</h2>
      <p>SPHEREx data: NASA / Caltech-IPAC, via the NASA/IPAC Infrared Science Archive (IRSA).</p>
    </main>
  )
}
