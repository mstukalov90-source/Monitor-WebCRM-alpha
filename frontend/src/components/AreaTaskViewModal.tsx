import type { TaskFeature, TaskSource } from '../types'
import { formatTaskTableCell, TASK_SOURCE_LABELS } from '../types'
import { TaskExecutorAssign } from './TaskExecutorAssign'

interface AreaTaskViewModalProps {
  feature: TaskFeature | null
  taskSource: TaskSource
  canManagePersonnel: boolean
  onClose: () => void
  onSaved: () => void
}

function attrString(attrs: Record<string, unknown>, field: string): string {
  const value = attrs[field]
  if (value == null || value === '') return '—'
  return String(value)
}

export function AreaTaskViewModal({
  feature,
  taskSource,
  canManagePersonnel,
  onClose,
  onSaved,
}: AreaTaskViewModalProps) {
  if (!feature) return null

  const attrs = feature.attributes
  const assignmentKey = feature.task_key ?? String(attrs.key ?? '')
  const initialExecutor =
    attrs.executor != null && String(attrs.executor).trim() !== ''
      ? String(attrs.executor)
      : null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Просмотр площадного заказа</h2>
        <p className="muted small">Источник: {TASK_SOURCE_LABELS[taskSource]}</p>
        <p className="muted small">Ключ: {assignmentKey}</p>
        <p className="muted small">Район: {attrString(attrs, 'rayon')}</p>
        <p className="muted small">Статус: {attrString(attrs, 'status')}</p>
        <p className="muted small">Площадь: {attrString(attrs, 'area')}</p>
        <p className="muted small">
          Дата обследования:{' '}
          {formatTaskTableCell(attrs.date_survey, 'date') || '—'}
        </p>

        {assignmentKey && (
          <TaskExecutorAssign
            table="area"
            assignmentKey={assignmentKey}
            initialExecutor={initialExecutor}
            canManage={canManagePersonnel}
            onAssigned={() => onSaved()}
          />
        )}

        <div className="modal-actions">
          <div className="modal-action-group">
            <div className="modal-action-buttons">
              <button type="button" className="btn" onClick={onClose}>
                Закрыть
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
