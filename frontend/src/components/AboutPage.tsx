import { GLOSSARY, type TermId } from '../lib/glossary'
import { routeHref } from '../lib/route'

const TERMS: readonly TermId[] = ['visit', 'detector', 'dipole', 'saturated', 'proper_motion']

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

      <h2>How to read a blink</h2>
      <ul>
        <li>
          Each frame is one visit: all exposures of a few weeks stacked together, for one detector or for all
          detectors combined. Frames of different detectors are never blinked together, because each detector sees a
          different wavelength range.
        </li>
        <li>
          All frames share one brightness scale, so a star that looks brighter in one frame really is brighter there.
        </li>
        <li>
          The marker shows where the target is expected from its catalog proper motion at each frame’s date. It is
          a prediction, not a detection.
        </li>
        <li>
          Click a pixel to read its value in every shown frame. Flagged pixels can be tinted: yellow saturated, red
          bad data, cyan artifacts.
        </li>
      </ul>

      <h2>How to read a difference</h2>
      <p>
        The difference view subtracts the earlier of the two chosen frames (A and B) from the later one, pixel by
        pixel. Orange means brighter later, blue brighter earlier, grey no change.
      </p>
      <ul>
        <li>A blue spot next to an orange spot (a dipole) is a source that moved, from blue to orange.</li>
        <li>A single orange or blue blob is a source that changed brightness.</li>
        <li>
          If the two frames cover different wavelengths (a visit missing some detectors, or few exposures), part of
          the difference may be spectral; the viewer then shows a warning.
        </li>
      </ul>

      <h2>Limitations</h2>
      <ul>
        <li>
          The pixel is 6.2″. Even the fastest stars move about one or two pixels between the first and the last
          visit (Barnard’s Star ≈ 1.8 px, ε Indi B ≈ 1.1 px): smaller motion is hard to see by eye; use the
          difference view.
        </li>
        <li>
          Saturated stars (Barnard’s Star, R Dra, RW Aur in most bands) are marked as saturated and are not measured.
        </li>
        <li>
          WISE 0855−0714: its motion is seen in D5–D6, but its aperture is blended with a field star, so the flux
          we measure there is only an upper bound, not WISE 0855’s own flux.
        </li>
        <li>
          Live requests stack at most 8 exposures per detector and visit, so their wavelength coverage is
          incomplete and marked as such; the five test targets use fuller, prebaked stacks.
        </li>
        <li>
          Positions stay in ICRS with proper motion only; parallax (≤ 0.55″, under 0.1 px) is ignored.
        </li>
        <li>This tool makes no claims about Planet Nine or Planet X.</li>
      </ul>

      <h2>Terms</h2>
      <dl className="glossary">
        {TERMS.map((id) => (
          <div key={id}>
            <dt>{GLOSSARY[id].term}</dt>
            <dd>{GLOSSARY[id].text}</dd>
          </div>
        ))}
      </dl>

      <h2>Data credits</h2>
      <p>SPHEREx data: NASA / Caltech-IPAC, via the NASA/IPAC Infrared Science Archive (IRSA).</p>
      <p>Name resolution: SIMBAD (CDS, Strasbourg, and its Harvard mirror).</p>
    </main>
  )
}
