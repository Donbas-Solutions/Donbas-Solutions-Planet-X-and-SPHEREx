import { useCallback, useEffect, useRef, useState } from 'react'
import { parseViewParams, viewParamsToSearch, type ViewParams } from '../lib/urlState'

export type HistoryMode = 'replace' | 'push'
export type SetViewParams = (patch: Partial<ViewParams>, history?: HistoryMode) => void

/** The page URL is the single source of truth for view params; this hook mirrors it both ways. */
export function useViewParams(): {
  params: ViewParams
  setParams: SetViewParams
  notices: readonly string[]
  /** Shows one notice in the page banner; unlike component state it survives a change of the sequence. */
  notify: (text: string) => void
  dismissNotices: () => void
} {
  const [initial] = useState(() => parseViewParams(window.location.search))
  const [params, setParamsState] = useState(initial.params)
  const [notices, setNotices] = useState<readonly string[]>(initial.notices)
  const nextHistory = useRef<HistoryMode>('replace')

  useEffect(() => {
    const search = viewParamsToSearch(params)
    if (search === window.location.search) return
    const url = `${window.location.pathname}${search}${window.location.hash}`
    if (nextHistory.current === 'push') window.history.pushState(null, '', url)
    else window.history.replaceState(null, '', url)
    nextHistory.current = 'replace'
  }, [params])

  useEffect(() => {
    const handlePopState = () => {
      const parsed = parseViewParams(window.location.search)
      setParamsState(parsed.params)
      setNotices(parsed.notices)
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const setParams = useCallback<SetViewParams>((patch, history = 'replace') => {
    if (history === 'push') nextHistory.current = 'push'
    setParamsState((prev) => ({ ...prev, ...patch }))
  }, [])

  const dismissNotices = useCallback(() => setNotices([]), [])
  const notify = useCallback((text: string) => setNotices([text]), [])

  return { params, setParams, notices, notify, dismissNotices }
}
