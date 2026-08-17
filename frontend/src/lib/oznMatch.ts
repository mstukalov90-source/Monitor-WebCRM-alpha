import type { OznMatchObject, PersonnelUser } from '../types'
import { displayUserName } from '../types'

const ASSIGNABLE_ROLES = new Set(['field', 'office'])

export function normalizePersonName(value: string | null | undefined): string {
  return (value ?? '').replace(/\s+/g, ' ').trim().toLowerCase()
}

export function matchExecutorLoginFromOzn(
  oznObjects: Pick<OznMatchObject, 'executor'>[],
  users: Pick<PersonnelUser, 'login' | 'name' | 'role'>[],
): string | null {
  const assignable = users.filter((user) => ASSIGNABLE_ROLES.has(user.role))
  const matchedLogins = new Set<string>()

  for (const obj of oznObjects) {
    const key = normalizePersonName(obj.executor)
    if (!key) continue
    const hits = assignable.filter((user) => normalizePersonName(user.name) === key)
    if (hits.length === 1) {
      matchedLogins.add(hits[0].login)
    }
  }

  if (matchedLogins.size !== 1) return null
  return [...matchedLogins][0]
}

export function oznOrderNames(oznObjects: Pick<OznMatchObject, 'order_name' | 'label'>[]): string[] {
  const names: string[] = []
  const seen = new Set<string>()
  for (const obj of oznObjects) {
    const name = (obj.order_name ?? obj.label ?? '').trim()
    if (!name || seen.has(name)) continue
    seen.add(name)
    names.push(name)
  }
  return names
}

export function buildOznAssignCopyText(params: {
  displayName: string
  taskNumber: string
  orderNames: string[]
}): string {
  const names = params.orderNames.join(', ')
  return `${params.displayName} Заказ по мониторингу ${params.taskNumber}, в него попадает заказ по ОЗН ${names}`
}

export function executorDisplayName(
  login: string | null | undefined,
  users: Pick<PersonnelUser, 'login' | 'name'>[],
): string {
  const key = (login ?? '').trim()
  if (!key) return ''
  const match = users.find((user) => user.login === key)
  return displayUserName(match?.name, key)
}
