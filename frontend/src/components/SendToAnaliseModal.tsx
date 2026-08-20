import { useEffect, useState } from 'react'
import { dispatchAreaAnalise, fetchAnaliseDispatch } from '../api/client'
import type { AnaliseDispatchContext } from '../types'
import { displayUserName } from '../types'

interface SendToAnaliseModalProps {
  orderKey: string
  taskNumber?: string | null
  rayon?: string | null
  onClose: () => void
  onDone: () => void
}

export function SendToAnaliseModal({
  orderKey,
  taskNumber,
  rayon,
  onClose,
  onDone,
}: SendToAnaliseModalProps) {
  const [ctx, setCtx] = useState<AnaliseDispatchContext | null>(null)
  const [assignee, setAssignee] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchAnaliseDispatch(orderKey)
      .then((result) => {
        if (cancelled) return
        setCtx(result)
        setAssignee(result.office_users[0]?.login ?? '')
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [orderKey])

  const titleParts = [taskNumber?.trim(), rayon?.trim()].filter(Boolean)
  const heading = titleParts.length ? titleParts.join(' · ') : orderKey.slice(0, 8)
  const alreadyDone = ctx?.workflow === 'done'
  const hasTasks = Boolean(ctx?.has_analise_tasks)
  const canSubmit =
    Boolean(ctx) && !alreadyDone && Boolean(assignee) && ctx!.office_users.length > 0 && !busy

  const submit = async () => {
    if (!ctx || !canSubmit) return
    setBusy(true)
    setError(null)
    try {
      await dispatchAreaAnalise(orderKey, {
        assignee_login: assignee,
        mode: hasTasks ? 'start' : 'complete',
      })
      onDone()
    } catch (e) {
      setError(String(e))
      setBusy(false)
    }
  }

  return (
    <div
      className="modal-backdrop send-to-analise-modal-backdrop"
      onClick={onClose}
    >
      <div
        className="modal send-to-analise-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <h2>Направить в обработку</h2>
        <p className="muted small">{heading}</p>

        {loading ? (
          <p className="muted">Загрузка…</p>
        ) : ctx ? (
          <>
            <p>
              {hasTasks
                ? `Есть ${ctx.task_count} ${taskCountLabel(ctx.task_count)} для анализа`
                : 'Задач для анализа нет'}
            </p>
            {ctx.lock_holder && !alreadyDone && (
              <p className="muted small">
                Сейчас в работе: {ctx.lock_holder}. Назначение переведёт заказ на выбранного
                сотрудника.
              </p>
            )}
            {alreadyDone && <p className="muted small">Заказ уже обработан.</p>}

            <label className="district-field">
              <span>Сотрудник office</span>
              <select
                value={assignee}
                disabled={busy || alreadyDone || ctx.office_users.length === 0}
                onChange={(e) => setAssignee(e.target.value)}
              >
                {ctx.office_users.length === 0 ? (
                  <option value="">Нет сотрудников с ролью office</option>
                ) : (
                  ctx.office_users.map((user) => (
                    <option key={user.login} value={user.login}>
                      {displayUserName(user.name, user.login)} ({user.login})
                    </option>
                  ))
                )}
              </select>
            </label>
          </>
        ) : null}

        {error && <p className="error-banner small">{error}</p>}

        <div className="modal-actions">
          <button
            type="button"
            className="btn primary"
            disabled={!canSubmit}
            onClick={() => void submit()}
          >
            {busy
              ? 'Сохранение…'
              : hasTasks
                ? 'Назначить в обработку'
                : 'Отметить обработанным'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Отмена
          </button>
        </div>
      </div>
    </div>
  )
}

function taskCountLabel(count: number): string {
  const n = Math.abs(count) % 100
  const n1 = n % 10
  if (n > 10 && n < 20) return 'задач'
  if (n1 === 1) return 'задача'
  if (n1 >= 2 && n1 <= 4) return 'задачи'
  return 'задач'
}
