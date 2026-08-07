import type { TaskFeature, TaskResult } from '../types'
import { isFieldObserved } from '../types'
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

/** Filter active tasks by field_observed for office analysis stages. */
export function filterTaskResultByFieldObserved(
  result: TaskResult,
  observed: boolean,
): TaskResult {
  return {
    ...result,
    groups: result.groups.map((group) => ({
      ...group,
      subgroups: group.subgroups.map((subgroup) => ({
        ...subgroup,
        features: subgroup.features.filter((feature) =>
          isFieldObserved(feature.attributes.field_observed) === observed,
        ),
      })),
    })),
  }
}

export function filterTaskResultByAreaAndStage(
  result: TaskResult,
  areaFeature: TaskFeature,
  stage: 'pre_analise' | 'analise',
): TaskResult {
  const byArea = filterTaskResultByArea(result, areaFeature)
  return filterTaskResultByFieldObserved(byArea, stage === 'analise')
}

export function orderHasStageTasks(
  activeTasks: TaskResult,
  order: TaskFeature,
  stage: 'pre_analise' | 'analise',
): boolean {
  return countTaskResultFeatures(filterTaskResultByAreaAndStage(activeTasks, order, stage)) > 0
}
