export type TermId = 'visit' | 'detector' | 'dipole' | 'saturated' | 'proper_motion'

export const GLOSSARY: Record<TermId, { term: string; text: string }> = {
  visit: {
    term: 'Visit',
    text:
      'A few weeks when SPHEREx scans the same patch of sky, about every six months. ' +
      'All exposures of one visit are stacked into one frame. Deep fields near the poles are split into 30-day bins.',
  },
  detector: {
    term: 'Detector',
    text:
      'SPHEREx has six detectors, D1 (0.75–1.11 µm) to D6 (4.42–5.00 µm). ' +
      'Each sees a different wavelength range, so only frames of the same detectors are compared.',
  },
  dipole: {
    term: 'Dipole',
    text:
      'A blue spot next to an orange spot in the difference image: the source was at the blue place earlier ' +
      'and at the orange place later, so it moved.',
  },
  saturated: {
    term: 'Saturated',
    text:
      'The star is too bright for the detector: its pixels are clipped or non-linear. ' +
      'They are marked, and no brightness or position is measured from them.',
  },
  proper_motion: {
    term: 'Proper motion',
    text:
      'How fast a star moves across the sky, in milliarcseconds per year. ' +
      'The expected-position marker moves the catalog position by it to each frame’s date.',
  },
}
