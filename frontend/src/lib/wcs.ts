import type { Grid, PixelPos } from '../api/types'

const RAD_PER_DEG = Math.PI / 180

function card(grid: Grid, key: string, fallback: number): number {
  const value = grid.wcs[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

/**
 * Gnomonic (TAN) projection of an ICRS position (degrees) onto the frame grid: 0-based pixel, row 0 = south,
 * x growing to the west. Null for a position on the far hemisphere.
 */
export function skyToPixel(grid: Grid, ra: number, dec: number): PixelPos | null {
  const centerPix = (grid.npix + 1) / 2
  const scaleDeg = grid.pixscale_arcsec / 3600
  const ra0 = card(grid, 'CRVAL1', grid.ra) * RAD_PER_DEG
  const dec0 = card(grid, 'CRVAL2', grid.dec) * RAD_PER_DEG
  const dRa = ra * RAD_PER_DEG - ra0
  const decRad = dec * RAD_PER_DEG
  const cosC = Math.sin(dec0) * Math.sin(decRad) + Math.cos(dec0) * Math.cos(decRad) * Math.cos(dRa)
  if (cosC <= 0) return null
  const eastDeg = (Math.cos(decRad) * Math.sin(dRa)) / cosC / RAD_PER_DEG
  const northDeg =
    (Math.cos(dec0) * Math.sin(decRad) - Math.sin(dec0) * Math.cos(decRad) * Math.cos(dRa)) / cosC / RAD_PER_DEG
  // FITS CRPIX is 1-based; CDELT1 is negative because east is to the left.
  return {
    x: card(grid, 'CRPIX1', centerPix) - 1 + eastDeg / card(grid, 'CDELT1', -scaleDeg),
    y: card(grid, 'CRPIX2', centerPix) - 1 + northDeg / card(grid, 'CDELT2', scaleDeg),
  }
}
