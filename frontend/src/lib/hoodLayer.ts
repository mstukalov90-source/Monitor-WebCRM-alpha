import type { LayerGroupConfig } from '../types'
import { HOOD_BOUNDARIES_DISPLAY_NAME } from '../types'

export function findHoodLayerKey(groups: LayerGroupConfig[]): string | null {
  for (const group of groups) {
    for (const layer of group.layers) {
      if (layer.display_name === HOOD_BOUNDARIES_DISPLAY_NAME) {
        return layer.layer_key
      }
    }
    if (group.groups.length) {
      const nested = findHoodLayerKey(group.groups)
      if (nested) return nested
    }
  }
  return null
}
