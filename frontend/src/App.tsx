import AboutPage from './components/AboutPage'
import AppStateProvider from './components/AppStateProvider'
import EmbedView from './components/embed/EmbedView'
import MainLayout from './components/MainLayout'
import { routeFromPath } from './lib/route'

const DEFAULT_MANIFEST = '/mock/sequence.json'

export default function App() {
  const route = routeFromPath(window.location.pathname)
  if (route === 'about') return <AboutPage />

  const manifestUrl = new URLSearchParams(window.location.search).get('manifest') ?? DEFAULT_MANIFEST
  return (
    <AppStateProvider key={manifestUrl} manifestUrl={manifestUrl}>
      {route === 'embed' ? <EmbedView /> : <MainLayout />}
    </AppStateProvider>
  )
}
