import type { TaskFeature, TaskResult } from '../types'
import { geometryInsideArea } from './geometry'

export function countTaskResultFeatures(result: TaskResult | null): number {
  if (!result) return 0
  return result.groups.reduce(
    (sum, group) =>
      sum + group.subgroups.reduce((subSum, sub) => subSum + sub.features.length, 0),
    0,
  )
}

export function filterTaskResultByArea(result: TaskResult, areaFeature: TaskFeature): TaskResult {
  const areaGeometry = areaFeature.geometry
  if (!areaGeometry) {
    return { ...result, groups: [] }
  }

  return {
    ...result,
    groups: result.groups.map((group) => ({
      ...group,
      subgroups: group.subgroups.map((subgroup) => ({
        ...subgroup,
        features: subgroup.features.filter((feature) =>
          geometryInsideArea(feature.geometry, areaGeometry),
        ),
      })),
    })),
  }
}
