/**
 * The five challenge test targets. Copied from science/targets.json (SIMBAD J2000 + proper motion), which stays
 * the source of truth; never use the challenge-text coordinates here (WISE 0855's are epoch ≈2010.5).
 */
export const PRESETS = [
  { id: 'barnard', name: "Barnard's Star", test: 'motion', ra: 269.452077, dec: 4.693365, pmra: -801.551, pmdec: 10362.394 },
  { id: 'eps_ind_b', name: 'ε Indi B', test: 'motion', ra: 331.0441466, dec: -56.7828442, pmra: 3981.977, pmdec: -2466.832 },
  { id: 'wise0855', name: 'WISE 0855−0714', test: 'motion', ra: 133.8189082, dec: -7.247048, pmra: -8123.7, pmdec: 673.2 },
  { id: 'rw_aur', name: 'RW Aurigae', test: 'brightness', ra: 76.956526, dec: 30.4014382, pmra: 7.23, pmdec: -20.33 },
  { id: 'r_dra', name: 'R Draconis', test: 'brightness', ra: 248.1676108, dec: 66.7549794, pmra: -20.643, pmdec: 6.149 },
] as const

export const PRESET_EPOCH = 2000.0

export type Preset = (typeof PRESETS)[number]
export type PresetId = Preset['id']

export function findPreset(id: string): Preset | undefined {
  return PRESETS.find((p) => p.id === id)
}
