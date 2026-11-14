import { useAppState } from '../../hooks/useAppState'
import AladinPanel from '../AladinPanel'

export default function ContextPanel() {
  const { sequence } = useAppState()
  if (!sequence) return null
  return <AladinPanel ra={sequence.grid.ra} dec={sequence.grid.dec} fovDeg={(sequence.grid.fov_arcmin / 60) * 3} />
}
