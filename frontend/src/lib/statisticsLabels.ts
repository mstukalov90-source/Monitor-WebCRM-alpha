export const STATISTICS_ACTION_LABELS: Record<string, string> = {
  task_created: 'Создано задач',
  task_completed: 'Выполнено задач',
  task_updated: 'Обновлено задач',
  task_sent_to_field: 'Отправлено в поле',
  task_closed_legal: 'Закрыто легальных',
  task_closed_illegal: 'Закрыто нелегальных',
  task_marked_clear: 'Разрывие отсутствует',
  task_returned_to_active: 'Возврат в активные',
  task_executor_assigned: 'Назначен исполнитель',
  task_workflow_changed: 'Смена статуса workflow',
  order_sent_to_survey: 'Отправлено на обследование',
  order_released_from_survey: 'Снято с обследования',
  order_completed: 'Завершено заказов',
  order_completed_survey: 'Обследование завершено',
  order_analise_started: 'Анализ начат',
  order_analise_paused: 'Анализ приостановлен',
  order_analise_completed: 'Анализ завершён',
  order_executor_assigned: 'Назначен исполнитель заказа',
  order_task_number_updated: 'Обновлён номер задачи',
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
