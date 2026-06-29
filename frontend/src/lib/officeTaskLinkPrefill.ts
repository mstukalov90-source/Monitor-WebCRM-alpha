import {
  AVR_SUBGROUP,
  EARTHWORK_SUBGROUP,
  LOCAL_REPAIR_SUBGROUP,
  OATI_ORDERS_SUBGROUP,
} from '../types'

const SUBGROUP_LINK_PREFILL: Record<string, { column: string; sourceField: string }> = {
  [OATI_ORDERS_SUBGROUP]: { column: 'oati_id', sourceField: 'order_number' },
  [EARTHWORK_SUBGROUP]: { column: 'earthwork_id', sourceField: 'registration_number_notifications' },
  [LOCAL_REPAIR_SUBGROUP]: { column: 'localwork_id', sourceField: 'global_id' },
  [AVR_SUBGROUP]: { column: 'avr_mos_id', sourceField: 'em_call_reg_num' },
}

export function officeTaskLinkPrefill(
  subgroupName: string,
  attributes: Record<string, unknown>,
): Record<string, string> | null {
  const mapping = SUBGROUP_LINK_PREFILL[subgroupName]
  if (!mapping) return null
  const value = attributes[mapping.sourceField]
  if (value == null || String(value).trim() === '') return null
  return { [mapping.column]: String(value).trim() }
}
