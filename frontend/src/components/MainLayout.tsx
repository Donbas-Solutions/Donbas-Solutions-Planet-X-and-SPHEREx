import { useAppState } from '../hooks/useAppState'
import BottomTabs from './BottomTabs'
import FramePanel from './FramePanel'
import LoadStatus from './LoadStatus'
import Notices from './Notices'
import OfflineBanner from './OfflineBanner'
import Player from './Player'
import TopBar from './TopBar'

interface Props {
  notices: readonly string[]
  onDismissNotices: () => void
}

export default function MainLayout({ notices, onDismissNotices }: Props) {
  const { sequence } = useAppState()
  return (
    <div className="layout">
      <TopBar />
      <div className="banners">
        <OfflineBanner />
        <Notices notices={notices} onDismiss={onDismissNotices} />
      </div>
      <main className="stage">
        <LoadStatus />
        <Player />
      </main>
      <FramePanel />
      {sequence && <BottomTabs />}
    </div>
  )
}
