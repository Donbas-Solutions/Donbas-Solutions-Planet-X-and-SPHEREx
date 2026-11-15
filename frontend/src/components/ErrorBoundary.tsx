import { Component, type ErrorInfo, type ReactNode } from 'react'
import { routeHref } from '../lib/route'

interface Props {
  children: ReactNode
}

interface State {
  hasFailed: boolean
}

/** Keeps a rendering error from blanking the page. React offers error boundaries only as class components. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasFailed: false }

  static getDerivedStateFromError(): State {
    return { hasFailed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('The viewer failed to render', error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.hasFailed) return this.props.children
    return (
      <main className="about" role="alert">
        <h1>SPHEREx Blink</h1>
        <p className="error">Something went wrong while drawing this view.</p>
        <p>
          <a href={window.location.href}>Reload this view</a> or <a href={routeHref('main')}>start over</a>.
        </p>
      </main>
    )
  }
}
