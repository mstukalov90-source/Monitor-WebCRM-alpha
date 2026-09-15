import type { OrderRouteProfile } from '../types'
import { ORDER_ROUTE_PROFILES } from '../lib/orderRouteProfile'

interface OrderRouteProfileSelectProps {
  value: OrderRouteProfile
  disabled?: boolean
  onChange: (profile: OrderRouteProfile) => void
}

export function OrderRouteProfileSelect({
  value,
  disabled,
  onChange,
}: OrderRouteProfileSelectProps) {
  return (
    <fieldset className="order-route-profile-select" disabled={disabled}>
      <legend>Граф OSRM</legend>
      <div className="order-route-profile-options">
        {ORDER_ROUTE_PROFILES.map((item) => (
          <label key={item.id} className="order-route-profile-option">
            <input
              type="radio"
              name="order-route-profile"
              value={item.id}
              checked={value === item.id}
              onChange={() => onChange(item.id)}
            />
            <span>
              {item.label} ({item.letter})
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
