import type { OrderRouteProfile } from '../types'

export const ORDER_ROUTE_PROFILES: {
  id: OrderRouteProfile
  letter: string
  label: string
}[] = [
  { id: 'driving', letter: 'А', label: 'Автомобильный' },
  { id: 'bicycle', letter: 'В', label: 'Велосипедный' },
  { id: 'foot', letter: 'П', label: 'Пешеходный' },
]

export const DEFAULT_ORDER_ROUTE_PROFILE: OrderRouteProfile = 'foot'

export function orderRouteProfileMeta(profile: string | null | undefined) {
  const id = ORDER_ROUTE_PROFILES.some((p) => p.id === profile)
    ? (profile as OrderRouteProfile)
    : DEFAULT_ORDER_ROUTE_PROFILE
  return ORDER_ROUTE_PROFILES.find((p) => p.id === id) ?? ORDER_ROUTE_PROFILES[2]
}

export function orderRouteDurationLabel(profile: string | null | undefined): string {
  switch (profile) {
    case 'driving':
      return 'Время (авто)'
    case 'bicycle':
      return 'Время (вело)'
    default:
      return 'Время (пешком)'
  }
}
