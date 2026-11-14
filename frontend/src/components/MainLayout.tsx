import { useMemo } from 'react'
import { useAppState } from '../hooks/useAppState'
import { flagMask } from '../lib/frames'
import BottomTabs from './BottomTabs'
import FramePanel from './FramePanel'
import LoadStatus from './LoadStatus'
import Notices from './Notices'
import OfflineBanner from './OfflineBanner'
import Player from './Player'
import TopBar from './TopBar'

const DEFAULT_OVERLAY = ['bad', 'saturation'] as const

interface Props {
  notices: readonly string[]
  onDismissNotices: () => void
}

export default function MainLayout({ notices, onDismissNotices }: Props) {
  const { sequence, params, setParams } = useAppState()
  const overlayMask = useMemo(
    () => (sequence && params.flags.length > 0 ? flagMask(sequence.flag_bits, [...params.flags]) : 0),
    [sequence, params.flags],
  )

  return (
    <div className="layout">
      <TopBar />
      <div className="banners">
        <OfflineBanner />
        <Notices notices={notices} onDismiss={onDismissNotices} />
      </div>
      <main className="stage">
        <LoadStatus />
        <Player overlayMask={overlayMask} />
      </main>
      <FramePanel
        showFlags={params.flags.length > 0}
        onShowFlagsChange={(show) => setParams({ flags: show ? DEFAULT_OVERLAY : [] })}
      />
      {sequence && <BottomTabs />}
    </div>
  )
}
