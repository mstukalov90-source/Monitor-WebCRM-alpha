import { useEffect, useState } from 'react'
import { aiPhotoImageUrl, fetchAiPhotoMeta } from '../api/client'
import type { AiPhotoMeta } from '../types'

const CLEAR_CONFIRM_MESSAGE = 'Отметить задачу: разрытие отсутствует?'

export interface PhotoViewModalTaskActions {
  canMarkDisruptionAbsent: boolean
  onMarkDisruptionAbsent: () => Promise<void>
}

interface PhotoViewModalProps {
  uuid: string | null
  onClose: () => void
  taskActions?: PhotoViewModalTaskActions
}

export function PhotoViewModal({ uuid, onClose, taskActions }: PhotoViewModalProps) {
  const [meta, setMeta] = useState<AiPhotoMeta | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [imageError, setImageError] = useState(false)
  const [pendingClear, setPendingClear] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)

  useEffect(() => {
    if (!uuid) {
      setMeta(null)
      setError(null)
      setImageError(false)
      setPendingClear(false)
      setActionBusy(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    setImageError(false)
    setMeta(null)
    setPendingClear(false)
    setActionBusy(false)

    fetchAiPhotoMeta(uuid)
      .then((data) => {
        if (!cancelled) setMeta(data)
      })
      .catch((e) => {
        if (!cancelled) {
          const message = e instanceof Error ? e.message : String(e)
          setError(message.replace(/^Error:\s*/, ''))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [uuid])

  useEffect(() => {
    if (!uuid) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [uuid, onClose])

  if (!uuid) return null

  const titleParts = [
    meta?.date ? `Дата: ${meta.date}` : null,
    meta?.image_name ?? null,
  ].filter(Boolean)

  const showTaskActions = Boolean(taskActions?.canMarkDisruptionAbsent)

  const handleConfirmClear = async () => {
    if (!taskActions?.onMarkDisruptionAbsent) return
    setActionBusy(true)
    try {
      await taskActions.onMarkDisruptionAbsent()
    } finally {
      setActionBusy(false)
      setPendingClear(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal photo-modal" onClick={(e) => e.stopPropagation()}>
        <div className="photo-modal-header">
          <h2>Просмотр фотографии</h2>
          <button type="button" className="btn ghost small" onClick={onClose}>
            Закрыть
          </button>
        </div>

        {loading && <p className="muted">Загрузка…</p>}
        {error && <p className="error-banner">{error || 'Фото не найдено на сервере'}</p>}

        {meta && !error && (
          <>
            {titleParts.length > 0 && (
              <p className="muted small photo-modal-meta">{titleParts.join(' · ')}</p>
            )}
            <p className="muted small">UUID: {meta.uuid}</p>
            <div className="photo-modal-body">
              {imageError ? (
                <p className="error-banner">Не удалось загрузить изображение</p>
              ) : (
                <img
                  src={aiPhotoImageUrl(meta.uuid)}
                  alt={meta.image_name}
                  className="photo-modal-image"
                  onError={() => setImageError(true)}
                />
              )}
            </div>
          </>
        )}

        {showTaskActions && (
          <div className="photo-modal-footer">
            {pendingClear ? (
              <div className="status-confirm">
                <p>{CLEAR_CONFIRM_MESSAGE}</p>
                <div className="modal-action-buttons">
                  <button
                    type="button"
                    className="btn primary"
                    disabled={actionBusy}
                    onClick={() => void handleConfirmClear()}
                  >
                    Подтвердить
                  </button>
                  <button
                    type="button"
                    className="btn"
                    disabled={actionBusy}
                    onClick={() => setPendingClear(false)}
                  >
                    Отмена
                  </button>
                </div>
              </div>
            ) : (
              <div className="modal-action-buttons">
                <button
                  type="button"
                  className="btn btn-status-clear"
                  disabled={actionBusy}
                  onClick={() => setPendingClear(true)}
                >
                  Разрытие отсутствует
                </button>
                <button type="button" className="btn" disabled={actionBusy} onClick={onClose}>
                  Продолжить работу с задачей
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
