import { useEffect, useMemo, useState } from 'react'
import { fetchPersonnelUsers, sendAreaToSurvey } from '../api/client'
import {
  buildOznAssignCopyText,
  executorDisplayName,
  matchExecutorLoginFromOzn,
  oznOrderNames,
} from '../lib/oznMatch'
import type { OznMatchObject, OznMatchOrder, PersonnelUser } from '../types'
import {
  formatAreaHectares,
  formatAreaStatus,
  formatTaskTableCell,
} from '../types'
import { TaskExecutorAssign } from './TaskExecutorAssign'

interface OznMatchOrderModalProps {
  order: OznMatchOrder
  oznObjects: OznMatchObject[]
  onClose: () => void
  onPatched: (orderKey: string, patch: Partial<Pick<OznMatchOrder, 'status' | 'executor'>>) => void
}

export function OznMatchOrderModal({
  order,
  oznObjects,
  onClose,
  onPatched,
}: OznMatchOrderModalProps) {
  const [users, setUsers] = useState<PersonnelUser[]>([])
  const [sendBusy, setSendBusy] = useState(false)
  const [sendMessage, setSendMessage] = useState<string | null>(null)
  const [copyText, setCopyText] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchPersonnelUsers()
      .then((list) => {
        if (!cancelled) setUsers(list)
      })
      .catch(() => {
        if (!cancelled) setUsers([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    setCopyText(null)
    setCopied(false)
    setSendMessage(null)
  }, [order.order_key])

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1500)
    return () => window.clearTimeout(timer)
  }, [copied])

  const existingExecutor = order.executor?.trim() || null
  const autofillLogin = useMemo(
    () => matchExecutorLoginFromOzn(oznObjects, users),
    [oznObjects, users],
  )
  const initialExecutor = existingExecutor ?? autofillLogin
  const taskNumber = order.task_number?.trim() || order.order_key.slice(0, 8)
  const statusKey = (order.status ?? '').trim().toLowerCase()
  const canSendToField = statusKey === 'free'

  const handleSendToField = async () => {
    setSendBusy(true)
    setSendMessage(null)
    try {
      const result = await sendAreaToSurvey(order.order_key)
      if (result.status === 'updated') {
        onPatched(order.order_key, { status: 'wip' })
        setSendMessage('Отправлено в поле (статус: wip)')
      } else if (result.status === 'skipped') {
        onPatched(order.order_key, { status: 'wip' })
        setSendMessage('Уже на обследовании (wip)')
      } else {
        setSendMessage('Заказ не найден')
      }
    } catch (e) {
      setSendMessage(String(e))
    } finally {
      setSendBusy(false)
    }
  }

  const handleAssigned = (executor: string | null) => {
    onPatched(order.order_key, { executor: executor ?? null })
    if (!executor) {
      setCopyText(null)
      return
    }
    setCopyText(
      buildOznAssignCopyText({
        displayName: executorDisplayName(executor, users) || executor,
        taskNumber,
        orderNames: oznOrderNames(oznObjects),
      }),
    )
  }

  const handleCopy = async () => {
    if (!copyText) return
    try {
      await navigator.clipboard.writeText(copyText)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal ozn-match-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Заказ Мониторинга {taskNumber}</h2>
        <p className="muted small">Район: {order.rayon || '—'}</p>
        <p className="muted small">
          Статус: {formatAreaStatus(order.status) || order.status || '—'}
        </p>
        <p className="muted small">Площадь: {formatAreaHectares(order.area) || '—'}</p>

        <div className="ozn-match-modal-table-wrap">
          <table className="ozn-match-modal-table">
            <thead>
              <tr>
                <th>Дата назначения ОЗН</th>
                <th>Исполнитель</th>
                <th>Название</th>
              </tr>
            </thead>
            <tbody>
              {oznObjects.length === 0 ? (
                <tr>
                  <td colSpan={3} className="muted">
                    Нет пересекающих объектов ОЗН
                  </td>
                </tr>
              ) : (
                oznObjects.map((item) => (
                  <tr key={item.id}>
                    <td>{formatTaskTableCell(item.ozn_date, 'date') || '—'}</td>
                    <td>{item.executor?.trim() || '—'}</td>
                    <td>{item.order_name?.trim() || item.label || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {canSendToField && (
          <div className="form-section">
            <button
              type="button"
              className="btn primary"
              disabled={sendBusy}
              onClick={() => void handleSendToField()}
            >
              {sendBusy ? 'Отправка…' : 'В поле'}
            </button>
            {sendMessage && <p className="message small">{sendMessage}</p>}
          </div>
        )}
        {!canSendToField && sendMessage && (
          <p className="message small">{sendMessage}</p>
        )}

        <TaskExecutorAssign
          table="area"
          assignmentKey={order.order_key}
          initialExecutor={initialExecutor}
          canManage
          onAssigned={handleAssigned}
        />

        {copyText && (
          <div className="ozn-match-copy">
            <p className="ozn-match-copy-text">{copyText}</p>
            <button type="button" className="btn" onClick={() => void handleCopy()}>
              {copied ? 'Скопировано' : 'Копировать'}
            </button>
          </div>
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
