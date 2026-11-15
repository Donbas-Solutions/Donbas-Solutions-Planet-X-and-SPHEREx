import { useEffect, useRef } from 'react'
import type { AladinCatalog, AladinInstance } from 'aladin-lite'

export interface SkyMarker {
  id: string
  /** ICRS degrees */
  ra: number
  dec: number
}

interface Props {
  ra: number
  dec: number
  fovDeg: number
  /** HiPS root URL */
  surveyUrl: string
  markers: readonly SkyMarker[]
  markerLabel: string
}

interface Handle {
  aladin: AladinInstance
  catalog: AladinCatalog
  add: (markers: readonly SkyMarker[]) => void
}

/** Context view. Loaded lazily: aladin-lite (WASM) is a separate chunk. The instance is created once per mount. */
export default function AladinPanel({ ra, dec, fovDeg, surveyUrl, markers, markerLabel }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const handle = useRef<Handle | null>(null)
  const latest = useRef({ ra, dec, fovDeg, surveyUrl, markers, markerLabel })

  useEffect(() => {
    latest.current = { ra, dec, fovDeg, surveyUrl, markers, markerLabel }
  })

  useEffect(() => {
    const el = ref.current
    if (!el) return
    let cancelled = false
    void import('aladin-lite').then(async ({ default: A }) => {
      await A.init
      if (cancelled) return
      const now = latest.current
      const aladin = A.aladin(el, {
        survey: now.surveyUrl,
        fov: now.fovDeg,
        target: `${now.ra} ${now.dec}`,
        cooFrame: 'ICRS',
        showReticle: true,
        showLayersControl: false,
        showProjectionControl: false,
        showFrame: false,
        log: false,
      })
      const catalog = A.catalog({ name: now.markerLabel, sourceSize: 10, color: '#b9f6ca', shape: 'rhomb' })
      aladin.addCatalog(catalog)
      const add = (list: readonly SkyMarker[]) => catalog.addSources(list.map((m) => A.source(m.ra, m.dec, { id: m.id })))
      add(now.markers)
      handle.current = { aladin, catalog, add }
    })
    return () => {
      cancelled = true
      handle.current = null
      el.innerHTML = ''
    }
  }, [])

  useEffect(() => {
    handle.current?.aladin.setImageSurvey(surveyUrl)
  }, [surveyUrl])

  useEffect(() => {
    handle.current?.aladin.gotoRaDec(ra, dec)
    handle.current?.aladin.setFoV(fovDeg)
  }, [ra, dec, fovDeg])

  useEffect(() => {
    const h = handle.current
    if (!h) return
    h.catalog.removeAll()
    h.add(markers)
  }, [markers])

  return <div ref={ref} className="aladin" />
}
