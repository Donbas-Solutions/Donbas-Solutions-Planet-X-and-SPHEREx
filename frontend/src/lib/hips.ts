export interface HipsLayer {
  id: string
  label: string
  /** HiPS root URL; `<url>/properties` answers when the server is up. */
  url: string
  /** What the user should know before comparing it with the SPHEREx frames. */
  note: string
}

const IRSA_HIPS = 'https://irsa.ipac.caltech.edu/data/hips/CDS'

/**
 * In order of preference. The SPHEREx mosaic exists only at CDS, whose HiPS servers were down on 2026-11-14/15;
 * the IRSA mirror of the other surveys answered throughout.
 */
export const HIPS_LAYERS: readonly HipsLayer[] = [
  {
    id: 'spherex',
    label: 'SPHEREx colour mosaic',
    url: 'https://alasky.cds.unistra.fr/SPHEREx/color',
    note: 'A colour mosaic of SPHEREx quick-release data, served by CDS.',
  },
  {
    id: '2mass',
    label: '2MASS colour (J, H, K)',
    url: `${IRSA_HIPS}/2MASS/Color`,
    note: 'Near-infrared images from 1997–2001: a fast star sits where it was then, not where SPHEREx sees it.',
  },
  {
    id: 'allwise',
    label: 'AllWISE colour (W4, W2, W1)',
    url: `${IRSA_HIPS}/AllWISE/RGB-W4-W2-W1`,
    note: 'Mid-infrared images from 2010: a fast star sits where it was then, not where SPHEREx sees it.',
  },
  {
    id: 'dss2',
    label: 'DSS2 colour (optical)',
    url: `${IRSA_HIPS}/DSS2/color`,
    note: 'Optical photographic plates from the 1980s–1990s.',
  },
]

const PROBE_TIMEOUT_MS = 8000

export async function isHipsUp(layer: HipsLayer, signal: AbortSignal): Promise<boolean> {
  const timeout = AbortSignal.timeout(PROBE_TIMEOUT_MS)
  try {
    const res = await fetch(`${layer.url}/properties`, { signal: AbortSignal.any([signal, timeout]) })
    return res.ok && (await res.text()).includes('hips_')
  } catch {
    return false
  }
}
