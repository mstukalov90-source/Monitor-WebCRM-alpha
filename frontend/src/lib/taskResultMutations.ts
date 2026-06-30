import type { TaskFeature, TaskResult } from '../types'

function featureTaskKey(feature: TaskFeature): string | null {
  if (feature.task_key) return feature.task_key
  const key = feature.attributes.key
  if (key == null || key === '') return null
  return String(key)
}

function matchesTaskKey(feature: TaskFeature, taskKey: string): boolean {
  return featureTaskKey(feature) === taskKey
}

export function removeTaskByKey(result: TaskResult, taskKey: string): TaskResult {
  return {
    ...result,
    groups: result.groups.map((group) => ({
      ...group,
      subgroups: group.subgroups.map((subgroup) => ({
        ...subgroup,
        features: subgroup.features.filter((feature) => !matchesTaskKey(feature, taskKey)),
      })),
    })),
  }
}

export function patchTaskAttributes(
  result: TaskResult,
  taskKey: string,
  patch: Record<string, unknown>,
): TaskResult {
  return {
    ...result,
    groups: result.groups.map((group) => ({
      ...group,
      subgroups: group.subgroups.map((subgroup) => ({
        ...subgroup,
        features: subgroup.features.map((feature) => {
          if (!matchesTaskKey(feature, taskKey)) return feature
          return {
            ...feature,
            attributes: { ...feature.attributes, ...patch },
          }
        }),
      })),
    })),
  }
}

export function patchAreaViewFeature(
  feature: TaskFeature,
  patch: Record<string, unknown>,
): TaskFeature {
  return {
    ...feature,
    attributes: { ...feature.attributes, ...patch },
  }
}
