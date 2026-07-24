import { useEffect, useMemo, useState } from 'react'
import { fetchOatiLetterDraft, generateOatiLetter } from '../api/client'
import { formatTaskTableCell, type OatiLetterDraft } from '../types'

interface OatiLetterFormProps {
  taskKey: string
  reportId: number
  onClose: () => void
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function addressHint(draft: OatiLetterDraft): string {
  if (!draft.address_auto) return ' (укажите вручную при необходимости)'
  if (draft.address_has_house) return ' (авто, ближайший адрес)'
  return ' (авто, без номера дома — дополните вручную)'
}

export function OatiLetterForm({ taskKey, reportId, onClose }: OatiLetterFormProps) {
  const [draft, setDraft] = useState<OatiLetterDraft | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [executor, setExecutor] = useState('')
  const [address, setAddress] = useState('')
  const [engineering, setEngineering] = useState('')
  const [description, setDescription] = useState('')
  const [violation, setViolation] = useState('')
  const [selectedPhotoIds, setSelectedPhotoIds] = useState<number[]>([])

  useEffect(() => {
    let cancelled = false
    fetchOatiLetterDraft(taskKey, reportId)
      .then((data) => {
        if (cancelled) return
        setDraft(data)
        setExecutor(data.executor ?? '')
        setAddress(data.address ?? '')
        setEngineering(data.engineering ?? '')
        setDescription(data.description ?? '')
        setViolation(data.violation ?? '')
        setSelectedPhotoIds(data.photos.map((p) => p.id))
      })
      .catch((e) => {
        if (!cancelled) {
          const text = e instanceof Error ? e.message : String(e)
          setError(text.replace(/^Error:\s*/, ''))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [taskKey, reportId])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose, submitting])

  const allSelected = useMemo(() => {
    if (!draft?.photos.length) return false
    return draft.photos.every((p) => selectedPhotoIds.includes(p.id))
  }, [draft, selectedPhotoIds])

  const togglePhoto = (id: number) => {
    setSelectedPhotoIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const toggleAll = () => {
    if (!draft) return
    if (allSelected) setSelectedPhotoIds([])
    else setSelectedPhotoIds(draft.photos.map((p) => p.id))
  }

  const handleGenerate = async () => {
    setSubmitting(true)
    setError(null)
    setMessage(null)
    try {
      const result = await generateOatiLetter(taskKey, reportId, {
        executor,
        address,
        engineering,
        description,
        violation,
        photo_ids: selectedPhotoIds,
      })
      downloadBlob(result.blob, result.filename)
      setMessage(
        result.fid != null
          ? `Письмо №${result.fid} сформировано и скачано`
          : 'Письмо сформировано и скачано',
      )
    } catch (e) {
      const text = e instanceof Error ? e.message : String(e)
      setError(text.replace(/^Error:\s*/, ''))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => !submitting && onClose()}>
      <div
        className="modal photo-modal oati-letter-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="photo-modal-header">
          <h2>Формирование письма ОАТИ</h2>
          <button
            type="button"
            className="btn ghost small"
            disabled={submitting}
            onClick={onClose}
          >
            Закрыть
          </button>
        </div>

        {loading && <p className="muted">Загрузка черновика…</p>}
        {error && <p className="error-banner">{error}</p>}
        {message && <p className="success-banner">{message}</p>}

        {draft && !loading && (
          <>
            <div className="oati-letter-meta">
              <p>
                <strong>Улица (заголовок):</strong> {draft.street || '—'}
              </p>
              <p>
                <strong>Район:</strong> {draft.rayon || '—'}
              </p>
              <p>
                <strong>Дата письма:</strong> {draft.today}
              </p>
              <p>
                <strong>Дата фиксации:</strong> {draft.incident_datetime || '—'}
              </p>
              <p>
                <strong>Координаты WGS 84:</strong> {draft.coordinates}
              </p>
              <p className="muted small">Отчёт #{draft.report_id}</p>
            </div>

            {draft.map_warning && (
              <p className="warning-banner">{draft.map_warning}</p>
            )}

            <div className="oati-letter-form-grid">
              <label className="form-row">
                <span>1. Производитель работ (из источника задачи)</span>
                <input
                  type="text"
                  value={executor}
                  onChange={(e) => setExecutor(e.target.value)}
                  disabled={submitting}
                />
              </label>

              <label className="form-row">
                <span>3. Адрес{addressHint(draft)}</span>
                <input
                  type="text"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  disabled={submitting}
                  placeholder="улица, дом"
                />
              </label>

              <label className="form-row">
                <span>5. Вид коммуникаций (engineering_net_obj)</span>
                <input
                  type="text"
                  value={engineering}
                  onChange={(e) => setEngineering(e.target.value)}
                  disabled={submitting}
                />
              </label>

              <label className="form-row">
                <span>6. Описание данных</span>
                <textarea
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={submitting}
                />
              </label>

              <label className="form-row">
                <span>7. Признаки правонарушения / НПА</span>
                <textarea
                  rows={4}
                  value={violation}
                  onChange={(e) => setViolation(e.target.value)}
                  disabled={submitting}
                />
              </label>
            </div>

            <section className="oati-letter-photos">
              <div className="field-materials-gallery-header">
                <h3 className="field-materials-section-title">
                  Фото для приложения ({selectedPhotoIds.length} из {draft.photos.length})
                </h3>
                {draft.photos.length > 0 && (
                  <button
                    type="button"
                    className="btn small"
                    disabled={submitting}
                    onClick={toggleAll}
                  >
                    {allSelected ? 'Снять все' : 'Выбрать все'}
                  </button>
                )}
              </div>
              {draft.photos.length === 0 ? (
                <p className="muted">Фотографии для отчёта не найдены</p>
              ) : (
                <ul className="oati-letter-photo-list">
                  {draft.photos.map((photo) => {
                    const checked = selectedPhotoIds.includes(photo.id)
                    return (
                      <li key={photo.id} className="oati-letter-photo-item">
                        <label className="oati-letter-photo-label">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={submitting}
                            onChange={() => togglePhoto(photo.id)}
                          />
                          <img
                            src={photo.image_url}
                            alt={photo.label ?? photo.file_path}
                            className="oati-letter-photo-thumb"
                          />
                          <span className="oati-letter-photo-meta">
                            {photo.label ?? 'Фото'}
                            {photo.created_at
                              ? ` · ${formatTaskTableCell(photo.created_at, 'date')}`
                              : ''}
                          </span>
                        </label>
                      </li>
                    )
                  })}
                </ul>
              )}
            </section>

            <div className="modal-action-buttons oati-letter-actions">
              <button
                type="button"
                className="btn primary"
                disabled={submitting}
                onClick={() => void handleGenerate()}
              >
                {submitting ? 'Формирование…' : 'Скачать .docx'}
              </button>
              <button
                type="button"
                className="btn"
                disabled={submitting}
                onClick={onClose}
              >
                Отмена
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
