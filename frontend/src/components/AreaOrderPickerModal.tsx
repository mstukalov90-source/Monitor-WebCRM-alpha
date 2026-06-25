import type { TaskFeature } from '../types'
import {
  analiseWorkflowStatus,
  analiseWorkflowStatusClass,
  canStartAnalise,
  formatAnaliseWorkflowStatus,
  formatAreaHectares,
  formatTaskTableCell,
} from '../types'

interface AreaOrderPickerModalProps {
  orders: TaskFeature[]
  currentUserLogin: string
  loading?: boolean
  onSelect: (feature: TaskFeature) => void
  onRefresh?: () => void
}

function attrString(attrs: Record<string, unknown>, field: string): string {
  const value = attrs[field]
  if (value == null || value === '') return '—'
  return String(value)
}

export function AreaOrderPickerModal({
  orders,
  currentUserLogin,
  loading,
  onSelect,
  onRefresh,
}: AreaOrderPickerModalProps) {
  return (
    <div className="modal-backdrop modal-backdrop-blocking">
      <div className="modal area-order-picker-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Выбор площадного заказа</h2>
        <p className="muted small">Выберите заказ для анализа активных задач внутри полигона</p>

        {loading ? (
          <p className="muted">Загрузка заказов…</p>
        ) : orders.length === 0 ? (
          <p className="muted">В районе нет площадных заказов</p>
        ) : (
          <div className="area-order-picker-table-wrap">
            <table className="task-table area-order-picker-table">
              <thead>
                <tr>
                  <th>Номер задачи</th>
                  <th>Площадь</th>
                  <th>Дата обследования</th>
                  <th>Статус</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => {
                  const attrs = order.attributes
                  const key = order.task_key ?? String(attrs.key ?? '')
                  const workflow = analiseWorkflowStatus(attrs)
                  const statusLabel = formatAnaliseWorkflowStatus(attrs)
                  const canStart = canStartAnalise(attrs, currentUserLogin)
                  const actionLabel = workflow === 'idle' ? 'В работу' : 'Продолжить'
                  return (
                    <tr key={key}>
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
                })}
              </tbody>
            </table>
          </div>
        )}

        {onRefresh && (
          <div className="modal-actions">
            <button type="button" className="btn" disabled={loading} onClick={onRefresh}>
              Обновить список
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
