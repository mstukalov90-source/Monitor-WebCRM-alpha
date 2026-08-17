import { useEffect, useMemo, useState } from 'react'
import { aiPhotoImageUrl, fetchAiPhotoMeta } from '../api/client'
import { parsePhotoBboxes } from '../lib/photoBboxes'
import { PhotoBboxOverlay } from './PhotoBboxOverlay'
import { PhotoLightboxImage } from './PhotoLightboxImage'
import { formatTaskTableCell, type AiPhotoMeta } from '../types'

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
  const [showBboxes, setShowBboxes] = useState(true)
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null)

  useEffect(() => {
    if (!uuid) {
      setMeta(null)
      setError(null)
      setImageError(false)
      setPendingClear(false)
      setActionBusy(false)
      setShowBboxes(true)
      setImageSize(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    setImageError(false)
    setMeta(null)
    setPendingClear(false)
    setActionBusy(false)
    setShowBboxes(true)
    setImageSize(null)

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

  const boxes = useMemo(() => parsePhotoBboxes(meta?.bboxes), [meta?.bboxes])
  const hasBboxes = boxes.length > 0

  if (!uuid) return null

  const titleParts = [
    meta?.date ? `Дата: ${formatTaskTableCell(meta.date, 'date')}` : null,
    meta?.image_name ?? null,
  ].filter(Boolean)

  const bboxOverlay =
    showBboxes && hasBboxes && imageSize ? (
      <PhotoBboxOverlay
        boxes={boxes}
        naturalWidth={imageSize.width}
        naturalHeight={imageSize.height}
      />
    ) : null

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
          <div className="photo-modal-header-actions">
            {hasBboxes && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={showBboxes}
                  onChange={(e) => setShowBboxes(e.target.checked)}
                />
                Разметка ИИ
              </label>
            )}
            <button type="button" className="btn ghost small" onClick={onClose}>
              Закрыть
            </button>
          </div>
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
                <PhotoLightboxImage
                  src={aiPhotoImageUrl(meta.uuid)}
                  alt={meta.image_name}
                  className="photo-modal-image"
                  overlay={bboxOverlay}
                  toolbarExtra={
                    hasBboxes ? (
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={showBboxes}
                          onChange={(e) => setShowBboxes(e.target.checked)}
                        />
                        Разметка ИИ
                      </label>
                    ) : null
                  }
                  onError={() => setImageError(true)}
                  onLoad={(e) => {
                    const img = e.currentTarget
                    if (img.naturalWidth > 0 && img.naturalHeight > 0) {
                      setImageSize({ width: img.naturalWidth, height: img.naturalHeight })
                    }
                  }}
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
