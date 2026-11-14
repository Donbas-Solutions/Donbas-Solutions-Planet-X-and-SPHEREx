import { useEffect, useRef } from 'react'

interface Props {
  ra: number
  dec: number
  fovDeg: number
  survey?: string
}

/** Context view. Loaded lazily: aladin-lite (WASM) is a separate chunk. */
export default function AladinPanel({ ra, dec, fovDeg, survey = 'CDS/P/SPHEREx/QR2/color' }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    let cancelled = false
    import('aladin-lite').then(async ({ default: A }) => {
      await A.init
      if (cancelled) return
      A.aladin(el, { survey, fov: fovDeg, target: `${ra} ${dec}`, cooFrame: 'ICRS', showReticle: true })
    })
    return () => {
      cancelled = true
      el.innerHTML = ''
    }
  }, [ra, dec, fovDeg, survey])

  return <div ref={ref} className="aladin" />
}
