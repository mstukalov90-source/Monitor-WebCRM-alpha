import { useEffect, useState } from 'react'
import { fetchLensPhotos } from '../api/client'
import {
  getStoredLensPhotoFolder,
  isLensPhotoFolderApiSupported,
  pickLensPhotoFolder,
  resolveFileFromLensFolder,
  windowsPathToFileUrl,
  type LensPhotoFolderHandle,
} from '../lib/lensPhotoFolder'
import { PhotoLightboxImage } from './PhotoLightboxImage'
import type { LensPhoto } from '../types'

const CLEAR_CONFIRM_MESSAGE = 'Отметить задачу: разрытие отсутствует?'

export interface LensPhotoModalTaskActions {
  canMarkDisruptionAbsent: boolean
  onMarkDisruptionAbsent: () => Promise<void>
}

interface LensPhotoModalProps {
  externalReportId: string | null
  onClose: () => void
  taskActions?: LensPhotoModalTaskActions
}

export function LensPhotoModal({ externalReportId, onClose, taskActions }: LensPhotoModalProps) {
  const [photos, setPhotos] = useState<LensPhoto[]>([])
  const [index, setIndex] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [folder, setFolder] = useState<LensPhotoFolderHandle | null>(null)
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const [folderError, setFolderError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [pendingClear, setPendingClear] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const folderApi = isLensPhotoFolderApiSupported()

  useEffect(() => {
    if (!externalReportId) {
      setPhotos([])
      setError(null)
      setIndex(0)
      setPendingClear(false)
      setActionBusy(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    setPhotos([])
    setIndex(0)
    setPendingClear(false)
    setActionBusy(false)

    fetchLensPhotos(externalReportId)
      .then((data) => {
        if (!cancelled) setPhotos(data.photos)
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
  }, [externalReportId])

  useEffect(() => {
    if (!externalReportId) {
      setFolder(null)
      return
    }
    let cancelled = false
    getStoredLensPhotoFolder().then((handle) => {
      if (!cancelled) setFolder(handle)
    })
    return () => {
      cancelled = true
    }
  }, [externalReportId])

  const current = photos[index] ?? null

  useEffect(() => {
    let cancelled = false

    if (!current || !folder) {
      setObjectUrl(null)
      setFolderError(null)
      return
    }

    setFolderError(null)
    setObjectUrl(null)

    resolveFileFromLensFolder(folder, current.relative_path)
      .then((file) => {
        if (cancelled) return
        if (!file) {
          setFolderError('Файл не найден в выбранной папке')
          return
        }
        setObjectUrl(URL.createObjectURL(file))
      })
      .catch(() => {
        if (!cancelled) setFolderError('Не удалось открыть файл из выбранной папки')
      })

    return () => {
      cancelled = true
    }
  }, [current, folder])

  useEffect(() => {
    if (!externalReportId) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft' && photos.length > 1) {
        setIndex((idx) => (idx - 1 + photos.length) % photos.length)
      }
      if (e.key === 'ArrowRight' && photos.length > 1) {
        setIndex((idx) => (idx + 1) % photos.length)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [externalReportId, onClose, photos.length])

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1500)
    return () => window.clearTimeout(timer)
  }, [copied])

  useEffect(() => {
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [objectUrl])

  if (!externalReportId) return null

  const showTaskActions = Boolean(taskActions?.canMarkDisruptionAbsent)
  const showEmpty = !loading && !error && photos.length === 0

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

  const handleCopyPath = async () => {
    if (!current) return
    try {
      await navigator.clipboard.writeText(current.windows_path)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  const handlePickFolder = async () => {
    try {
      const handle = await pickLensPhotoFolder()
      setFolder(handle)
      setFolderError(null)
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      setFolderError(e instanceof Error ? e.message : String(e))
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
        {error && <p className="error-banner">{error}</p>}
        {showEmpty && <p className="muted">Фото не найдены</p>}

        {current && !error && (
          <>
            <div className="field-materials-gallery-header">
              <p className="muted small photo-modal-meta">
                {photos.length > 1
                  ? `${current.file_name} (${index + 1} из ${photos.length})`
                  : current.file_name}
              </p>
              {photos.length > 1 && (
                <div className="field-materials-nav">
                  <button
                    type="button"
                    className="btn small"
                    onClick={() => setIndex((idx) => (idx - 1 + photos.length) % photos.length)}
                  >
                    ←
                  </button>
                  <button
                    type="button"
                    className="btn small"
                    onClick={() => setIndex((idx) => (idx + 1) % photos.length)}
                  >
                    →
                  </button>
                </div>
              )}
            </div>

            {objectUrl ? (
              <div className="photo-modal-body">
                <PhotoLightboxImage
                  src={objectUrl}
                  alt={current.file_name}
                  className="photo-modal-image"
                />
              </div>
            ) : (
              <div className="lens-photo-fallback">
                {folderError && <p className="error-banner">{folderError}</p>}
                <p className="muted small">
                  Файлы лежат на сетевом диске. Выберите папку «Объектив», чтобы открыть фото
                  в браузере, или скопируйте путь и откройте его в Проводнике.
                </p>
                <a
                  className="lens-photo-path"
                  href={windowsPathToFileUrl(current.windows_path)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {current.windows_path}
                </a>
                <div className="lens-photo-actions">
                  <a
                    className="btn primary"
                    href={windowsPathToFileUrl(current.windows_path)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Просмотр фото
                  </a>
                  <button type="button" className="btn" onClick={() => void handleCopyPath()}>
                    {copied ? 'Скопировано' : 'Копировать путь'}
                  </button>
                  {folderApi && (
                    <button type="button" className="btn" onClick={() => void handlePickFolder()}>
                      Выбрать папку Объектив
                    </button>
                  )}
                </div>
              </div>
            )}

            {objectUrl && (
              <div className="lens-photo-actions lens-photo-actions-below">
                <a
                  className="btn primary small"
                  href={windowsPathToFileUrl(current.windows_path)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Просмотр фото
                </a>
                {folderApi && (
                  <button type="button" className="btn small" onClick={() => void handlePickFolder()}>
                    Сменить папку
                  </button>
                )}
                <button type="button" className="btn small" onClick={() => void handleCopyPath()}>
                  {copied ? 'Скопировано' : 'Копировать путь'}
                </button>
              </div>
            )}
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
