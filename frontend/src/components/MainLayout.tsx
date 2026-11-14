import { useMemo, useState } from 'react'
import { useAppState } from '../hooks/useAppState'
import { flagMask } from '../lib/frames'
import BottomTabs from './BottomTabs'
import FramePanel from './FramePanel'
import LoadStatus from './LoadStatus'
import PlayerControls from './PlayerControls'
import TopBar from './TopBar'
import Viewer from './Viewer'

const ZOOM = 5

export default function MainLayout() {
  const { sequence } = useAppState()
  const [showFlags, setShowFlags] = useState(false)
  const overlayMask = useMemo(
    () => (sequence && showFlags ? flagMask(sequence.flag_bits, ['bad', 'saturation']) : 0),
    [sequence, showFlags],
  )

  return (
    <div className="layout">
      <TopBar />
      <main className="stage">
        <LoadStatus />
        <Viewer zoom={ZOOM} overlayMask={overlayMask} />
        <PlayerControls />
      </main>
      <FramePanel showFlags={showFlags} onShowFlagsChange={setShowFlags} />
      {sequence && <BottomTabs />}
    </div>
  )
}
