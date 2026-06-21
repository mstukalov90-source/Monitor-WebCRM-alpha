import { fetchTask, lookupTaskByFeature } from '../api/client'
import type { SelectedTaskContext, TaskFeature, TaskSource } from '../types'

export async function buildTaskExecutionContext(
  groupName: string,
  subgroupName: string,
  feature: TaskFeature,
  taskSource: TaskSource,
): Promise<SelectedTaskContext> {
  const taskKey = feature.task_key
  if (taskKey) {
    await fetchTask(taskKey)
  } else {
    await lookupTaskByFeature(subgroupName, feature.attributes)
  }

  return {
    groupName,
    subgroupName,
    feature,
    taskKey: taskKey ?? undefined,
    taskSource,
  }
}
