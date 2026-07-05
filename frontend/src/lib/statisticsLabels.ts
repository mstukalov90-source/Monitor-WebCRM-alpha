export const STATISTICS_ACTION_LABELS: Record<string, string> = {
  field_camera_survey: 'Обследование камеральной задачи',
  field_disruption_absent: 'Отсутствие разрытия по задаче',
  field_disruption_found: 'Обнаружение разрытия в поле',
  field_order_closed: 'Закрытие заказа',
  office_analise_started: 'Анализ начат',
  office_analise_completed: 'Анализ завершён',
  office_disruption_absent: 'Разрытие отсутствует',
  office_camera_tasks_created: 'Создано камеральных задач',
  office_closed_illegal: 'Закрыто нелегально',
  office_closed_legal: 'Закрыто легально',
}

export const STATISTICS_OBJECT_TYPE_LABELS: Record<string, string> = {
  task: 'Задача',
  order: 'Заказ',
}

export function formatStatisticsAction(action: string): string {
  return STATISTICS_ACTION_LABELS[action] ?? action
}

export function formatStatisticsObjectType(objectType: string): string {
  return STATISTICS_OBJECT_TYPE_LABELS[objectType] ?? objectType
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

export function formatIsoDateLocal(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

export function defaultStatisticsDateRange(): { dateFrom: string; dateTo: string } {
  const to = new Date()
  const from = new Date()
  from.setDate(from.getDate() - 30)
  return { dateFrom: formatIsoDateLocal(from), dateTo: formatIsoDateLocal(to) }
}
