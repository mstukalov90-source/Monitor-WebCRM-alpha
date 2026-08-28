import { useCallback, useEffect, useState } from 'react'
import { fetchMyClosedTasks } from '../api/client'
import type { MyClosedTask } from '../types'
import { TASK_SOURCE_LABELS } from '../types'

interface MyClosedTasksModalProps {
  onClose: () => void
  onSelect: (task: MyClosedTask) => void | Promise<void>
}

export function MyClosedTasksModal({ onClose, onSelect }: MyClosedTasksModalProps) {
  const [tasks, setTasks] = useState<MyClosedTask[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchMyClosedTasks()
      setTasks(result.tasks)
    } catch (e) {
      setError(String(e))
      setTasks([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleSelect = async (task: MyClosedTask) => {
    setBusy(true)
    setError(null)
    try {
      await onSelect(task)
    } catch (e) {
      setError(String(e))
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal order-status-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Мои закрытые задачи</h2>
        <p className="muted small">Закрытые вами задачи: район и название слоя</p>

        {error && <p className="error-banner small">{error}</p>}
        {loading ? (
          <p className="muted">Загрузка…</p>
        ) : tasks.length === 0 ? (
          <p className="muted small">Нет закрытых задач</p>
        ) : (
          <section className="order-status-section">
            <ul className="order-status-list">
              {tasks.map((task) => (
                <li key={task.task_key}>
                  <button
                    type="button"
                    className="order-status-item"
                    disabled={busy}
                    onClick={() => void handleSelect(task)}
                  >
                    <span className="order-status-item-main">
                      {task.rayon.trim() || 'Без района'} · {task.task_name}
                    </span>
                    <span className="muted small">
                      {TASK_SOURCE_LABELS[task.task_source] ?? task.task_source}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <div className="modal-actions">
          <button type="button" className="btn" disabled={loading || busy} onClick={() => void load()}>
            {loading ? 'Обновление…' : 'Обновить'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  )
}
