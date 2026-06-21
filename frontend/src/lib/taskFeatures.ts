import type { LayerConfig, TaskFeature, TaskGroup } from '../types'

export interface TaskFeatureOnMap extends TaskFeature {
  subgroupName: string
  groupName: string
}

export function allTaskFeatures(
  groups: { subgroups: { features: TaskFeature[] }[] }[],
): TaskFeature[] {
  return groups.flatMap((g) => g.subgroups.flatMap((s) => s.features))
}

export function allTaskFeaturesOnMap(groups: TaskGroup[]): TaskFeatureOnMap[] {
  return groups.flatMap((group) =>
    group.subgroups.flatMap((subgroup) =>
      subgroup.features.map((feature) => ({
        ...feature,
        subgroupName: subgroup.name,
        groupName: group.name,
      })),
    ),
  )
}

export function layerConfigMap(layers: LayerConfig[]): Map<string, LayerConfig> {
  return new Map(layers.map((l) => [l.layer_key, l]))
}
