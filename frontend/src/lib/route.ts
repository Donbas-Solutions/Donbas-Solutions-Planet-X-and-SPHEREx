export type Route = 'main' | 'embed' | 'about'

const BASE = import.meta.env.BASE_URL

export function routeFromPath(pathname: string): Route {
  const rest = pathname.startsWith(BASE) ? pathname.slice(BASE.length) : pathname
  switch (rest.replace(/^\/+|\/+$/g, '')) {
    case 'embed':
      return 'embed'
    case 'about':
      return 'about'
    default:
      return 'main'
  }
}

/** Page URL for a route; `search` is the query string including its leading `?` (or empty). */
export function routeHref(route: Route, search = ''): string {
  return `${BASE}${route === 'main' ? '' : route}${search}`
}
