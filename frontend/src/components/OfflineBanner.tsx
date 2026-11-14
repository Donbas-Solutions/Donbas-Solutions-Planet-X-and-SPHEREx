import { useBackendStatus } from '../hooks/useBackendStatus'

export default function OfflineBanner() {
  const status = useBackendStatus()
  if (status !== 'offline') return null
  return (
    <p className="offline-banner" role="note">
      <strong>Offline mode — test targets only.</strong> The live SPHEREx archive search is unavailable; the five test
      targets still work from prebaked data.
    </p>
  )
}
