import { useEffect, useMemo, useState } from 'react'
import { fetchFieldPhotos, fetchFieldReports } from '../api/client'
import { PhotoLightboxImage } from './PhotoLightboxImage'
import { OatiLetterForm } from './OatiLetterForm'
import {
  formatTaskTableCell,
  type FieldPhoto,
  type FieldPhotosResult,
  type FieldReportFeature,
} from '../types'

interface FieldMaterialsModalProps {
  taskKey: string | null
  reportId?: number | null
  canGenerateLetter?: boolean
  onClose: () => void
}

function reportScopeLabel(report: FieldReportFeature, index: number): string {
  const comment = report.comment?.trim()
  if (comment) {
    return comment.length > 36 ? `${comment.slice(0, 36)}…` : comment
  }
  const geomType = report.geometry?.type
  if (geomType === 'LineString' || geomType === 'MultiLineString') {
    return `Линия ${index + 1}`
  }
  if (geomType === 'Polygon' || geomType === 'MultiPolygon') {
    return `Полигон ${index + 1}`
  }
  return `Точка ${index + 1}`
}

export function FieldMaterialsModal({
  taskKey,
  reportId = null,
  canGenerateLetter = false,
  onClose,
}: FieldMaterialsModalProps) {
  const [result, setResult] = useState<FieldPhotosResult | null>(null)
  const [reports, setReports] = useState<FieldReportFeature[]>([])
  const [activeReportId, setActiveReportId] = useState<number | null>(reportId)
  const [loading, setLoading] = useState(false)
  const [reportsLoading, setReportsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [bannerIndex, setBannerIndex] = useState(0)
  const [galleryIndex, setGalleryIndex] = useState(0)
  const [bannerImageError, setBannerImageError] = useState(false)
  const [galleryImageError, setGalleryImageError] = useState(false)
  const [letterReportId, setLetterReportId] = useState<number | null>(null)

  const bannerPhotos = useMemo(
    () => result?.photos.filter((photo) => photo.banner) ?? [],
    [result],
  )
  const galleryPhotos = useMemo(
    () => result?.photos.filter((photo) => !photo.banner) ?? [],
    [result],
  )
  const currentBannerPhoto: FieldPhoto | null = bannerPhotos[bannerIndex] ?? null
  const currentGalleryPhoto: FieldPhoto | null = galleryPhotos[galleryIndex] ?? null
  const showScopeSwitcher = reports.length > 0

  useEffect(() => {
    setActiveReportId(reportId ?? null)
  }, [taskKey, reportId])

  useEffect(() => {
    if (!taskKey) {
      setReports([])
      setReportsLoading(false)
      return
    }

    let cancelled = false
    setReportsLoading(true)
    fetchFieldReports(taskKey)
      .then((data) => {
        if (cancelled) return
        const sorted = [...data.reports].sort((a, b) => a.report_id - b.report_id)
        setReports(sorted)
      })
      .catch(() => {
        if (!cancelled) setReports([])
      })
      .finally(() => {
        if (!cancelled) setReportsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [taskKey])

  useEffect(() => {
    if (!taskKey) {
      setResult(null)
      setError(null)
      setBannerIndex(0)
      setGalleryIndex(0)
      setBannerImageError(false)
      setGalleryImageError(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    setResult(null)
    setBannerIndex(0)
    setGalleryIndex(0)
    setBannerImageError(false)
    setGalleryImageError(false)

    fetchFieldPhotos(taskKey, { reportId: activeReportId })
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
  }, [taskKey, activeReportId])

  useEffect(() => {
    if (bannerIndex >= bannerPhotos.length && bannerPhotos.length > 0) {
      setBannerIndex(0)
    }
  }, [bannerIndex, bannerPhotos.length])

  useEffect(() => {
    if (galleryIndex >= galleryPhotos.length && galleryPhotos.length > 0) {
      setGalleryIndex(0)
    }
  }, [galleryIndex, galleryPhotos.length])

  useEffect(() => {
    setBannerImageError(false)
  }, [bannerIndex, currentBannerPhoto?.id])

  useEffect(() => {
    setGalleryImageError(false)
  }, [galleryIndex, currentGalleryPhoto?.id])

  useEffect(() => {
    if (!taskKey) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') {
        if (galleryPhotos.length > 1) {
          setGalleryIndex((idx) => (idx - 1 + galleryPhotos.length) % galleryPhotos.length)
        } else if (bannerPhotos.length > 1) {
          setBannerIndex((idx) => (idx - 1 + bannerPhotos.length) % bannerPhotos.length)
        }
      }
      if (e.key === 'ArrowRight') {
        if (galleryPhotos.length > 1) {
          setGalleryIndex((idx) => (idx + 1) % galleryPhotos.length)
        } else if (bannerPhotos.length > 1) {
          setBannerIndex((idx) => (idx + 1) % bannerPhotos.length)
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [taskKey, onClose, galleryPhotos.length, bannerPhotos.length])

  if (!taskKey) return null

  const hasPhotos = (result?.photos.length ?? 0) > 0
  const hasComment = Boolean(result?.comment?.trim())
  const showEmpty = !loading && !error && result != null && !hasPhotos && !hasComment
  const showBannerSection = bannerPhotos.length > 0 || activeReportId == null
  const title =
    activeReportId != null ? 'Фото полевого отчёта' : 'Просмотр полевых материалов'
  const showLetterButton = canGenerateLetter && activeReportId != null

  return (
    <>
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal photo-modal field-materials-modal" onClick={(e) => e.stopPropagation()}>
        <div className="photo-modal-header">
          <h2>{title}</h2>
          <div className="field-materials-header-actions">
            {showLetterButton && (
              <button
                type="button"
                className="btn primary small"
                onClick={() => setLetterReportId(activeReportId)}
              >
                Сформировать письмо
              </button>
            )}
            <button type="button" className="btn ghost small" onClick={onClose}>
              Закрыть
            </button>
          </div>
        </div>

        {showScopeSwitcher && (
          <div className="field-materials-scope" role="tablist" aria-label="Область материалов">
            <button
              type="button"
              role="tab"
              aria-selected={activeReportId == null}
              className={`btn small${activeReportId == null ? ' primary' : ''}`}
              onClick={() => setActiveReportId(null)}
            >
              Все материалы
            </button>
            {reports.map((report, index) => (
              <button
                key={report.report_id}
                type="button"
                role="tab"
                aria-selected={activeReportId === report.report_id}
                className={`btn small${activeReportId === report.report_id ? ' primary' : ''}`}
                title={report.comment?.trim() || `Отчёт #${report.report_id}`}
                onClick={() => setActiveReportId(report.report_id)}
              >
                {reportScopeLabel(report, index)}
              </button>
            ))}
          </div>
        )}
        {reportsLoading && !showScopeSwitcher && (
          <p className="muted small">Загрузка списка отчётов…</p>
        )}

        {loading && <p className="muted">Загрузка…</p>}
        {error && <p className="error-banner">{error}</p>}
        {showEmpty && <p className="muted">Материалы не найдены</p>}

        {result && !error && hasComment && (
          <section className="field-materials-comment">
            <h3 className="field-materials-section-title">Комментарий полевого сотрудника</h3>
            <p className="field-materials-comment-text">{result.comment?.trim()}</p>
          </section>
        )}

        {result && !error && hasPhotos && (
          <>
            {showBannerSection && (
              <section className="field-materials-banner">
                <div className="field-materials-gallery-header">
                  <h3 className="field-materials-section-title">
                    {bannerPhotos.length <= 1
                      ? 'Фото баннера'
                      : `Фото баннера (${bannerIndex + 1} из ${bannerPhotos.length})`}
                  </h3>
                  {bannerPhotos.length > 1 && (
                    <div className="field-materials-nav">
                      <button
                        type="button"
                        className="btn small"
                        onClick={() =>
                          setBannerIndex(
                            (idx) => (idx - 1 + bannerPhotos.length) % bannerPhotos.length,
                          )
                        }
                      >
                        ←
                      </button>
                      <button
                        type="button"
                        className="btn small"
                        onClick={() => setBannerIndex((idx) => (idx + 1) % bannerPhotos.length)}
                      >
                        →
                      </button>
                    </div>
                  )}
                </div>
                {currentBannerPhoto ? (
                  <>
                    <p className="muted small photo-modal-meta">
                      {[
                        currentBannerPhoto.label,
                        currentBannerPhoto.created_at
                          ? `Дата: ${formatTaskTableCell(currentBannerPhoto.created_at, 'date')}`
                          : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>
                    <div className="photo-modal-body">
                      {bannerImageError ? (
                        <p className="error-banner">Не удалось загрузить изображение</p>
                      ) : (
                        <PhotoLightboxImage
                          src={currentBannerPhoto.image_url}
                          alt={currentBannerPhoto.label ?? currentBannerPhoto.file_path}
                          className="photo-modal-image"
                          onError={() => setBannerImageError(true)}
                        />
                      )}
                    </div>
                  </>
                ) : (
                  <p className="field-materials-banner-missing">Фото баннера отсутствует</p>
                )}
              </section>
            )}

            {(galleryPhotos.length > 0 ||
              (activeReportId != null && bannerPhotos.length === 0 && hasPhotos)) && (
              <section className="field-materials-gallery">
                <div className="field-materials-gallery-header">
                  <h3 className="field-materials-section-title">
                    {galleryPhotos.length <= 1
                      ? 'Фото'
                      : `Фото (${galleryIndex + 1} из ${galleryPhotos.length})`}
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
                      {galleryImageError ? (
                        <p className="error-banner">Не удалось загрузить изображение</p>
                      ) : (
                        <PhotoLightboxImage
                          src={currentGalleryPhoto.image_url}
                          alt={currentGalleryPhoto.file_path}
                          className="photo-modal-image"
                          onError={() => setGalleryImageError(true)}
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
    {taskKey && letterReportId != null && (
      <OatiLetterForm
        key={`${taskKey}:${letterReportId}`}
        taskKey={taskKey}
        reportId={letterReportId}
        onClose={() => setLetterReportId(null)}
      />
    )}
    </>
  )
}
