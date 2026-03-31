import { 
  Bike, 
  Activity,
  Footprints,
  Dumbbell,
  Waves
} from 'lucide-react'

interface Props {
  sport?: string
  size?: number
  className?: string
}

export default function SportIcon({ sport, size = 16, className }: Props) {
  const s = sport?.toLowerCase() || 'cycling'
  if (s === 'running' || s === 'run' || s === 'walking' || s === 'walk' || s === 'hiking' || s === 'hike') {
    return <Footprints size={size} className={className} />
  }
  if (s === 'swimming' || s === 'swim') {
    return <Waves size={size} className={className} />
  }
  if (s === 'strength_training' || s === 'strength' || s === 'gym' || s === 'weight_lifting' || s === 'fitness_equipment') {
    return <Dumbbell size={size} className={className} />
  }
  if (s === 'cycling' || s === 'bike' || s === 'virtualride' || s === 'mountainbikeride') {
    return <Bike size={size} className={className} />
  }
  return <Activity size={size} className={className} />
}
