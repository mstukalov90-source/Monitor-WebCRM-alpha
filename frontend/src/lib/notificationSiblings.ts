import type { LinkedTaskFeature, TaskFeature } from '../types'

export const ORDER_SUBGROUP_LINK_FIELDS: Record<string, string> = {
  'Ордера ОАТИ': 'order_number',
  'Уведомления на земляные работы': 'registration_number_notifications',
  'Текущие локальные ремонты': 'global_id',
  'Аварийно-восстановительные работы': 'em_call_reg_num',
}

export function getSubgroupLinkField(subgroupName: string): string | null {
  return ORDER_SUBGROUP_LINK_FIELDS[subgroupName] ?? null
}

export function normalizeLinkValue(value: unknown): string | null {
  if (value == null) return null
  const text = String(value).trim()
  return text || null
}

export function findSiblingFeatures(
  features: TaskFeature[],
  feature: TaskFeature,
  linkField: string,
  excludeTaskKey?: string | null,
): TaskFeature[] {
  const linkValue = normalizeLinkValue(feature.attributes[linkField])
  if (!linkValue) return []
  return features.filter((candidate) => {
    if (candidate === feature) return false
    if (excludeTaskKey && candidate.task_key === excludeTaskKey) return false
    if (!candidate.geometry) return false
    return normalizeLinkValue(candidate.attributes[linkField]) === linkValue
  })
}

export function siblingsToLinkedFeatures(
  siblings: TaskFeature[],
  linkField: string,
  linkValue: string,
): LinkedTaskFeature[] {
  return siblings.map((feat) => ({
    link_column: linkField,
    layer_key: feat.layer_key,
    layer_name: feat.layer_name,
    geometry: feat.geometry ?? null,
    attributes: feat.attributes,
    business_id: linkValue,
    link_kind: 'sibling',
  }))
}

export function geometryKindLabel(layerName: string): string {
  if (layerName.includes('— точки')) return 'точка'
  if (layerName.includes('— линии')) return 'линия'
  if (layerName.includes('— полигоны')) return 'полигон'
  return 'объект'
}

export function countNotificationGroup(
  features: TaskFeature[],
  linkField: string,
  linkValue: string,
): number {
  return features.filter(
    (candidate) => normalizeLinkValue(candidate.attributes[linkField]) === linkValue,
  ).length
}

export type TaskTableRow =
  | { kind: 'group'; groupKey: string; label: string; count: number; collapsed: boolean }
  | { kind: 'feature'; featureIndex: number; feature: TaskFeature; indent?: boolean }

export function buildGroupedTableRows(
  features: TaskFeature[],
  subgroupName: string,
  groupName: string,
  collapsedGroups: Record<string, boolean>,
  ordersGroupName: string,
): TaskTableRow[] {
  const linkField =
    groupName === ordersGroupName ? getSubgroupLinkField(subgroupName) : null
  if (!linkField) {
    return features.map((feature, featureIndex) => ({
      kind: 'feature',
      featureIndex,
      feature,
    }))
  }

  const grouped = new Map<string, number[]>()
  const ungrouped: number[] = []

  features.forEach((feature, featureIndex) => {
    const linkValue = normalizeLinkValue(feature.attributes[linkField])
    if (!linkValue) {
      ungrouped.push(featureIndex)
      return
    }
    const bucket = grouped.get(linkValue) ?? []
    bucket.push(featureIndex)
    grouped.set(linkValue, bucket)
  })

  const rows: TaskTableRow[] = []
  for (const label of [...grouped.keys()].sort((a, b) => a.localeCompare(b, 'ru'))) {
    const indices = grouped.get(label) ?? []
    if (indices.length === 1) {
      rows.push({
        kind: 'feature',
        featureIndex: indices[0],
        feature: features[indices[0]],
      })
      continue
    }
    const groupKey = `${linkField}:${label}`
    const collapsed = collapsedGroups[groupKey] ?? false
    rows.push({ kind: 'group', groupKey, label, count: indices.length, collapsed })
    if (!collapsed) {
      for (const featureIndex of indices) {
        rows.push({
          kind: 'feature',
          featureIndex,
          feature: features[featureIndex],
          indent: true,
        })
      }
    }
  }

  for (const featureIndex of ungrouped) {
    rows.push({
      kind: 'feature',
      featureIndex,
      feature: features[featureIndex],
    })
  }

  return rows
}
