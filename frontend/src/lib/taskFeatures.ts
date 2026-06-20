import type { LayerConfig, TaskFeature } from '../types'

export function allTaskFeatures(
  groups: { subgroups: { features: TaskFeature[] }[] }[],
): TaskFeature[] {
  return groups.flatMap((g) => g.subgroups.flatMap((s) => s.features))
}

export function layerConfigMap(layers: LayerConfig[]): Map<string, LayerConfig> {
  return new Map(layers.map((l) => [l.layer_key, l]))
}
