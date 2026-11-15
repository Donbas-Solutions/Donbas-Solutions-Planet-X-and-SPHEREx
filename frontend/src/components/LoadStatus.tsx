import { useAppState } from '../hooks/useAppState'
import { hasPartialData } from '../lib/warnings'
import Landing from './Landing'

function stageLabel(stage: string): string {
  return stage ? stage[0]?.toUpperCase() + stage.slice(1) : ''
}

/** Every non-ready state of spec §5.2, plus the notices that go with a ready sequence. */
export default function LoadStatus() {
  const { load, retry, cancel, playlist, source } = useAppState()
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
      // Only the frames being blinked: other detectors' frames are not on screen.
      const shown = playlist.frames
      const partial = shown.filter((f) => hasPartialData(f.frame)).length
      if (!load.notice && partial === 0) return null
      // A notice means the live request fell back to a prebaked bundle: the frames are not live stacks then.
      const isLiveData = source.kind === 'live' && !load.notice
      return (
        <div className={load.notice ? 'status warn' : 'status note'} aria-live="polite">
          {load.notice && <p>{load.notice}</p>}
          {partial > 0 && partial === shown.length && (
            <p>
              Every frame shown stacks few exposures or samples only part of its wavelength band
              {isLiveData ? ': live requests take only a few exposures per detector and visit' : ''}. Motion still
              shows; compare brightness between frames with care.
            </p>
          )}
          {partial > 0 && partial < shown.length && (
            <p>
              {partial} of the {shown.length} frames shown {partial === 1 ? 'comes from a visit' : 'come from visits'}{' '}
              in which SPHEREx took fewer exposures or covered less of the wavelength band than in the fullest visit
              (see the frame details). Motion still shows; compare brightness between frames with care.
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
