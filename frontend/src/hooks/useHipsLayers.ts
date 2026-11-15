import { useEffect, useState } from 'react'
import { HIPS_LAYERS, isHipsUp } from '../lib/hips'

export type HipsStatus = 'checking' | 'up' | 'down'

/** Which image servers answer right now, by layer id; checked once when the panel opens. */
export function useHipsLayers(): Readonly<Record<string, HipsStatus>> {
  const [status, setStatus] = useState<Readonly<Record<string, HipsStatus>>>({})

  useEffect(() => {
    const ac = new AbortController()
    for (const layer of HIPS_LAYERS) {
      void isHipsUp(layer, ac.signal).then((isUp) => {
        if (!ac.signal.aborted) setStatus((prev) => ({ ...prev, [layer.id]: isUp ? 'up' : 'down' }))
      })
    }
    return () => ac.abort()
  }, [])

  return status
}
