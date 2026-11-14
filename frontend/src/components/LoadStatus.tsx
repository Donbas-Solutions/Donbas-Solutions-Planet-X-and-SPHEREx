import { useAppState } from '../hooks/useAppState'

/** Loading and error states; renders nothing once the sequence is ready. */
export default function LoadStatus() {
  const { load, retry, source } = useAppState()
  switch (load.status) {
    case 'loading':
      return (
        <p className="muted" aria-live="polite">
          {load.message}
        </p>
      )
    case 'error':
      return (
        <div className="error" role="alert">
          <p>{load.message}</p>
          {source.kind === 'manifest' && (
            <button type="button" onClick={retry}>
              Retry
            </button>
          )}
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
