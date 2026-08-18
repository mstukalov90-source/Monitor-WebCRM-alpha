import { useEffect, useMemo, useState } from 'react'
import { applyZipClose, fetchPersonnelUsers, previewZipClose } from '../api/client'
import type { PersonnelUser, ZipCloseApplyResult, ZipCloseItem, ZipClosePreview } from '../types'
import { displayUserName } from '../types'

interface ZipCloseModalProps {
  onClose: () => void
}

const CLOSE_KIND_LABEL: Record<string, string> = {
  clear: 'без разрытия → tasks_clear',
  observed: 'разрытие → field_observed',
  area_done: 'площадь wip_field → done',
  track_only: 'только трек',
}

const KIND_LABEL: Record<string, string> = {
  field_order: 'точка',
  area: 'площадь',
  unknown: '—',
}

const OUTCOME_LABEL: Record<string, string> = {
  ok: 'сходится',
  skip: 'пропуск',
  mismatch: 'не сходится',
  error: 'ошибка',
}

function outcomeClass(outcome: string): string {
  if (outcome === 'ok') return 'zip-close-outcome-ok'
  if (outcome === 'skip') return 'zip-close-outcome-skip'
  return 'zip-close-outcome-bad'
}

function ItemDetails({ item }: { item: ZipCloseItem }) {
  const lines: string[] = []
  if (item.skip_reason) lines.push(item.skip_reason)
  if (item.error) lines.push(item.error)
  if (item.apply_error) lines.push(item.apply_error)
  lines.push(...item.warnings)
  lines.push(...item.actions)
  if (lines.length === 0) return <span className="muted">—</span>
  return (
    <ul className="zip-close-notes">
      {lines.map((line, index) => (
        <li key={`${index}-${line.slice(0, 40)}`}>{line}</li>
      ))}
    </ul>
  )
}

export function ZipCloseModal({ onClose }: ZipCloseModalProps) {
  const [users, setUsers] = useState<PersonnelUser[]>([])
  const [username, setUsername] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [preview, setPreview] = useState<ZipClosePreview | null>(null)
  const [applyResult, setApplyResult] = useState<ZipCloseApplyResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchPersonnelUsers()
      .then((list) => {
        const fieldUsers = list.filter((user) => user.role === 'field')
        setUsers(fieldUsers)
      })
      .catch(() => setUsers([]))
  }, [])

  const rows = applyResult?.items ?? preview?.items ?? []
  const canApply = Boolean(preview?.can_apply) && !applyResult && !loading
  const fileLabel = files.length === 0 ? 'файлы не выбраны' : `${files.length} ZIP`

  const summary = useMemo(() => {
    if (rows.length === 0) return null
    const write = rows.filter((item) => item.will_write).length
    const skip = rows.filter((item) => item.outcome === 'skip').length
    const bad = rows.filter((item) => item.outcome === 'mismatch' || item.outcome === 'error').length
    return { write, skip, bad }
  }, [rows])

  const resetPreview = () => {
    setPreview(null)
    setApplyResult(null)
  }

  const handleFiles = (list: FileList | null) => {
    const next = list ? Array.from(list).filter((file) => file.name.toLowerCase().endsWith('.zip')) : []
    setFiles(next)
    resetPreview()
  }

  const handlePreview = async () => {
    if (!username || files.length === 0) return
    setLoading(true)
    setError(null)
    setApplyResult(null)
    try {
      const result = await previewZipClose(username, files)
      setPreview(result)
    } catch (e) {
      setPreview(null)
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleApply = async () => {
    if (!preview?.preview_id || !preview.can_apply) return
    setLoading(true)
    setError(null)
    try {
      const result = await applyZipClose(preview.preview_id, preview.username)
      setApplyResult(result)
      setPreview(null)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal zip-close-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Закрытие через ZIP</h2>
        <p className="muted small">
          Сначала проверка архивов FieldControl против БД. Запись в БД и фотосервис — только после
          подтверждения и только для сходящихся ZIP.
        </p>

        <label className="district-field">
          <span>Кто закрывает</span>
          <select
            value={username}
            disabled={loading}
            onChange={(e) => {
              setUsername(e.target.value)
              resetPreview()
            }}
          >
            <option value="">— выберите полевого сотрудника —</option>
            {users.map((user) => (
              <option key={user.uuid} value={user.login}>
                {displayUserName(user.name, user.login)} ({user.login})
              </option>
            ))}
          </select>
        </label>

        <label className="district-field">
          <span>ZIP архивы</span>
          <input
            type="file"
            accept=".zip,application/zip"
            multiple
            disabled={loading}
            onChange={(e) => handleFiles(e.target.files)}
          />
          <span className="muted small">{fileLabel}</span>
        </label>

        {error && <p className="error-banner small">{error}</p>}

        {summary && (
          <p className="muted small">
            Сходятся: {summary.write} · пропуск: {summary.skip} · не сходятся / ошибка: {summary.bad}
            {applyResult ? ` · записано: ${applyResult.applied_count}` : ''}
          </p>
        )}

        {rows.length > 0 && (
          <div className="zip-close-table-wrap">
            <table className="zip-close-table">
              <thead>
                <tr>
                  <th>файл</th>
                  <th>тип</th>
                  <th>заказ</th>
                  <th>район</th>
                  <th>в БД</th>
                  <th>действие</th>
                  <th>фото</th>
                  <th>статус</th>
                  <th>детали</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => (
                  <tr key={`${item.filename}-${item.order_uuid ?? item.error ?? ''}`}>
                    <td>{item.filename}</td>
                    <td>{KIND_LABEL[item.kind] ?? item.kind}</td>
                    <td>{item.order_number || (item.order_uuid ? item.order_uuid.slice(0, 8) : '—')}</td>
                    <td>{item.rayon || '—'}</td>
                    <td>{item.db_status || '—'}</td>
                    <td>
                      {item.close_kind ? CLOSE_KIND_LABEL[item.close_kind] ?? item.close_kind : '—'}
                    </td>
                    <td>{item.photo_count}</td>
                    <td>
                      <span className={`zip-close-outcome ${outcomeClass(item.outcome)}`}>
                        {item.applied ? 'записано' : OUTCOME_LABEL[item.outcome] ?? item.outcome}
                      </span>
                    </td>
                    <td>
                      <ItemDetails item={item} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="modal-actions">
          <button
            type="button"
            className="btn"
            disabled={loading || !username || files.length === 0}
            onClick={() => void handlePreview()}
          >
            {loading && !applyResult ? 'Проверка…' : 'Проверить'}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={!canApply}
            onClick={() => void handleApply()}
          >
            {loading && preview ? 'Запись…' : 'Записать в БД и сервис'}
          </button>
          <button type="button" className="btn" disabled={loading} onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  )
}
