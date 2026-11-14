import { useMemo } from 'react'
import { useAppState } from '../hooks/useAppState'
import { flagMask } from '../lib/frames'
import BottomTabs from './BottomTabs'
import FramePanel from './FramePanel'
import LoadStatus from './LoadStatus'
import Notices from './Notices'
import PlayerControls from './PlayerControls'
import TopBar from './TopBar'
import Viewer from './Viewer'

const ZOOM = 5
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
      <Notices notices={notices} onDismiss={onDismissNotices} />
      <main className="stage">
        <LoadStatus />
        <Viewer zoom={ZOOM} overlayMask={overlayMask} />
        <PlayerControls />
      </main>
      <FramePanel
        showFlags={params.flags.length > 0}
        onShowFlagsChange={(show) => setParams({ flags: show ? DEFAULT_OVERLAY : [] })}
      />
      {sequence && <BottomTabs />}
    </div>
  )
}
