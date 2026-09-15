import { useCallback, useEffect, useState } from 'react'
import {
  fetchLettersForReview,
  hideLetterFromReview,
  updateLetterReview,
} from '../api/client'
import {
  LETTER_REVIEW_LIMITS,
  formatRuDate,
  type LetterReviewLimit,
  type LetterReviewStatus,
  type OatiLetterReviewItem,
} from '../types'
import { LetterPointMapView } from './LetterPointMapView'
import { LetterReviewActions } from './LetterReviewActions'

interface LetterReviewScreenProps {
  userLogin: string
  onBack: () => void
  onLogout: () => Promise<void>
}

function letterTitle(item: OatiLetterReviewItem): string {
  const street = item.street.trim()
  return street || `Письмо №${item.fid}`
}

function formatCreatedAt(value: string | null): string {
  if (!value) return '—'
  const datePart = formatRuDate(value)
  const time = value.match(/T(\d{2}:\d{2})/)
  return time ? `${datePart} ${time[1]}` : datePart || value
}

export function LetterReviewScreen({
  userLogin,
  onBack,
  onLogout,
}: LetterReviewScreenProps) {
  const [limit, setLimit] = useState<LetterReviewLimit>(50)
  const [items, setItems] = useState<OatiLetterReviewItem[]>([])
  const [loading, setLoading] = useState(false)
  const [busyFid, setBusyFid] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<OatiLetterReviewItem | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const rows = await fetchLettersForReview(limit)
      setItems(rows)
      setSelected((prev) => {
        if (!prev) return null
        return rows.find((row) => row.fid === prev.fid) ?? null
      })
    } catch (e) {
      setError(String(e))
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [limit])

  useEffect(() => {
    void load()
  }, [load])

  const patchItem = (updated: OatiLetterReviewItem) => {
    setItems((prev) => prev.map((row) => (row.fid === updated.fid ? updated : row)))
    setSelected((prev) => (prev?.fid === updated.fid ? updated : prev))
  }

  const handleReview = async (item: OatiLetterReviewItem, next: LetterReviewStatus) => {
    const status = item.review_status === next ? null : next
    setBusyFid(item.fid)
    setError(null)
    try {
      const updated = await updateLetterReview(item.fid, status)
      patchItem(updated)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusyFid(null)
    }
  }

  const handleHide = async (item: OatiLetterReviewItem) => {
    setBusyFid(item.fid)
    setError(null)
    try {
      await hideLetterFromReview(item.fid)
      setItems((prev) => prev.filter((row) => row.fid !== item.fid))
      setSelected((prev) => (prev?.fid === item.fid ? null : prev))
    } catch (e) {
      setError(String(e))
    } finally {
      setBusyFid(null)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="workspace-header">
          <h1>Ревью писем</h1>
          <div className="workspace-meta">
            <span className="muted">{userLogin}</span>
            <label className="district-field-inline">
              <span>Лимит</span>
              <select
                value={limit}
                disabled={loading}
                onChange={(e) => setLimit(Number(e.target.value) as LetterReviewLimit)}
              >
                {LETTER_REVIEW_LIMITS.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="btn" onClick={onBack}>
              К карте
            </button>
            <button type="button" className="btn" onClick={() => void onLogout()}>
              Выйти
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={loading}
              onClick={() => void load()}
            >
              {loading ? 'Обновление…' : 'Обновить'}
            </button>
          </div>
        </div>
        {error && <div className="error-banner">{error}</div>}
      </header>

      <div className="letter-review-body">
        {loading && items.length === 0 ? (
          <p className="muted">Загрузка писем…</p>
        ) : items.length === 0 ? (
          <p className="muted">Писем нет</p>
        ) : (
          <div className="letter-review-table-wrap">
            <table className="personnel-table letter-review-table">
              <thead>
                <tr>
                  <th>№</th>
                  <th>Дата</th>
                  <th>Район</th>
                  <th>Улица</th>
                  <th>Автор</th>
                  <th>Ревью</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.fid}
                    className={selected?.fid === item.fid ? 'selected' : ''}
                    onClick={() => setSelected(item)}
                  >
                    <td>{item.fid}</td>
                    <td>{formatCreatedAt(item.created_at)}</td>
                    <td>{item.rayon || '—'}</td>
                    <td>{letterTitle(item)}</td>
                    <td>{item.created_by || '—'}</td>
                    <td>
                      {item.review_status === 'approved'
                        ? 'Одобрено'
                        : item.review_status === 'rejected'
                          ? 'Отклонено'
                          : '—'}
                    </td>
                    <td>
                      <LetterReviewActions
                        status={item.review_status}
                        disabled={busyFid === item.fid}
                        onApprove={() => void handleReview(item, 'approved')}
                        onReject={() => void handleReview(item, 'rejected')}
                        onHide={() => void handleHide(item)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <div
            className="modal letter-review-preview"
            onClick={(e) => e.stopPropagation()}
          >
            <h2>Письмо №{selected.fid}</h2>
            <p className="muted small">
              {formatCreatedAt(selected.created_at)}
              {selected.created_by ? ` · ${selected.created_by}` : ''}
            </p>
            <div className="letter-review-preview-meta">
              <p>
                <strong>Район:</strong> {selected.rayon || '—'}
              </p>
              <p>
                <strong>Улица:</strong> {selected.street || '—'}
              </p>
              <p>
                <strong>Адрес:</strong> {selected.address || '—'}
              </p>
              <p>
                <strong>Заказчик:</strong> {selected.customer || '—'}
              </p>
              <p>
                <strong>Исполнитель:</strong> {selected.executor || '—'}
              </p>
              <p>
                <strong>Описание:</strong> {selected.description || '—'}
              </p>
              <p>
                <strong>Координаты:</strong> {selected.coordinates || '—'}
              </p>
            </div>
            <div className="letter-review-map-wrap">
              <LetterPointMapView lat={selected.lat} lon={selected.lon} />
            </div>
            <div className="modal-actions letter-review-preview-actions">
              <LetterReviewActions
                status={selected.review_status}
                disabled={busyFid === selected.fid}
                onApprove={() => void handleReview(selected, 'approved')}
                onReject={() => void handleReview(selected, 'rejected')}
                onHide={() => void handleHide(selected)}
              />
              <button type="button" className="btn" onClick={() => setSelected(null)}>
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
