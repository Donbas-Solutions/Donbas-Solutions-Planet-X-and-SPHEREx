import AboutPage from './components/AboutPage'
import AppStateProvider from './components/AppStateProvider'
import EmbedView from './components/embed/EmbedView'
import MainLayout from './components/MainLayout'
import { useViewParams } from './hooks/useViewParams'
import { routeFromPath } from './lib/route'
import { sequenceSource, sourceKey } from './lib/urlState'

export default function App() {
  const route = routeFromPath(window.location.pathname)
  const { params, setParams, notices, notify, dismissNotices } = useViewParams()
  if (route === 'about') return <AboutPage />

  const source = sequenceSource(params, import.meta.env.BASE_URL)
  return (
    <AppStateProvider key={sourceKey(source)} params={params} setParams={setParams} notify={notify} source={source}>
      {route === 'embed' ? <EmbedView /> : <MainLayout notices={notices} onDismissNotices={dismissNotices} />}
    </AppStateProvider>
  )
}
