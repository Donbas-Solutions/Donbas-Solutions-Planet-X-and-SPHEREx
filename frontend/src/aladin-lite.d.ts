// aladin-lite ships without TypeScript types: only what this app calls is declared (checked against 3.8.2).
declare module 'aladin-lite' {
  export interface AladinOptions {
    survey: string
    fov: number
    target: string
    cooFrame: 'ICRS'
    showReticle?: boolean
    showLayersControl?: boolean
    showProjectionControl?: boolean
    showFrame?: boolean
    /** Usage ping to CDS; it throws in the console while CDS is down. */
    log?: boolean
  }

  export interface AladinSource {
    readonly ra: number
    readonly dec: number
  }

  export interface AladinCatalog {
    addSources(sources: AladinSource[]): void
    removeAll(): void
  }

  export interface AladinInstance {
    setImageSurvey(urlOrId: string): void
    gotoRaDec(ra: number, dec: number): void
    setFoV(fovDeg: number): void
    addCatalog(catalog: AladinCatalog): void
  }

  const A: {
    init: Promise<void>
    aladin(element: HTMLElement, options: AladinOptions): AladinInstance
    catalog(options: { name: string; sourceSize: number; color: string; shape: string }): AladinCatalog
    source(ra: number, dec: number, data?: Record<string, string>): AladinSource
  }
  export default A
}
