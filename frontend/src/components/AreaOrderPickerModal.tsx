import type { OfficeAnaliseStage, TaskFeature } from '../types'
import {
  analiseWorkflowStatusClass,
  canStartStage,
  formatAreaHectares,
  formatStageWorkflowStatus,
  formatTaskTableCell,
  stageWorkflowStatus,
} from '../types'
import { groupAreaOrdersByRayon } from '../lib/areaOrders'

interface AreaOrderPickerModalProps {
  orders: TaskFeature[]
  currentUserLogin: string
  stage: OfficeAnaliseStage
  loading?: boolean
  groupByRayon?: boolean
  onSelect: (feature: TaskFeature) => void
  onRefresh?: () => void
  onChangeMode?: () => void
}

function attrString(attrs: Record<string, unknown>, field: string): string {
  const value = attrs[field]
  if (value == null || value === '') return '—'
  return String(value)
}

export function AreaOrderPickerModal({
  orders,
  currentUserLogin,
  stage,
  loading,
  groupByRayon = false,
  onSelect,
  onRefresh,
  onChangeMode,
}: AreaOrderPickerModalProps) {
  const title =
    stage === 'pre_analise' ? 'Подготовка данных в поле' : 'Анализ полевых данных'
  const hint =
    stage === 'pre_analise'
      ? 'Заказы с активными задачами, не обследованными в поле'
      : 'Заказы с активными задачами, обследованными в поле'

  const groups = groupByRayon ? groupAreaOrdersByRayon(orders) : null

  const renderRow = (order: TaskFeature) => {
    const attrs = order.attributes
    const key = order.task_key ?? String(attrs.key ?? '')
    const workflow = stageWorkflowStatus(attrs, stage)
    const statusLabel = formatStageWorkflowStatus(attrs, stage)
    const canStart = canStartStage(attrs, currentUserLogin, stage)
    const actionLabel = workflow === 'idle' ? 'В работу' : 'Продолжить'
    return (
      <tr key={key}>
        {groupByRayon && <td>{attrString(attrs, 'rayon')}</td>}
        <td>{attrString(attrs, 'task_number')}</td>
        <td>{formatAreaHectares(attrs.area) || '—'}</td>
        <td>{formatTaskTableCell(attrs.date_survey, 'date') || '—'}</td>
        <td>
          <span
            className={`area-analise-status ${analiseWorkflowStatusClass(workflow)}`}
            title={statusLabel}
          >
            {statusLabel}
          </span>
        </td>
        <td className="area-order-picker-action">
          {canStart && (
            <button
              type="button"
              className="btn primary"
              disabled={loading}
              onClick={() => onSelect(order)}
            >
              {actionLabel}
            </button>
          )}
        </td>
      </tr>
    )
  }

  return (
    <div className="modal-backdrop modal-backdrop-blocking">
      <div className="modal area-order-picker-modal" onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        <p className="muted small">{hint}</p>

        {loading ? (
          <p className="muted">Загрузка заказов…</p>
        ) : orders.length === 0 ? (
          <p className="muted">Нет подходящих площадных заказов</p>
        ) : (
          <div className="area-order-picker-table-wrap">
            <table className="task-table area-order-picker-table">
              <thead>
                <tr>
                  {groupByRayon && <th>Район</th>}
                  <th>Номер задачи</th>
                  <th>Площадь</th>
                  <th>Дата обследования</th>
                  <th>Статус</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {groups
                  ? groups.flatMap((group) => group.orders.map(renderRow))
                  : orders.map(renderRow)}
              </tbody>
            </table>
          </div>
        )}

        <div className="modal-actions">
          {onRefresh && (
            <button type="button" className="btn" disabled={loading} onClick={onRefresh}>
              Обновить список
            </button>
          )}
          {onChangeMode && (
            <button type="button" className="btn" disabled={loading} onClick={onChangeMode}>
              Сменить режим
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
