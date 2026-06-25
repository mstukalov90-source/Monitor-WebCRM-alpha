import type { TaskFilterSelection, TaskSource } from '../types'
import {
  TASK_FILTER_LABEL,
  TASK_FILTER_NONE,
  TASK_SECTION_ORDER_SOURCES,
  TASK_SECTION_TASK_SOURCES,
  TASK_SOURCE_LABELS,
} from '../types'

interface TaskSourceTabsProps {
  taskFilterValue: TaskFilterSelection
  allowedSources: TaskSource[]
  onTaskFilterChange: (source: TaskFilterSelection) => void
  ordersOnMap: boolean
  onOrdersToggle: () => void
  loading?: boolean
  showPauseOrder?: boolean
  onPauseOrder?: () => void
  showCompleteOrder?: boolean
  canCompleteOrder?: boolean
  completeOrderTitle?: string
  onCompleteOrder?: () => void
}

export function TaskSourceTabs({
  taskFilterValue,
  allowedSources,
  onTaskFilterChange,
  ordersOnMap,
  onOrdersToggle,
  loading,
  showPauseOrder,
  onPauseOrder,
  showCompleteOrder,
  canCompleteOrder,
  completeOrderTitle,
  onCompleteOrder,
}: TaskSourceTabsProps) {
  const taskSources = TASK_SECTION_TASK_SOURCES.filter((s) => allowedSources.includes(s))
  const hasOrders = TASK_SECTION_ORDER_SOURCES.some((s) => allowedSources.includes(s))
  const showOrderActions = showPauseOrder || showCompleteOrder

  return (
    <div className="task-source-tabs">
      <div className="task-source-tabs-left">
        {taskSources.length > 0 && (
          <select
            className="task-source-filter-select"
            value={taskFilterValue}
            disabled={loading}
            aria-label="Фильтр задач"
            onChange={(e) => onTaskFilterChange(e.target.value as TaskFilterSelection)}
          >
            <option value={TASK_FILTER_NONE}>{TASK_FILTER_LABEL}</option>
            {taskSources.map((source) => (
              <option key={source} value={source}>
                {TASK_SOURCE_LABELS[source]}
              </option>
            ))}
          </select>
        )}
        {hasOrders && (
          <button
            type="button"
            className={`task-source-tab task-source-orders-tab ${ordersOnMap ? 'active' : ''}`}
            disabled={loading}
            aria-pressed={ordersOnMap}
            title={ordersOnMap ? 'Скрыть заказы на карте и в панели' : 'Показать заказы на карте и в панели'}
            onClick={onOrdersToggle}
          >
            Заказы
          </button>
        )}
      </div>
      {showOrderActions && (
        <div className="task-source-order-actions">
          {showPauseOrder && (
            <button
              type="button"
              className="btn task-source-pause-order"
              disabled={loading}
              onClick={onPauseOrder}
            >
              Приостановить заказ
            </button>
          )}
          {showCompleteOrder && (
            <button
              type="button"
              className="btn primary task-source-complete-order"
              disabled={!canCompleteOrder || loading}
              title={completeOrderTitle}
              onClick={onCompleteOrder}
            >
              Завершить заказ
            </button>
          )}
        </div>
      )}
    </div>
  )
}
