import type { CollectLayerChunk, CollectPlan, TaskResult } from '../types'

export function taskResultFromPlan(plan: CollectPlan): TaskResult {
  return {
    district_name: plan.district_name,
    filter_date_from: plan.filter_date_from,
    filter_date_to: plan.filter_date_to,
    apply_date_filter: plan.apply_date_filter,
    errors: [...plan.errors],
    groups: plan.groups.map((group) => ({
      name: group.name,
      subgroups: group.subgroups.map((subgroup) => ({
        name: subgroup.name,
        date_field: subgroup.date_field,
        features: [],
      })),
    })),
    task_source: 'active',
  }
}

export function appendLayerChunk(result: TaskResult, chunk: CollectLayerChunk): void {
  if (chunk.errors.length) {
    result.errors.push(...chunk.errors)
  }
  const group = result.groups.find((g) => g.name === chunk.group_name)
  const subgroup = group?.subgroups.find((s) => s.name === chunk.subgroup_name)
  if (!subgroup) {
    result.errors.push(
      `Не найдена подгруппа «${chunk.subgroup_name}» для слоя ${chunk.layer_key}`,
    )
    return
  }
  subgroup.features.push(...chunk.features)
}
