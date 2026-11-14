import { useAppState } from '../hooks/useAppState'
import { hasPartialData } from '../lib/warnings'
import Landing from './Landing'

function stageLabel(stage: string): string {
  return stage ? stage[0]?.toUpperCase() + stage.slice(1) : ''
}

/** Every non-ready state of spec §5.2, plus the notices that go with a ready sequence. */
export default function LoadStatus() {
  const { load, retry, cancel, frames, source } = useAppState()
  switch (load.status) {
    case 'idle':
      return <Landing />
    case 'loading': {
      const { progress } = load
      return (
        <div className="status" aria-live="polite">
          <p>
            {load.message}
            {progress && (
              <>
                {' '}
                {stageLabel(progress.stage)}
                {progress.total > 0 && ` ${progress.done} / ${progress.total}`}
              </>
            )}
          </p>
          {progress && progress.total > 0 ? (
            <progress value={progress.done} max={progress.total} />
          ) : (
            <progress aria-label="Working" />
          )}
          {load.canCancel && (
            <button type="button" onClick={cancel}>
              Cancel
            </button>
          )}
        </div>
      )
    }
    case 'empty':
      return (
        <div className="status" aria-live="polite">
          <p>{load.message}</p>
        </div>
      )
    case 'error':
      return (
        <div className="status error" role="alert">
          <p>{load.message}</p>
          <p className="muted">The test targets above work without the live archive.</p>
          {load.canRetry && (
            <button type="button" onClick={retry}>
              Retry
            </button>
          )}
        </div>
      )
    case 'cancelled':
      return (
        <div className="status" aria-live="polite">
          <p>Request cancelled.</p>
          <button type="button" onClick={retry}>
            Start again
          </button>
        </div>
      )
    case 'ready': {
      const partial = frames.filter((f) => hasPartialData(f.frame)).length
      if (!load.notice && partial === 0) return null
      // A notice means the live request fell back to a prebaked bundle: the frames are not live stacks then.
      const isLiveData = source.kind === 'live' && !load.notice
      return (
        <div className="status warn" aria-live="polite">
          {load.notice && <p>{load.notice}</p>}
          {partial > 0 && partial === frames.length && (
            <p>
              Every frame has few exposures or incomplete wavelength coverage
              {isLiveData ? ': live requests stack only a few exposures per detector and visit' : ''}. Motion still
              shows; compare brightness with care.
            </p>
          )}
          {partial > 0 && partial < frames.length && (
            <p>
              Partial data: {partial} of {frames.length} frames have few exposures or incomplete wavelength coverage
              (see the frame details).
            </p>
          )}
        </div>
      )
    }
    default: {
      const never: never = load
      return never
    }
  }
}
