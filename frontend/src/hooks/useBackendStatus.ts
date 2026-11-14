import { useEffect, useState } from 'react'
import { isBackendOnline } from '../api/sequence'

export type BackendStatus = 'checking' | 'online' | 'offline'

/** One /api/health check per page load: decides whether to show the offline banner (FR-14). */
export function useBackendStatus(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>('checking')
  useEffect(() => {
    const ac = new AbortController()
    isBackendOnline(ac.signal).then(
      (online) => setStatus(online ? 'online' : 'offline'),
      () => {},
    )
    return () => ac.abort()
  }, [])
  return status
}
