import { useAppState } from '../hooks/useAppState'

/** Loading and error states; renders nothing once the sequence is ready. */
export default function LoadStatus() {
  const { load, retry, manifestUrl } = useAppState()
  switch (load.status) {
    case 'loading':
      return (
        <p className="muted" aria-live="polite">
          Loading {manifestUrl}…
        </p>
      )
    case 'error':
      return (
        <div className="error" role="alert">
          <p>Could not load the sequence: {load.message}</p>
          <button type="button" onClick={retry}>
            Retry
          </button>
        </div>
      )
    case 'ready':
      return null
    default: {
      const never: never = load
      return never
    }
  }
}
