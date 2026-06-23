import { useEffect, useState } from 'react'
import {
  assignAreaTaskExecutor,
  assignFieldTaskExecutor,
  fetchPersonnelUsers,
} from '../api/client'
import type { PersonnelUser } from '../types'

interface TaskExecutorAssignProps {
  table: 'field' | 'area'
  assignmentKey: string
  initialExecutor: string | null
  canManage: boolean
  onAssigned?: (executor: string | null) => void
}

export function TaskExecutorAssign({
  table,
  assignmentKey,
  initialExecutor,
  canManage,
  onAssigned,
}: TaskExecutorAssignProps) {
  const [users, setUsers] = useState<PersonnelUser[]>([])
  const [executor, setExecutor] = useState(initialExecutor ?? '')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    setExecutor(initialExecutor ?? '')
  }, [initialExecutor, assignmentKey])

  useEffect(() => {
    if (!canManage) return
    fetchPersonnelUsers()
      .then(setUsers)
      .catch(() => setUsers([]))
  }, [canManage])

  const handleSave = async () => {
    setLoading(true)
    setMessage('')
    try {
      const value = executor.trim() || null
      if (table === 'field') {
        await assignFieldTaskExecutor(assignmentKey, value)
      } else {
        await assignAreaTaskExecutor(assignmentKey, value)
      }
      setMessage('Исполнитель сохранён')
      onAssigned?.(value)
    } catch (e) {
      setMessage(String(e))
    } finally {
      setLoading(false)
    }
  }

  const displayExecutor = initialExecutor?.trim() || '—'

  return (
    <div className="form-section">
      <h4>Исполнитель</h4>
      {canManage ? (
        <>
          <label className="form-row">
            <span>Сотрудник</span>
            <select
              value={executor}
              onChange={(e) => setExecutor(e.target.value)}
              disabled={loading}
            >
              <option value="">— не назначен —</option>
              {users.map((u) => (
                <option key={u.uuid} value={u.login}>
                  {u.login} ({u.role})
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn" disabled={loading} onClick={() => void handleSave()}>
            {loading ? 'Сохранение…' : 'Сохранить исполнителя'}
          </button>
        </>
      ) : (
        <p className="muted small">Назначен: {displayExecutor}</p>
      )}
      {message && <p className="message small">{message}</p>}
    </div>
  )
}
