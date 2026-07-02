import { useEffect, useMemo, useState } from 'react'
import { fetchFieldPhotos } from '../api/client'
import { PhotoLightboxImage } from './PhotoLightboxImage'
import { formatTaskTableCell, type FieldPhoto, type FieldPhotosResult } from '../types'

interface FieldMaterialsModalProps {
  taskKey: string | null
  onClose: () => void
}

export function FieldMaterialsModal({ taskKey, onClose }: FieldMaterialsModalProps) {
  const [result, setResult] = useState<FieldPhotosResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [galleryIndex, setGalleryIndex] = useState(0)
  const [imageError, setImageError] = useState(false)

  const bannerPhoto = useMemo(
    () => result?.photos.find((photo) => photo.banner) ?? null,
    [result],
  )
  const galleryPhotos = useMemo(
    () => result?.photos.filter((photo) => !photo.banner) ?? [],
    [result],
  )
  const currentGalleryPhoto: FieldPhoto | null = galleryPhotos[galleryIndex] ?? null

  useEffect(() => {
    if (!taskKey) {
      setResult(null)
      setError(null)
      setGalleryIndex(0)
      setImageError(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    setResult(null)
    setGalleryIndex(0)
    setImageError(false)

    fetchFieldPhotos(taskKey)
      .then((data) => {
        if (!cancelled) setResult(data)
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
  }, [taskKey])

  useEffect(() => {
    setImageError(false)
  }, [galleryIndex, bannerPhoto?.id])

  useEffect(() => {
    if (!taskKey) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft' && galleryPhotos.length > 1) {
        setGalleryIndex((idx) => (idx - 1 + galleryPhotos.length) % galleryPhotos.length)
      }
      if (e.key === 'ArrowRight' && galleryPhotos.length > 1) {
        setGalleryIndex((idx) => (idx + 1) % galleryPhotos.length)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [taskKey, onClose, galleryPhotos.length])

  if (!taskKey) return null

  const hasPhotos = (result?.photos.length ?? 0) > 0
  const showEmpty = !loading && !error && result != null && !hasPhotos

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal photo-modal field-materials-modal" onClick={(e) => e.stopPropagation()}>
        <div className="photo-modal-header">
          <h2>Просмотр полевых материалов</h2>
          <button type="button" className="btn ghost small" onClick={onClose}>
            Закрыть
          </button>
        </div>

        {loading && <p className="muted">Загрузка…</p>}
        {error && <p className="error-banner">{error}</p>}
        {showEmpty && <p className="muted">Материалы не найдены</p>}

        {result && !error && hasPhotos && (
          <>
            <section className="field-materials-banner">
              <h3 className="field-materials-section-title">Фото баннера</h3>
              {bannerPhoto ? (
                <>
                  <p className="muted small photo-modal-meta">
                    {[
                      bannerPhoto.label,
                      bannerPhoto.created_at
                        ? `Дата: ${formatTaskTableCell(bannerPhoto.created_at, 'date')}`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                  <div className="photo-modal-body">
                    <PhotoLightboxImage
                      src={bannerPhoto.image_url}
                      alt={bannerPhoto.label ?? bannerPhoto.file_path}
                      className="photo-modal-image"
                    />
                  </div>
                </>
              ) : (
                <p className="field-materials-banner-missing">Фото баннера отсутствует</p>
              )}
            </section>

            {galleryPhotos.length > 0 && (
              <section className="field-materials-gallery">
                <div className="field-materials-gallery-header">
                  <h3 className="field-materials-section-title">
                    {galleryPhotos.length === 1 ? 'Фото' : `Фото (${galleryIndex + 1} из ${galleryPhotos.length})`}
                  </h3>
                  {galleryPhotos.length > 1 && (
                    <div className="field-materials-nav">
                      <button
                        type="button"
                        className="btn small"
                        onClick={() =>
                          setGalleryIndex(
                            (idx) => (idx - 1 + galleryPhotos.length) % galleryPhotos.length,
                          )
                        }
                      >
                        ←
                      </button>
                      <button
                        type="button"
                        className="btn small"
                        onClick={() => setGalleryIndex((idx) => (idx + 1) % galleryPhotos.length)}
                      >
                        →
                      </button>
                    </div>
                  )}
                </div>
                {currentGalleryPhoto && (
                  <>
                    {currentGalleryPhoto.created_at && (
                      <p className="muted small photo-modal-meta">
                        Дата: {formatTaskTableCell(currentGalleryPhoto.created_at, 'date')}
                      </p>
                    )}
                    <div className="photo-modal-body">
                      {imageError ? (
                        <p className="error-banner">Не удалось загрузить изображение</p>
                      ) : (
                        <PhotoLightboxImage
                          src={currentGalleryPhoto.image_url}
                          alt={currentGalleryPhoto.file_path}
                          className="photo-modal-image"
                          onError={() => setImageError(true)}
                        />
                      )}
                    </div>
                  </>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </div>
  )
}
