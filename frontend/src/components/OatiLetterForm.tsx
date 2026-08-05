import { useEffect, useMemo, useState } from 'react'
import {
  fetchOatiLetterDraft,
  fetchOatiMapPreview,
  generateOatiLetter,
} from '../api/client'
import { formatTaskTableCell, type OatiLetterDraft } from '../types'

interface OatiLetterFormProps {
  taskKey: string
  reportId: number
  onClose: () => void
}

type AddressSource = 'geocode' | 'mos' | 'manual'
type EngineeringSource = 'undefined' | 'absent' | 'list'

const ENGINEERING_UNDEFINED = 'не определено'
const ENGINEERING_ABSENT = 'отсутствует'

/** Native GET download — Chrome uses Content-Disposition for Cyrillic names (blob+download breaks). */
function triggerServerDownload(downloadUrl: string) {
  const link = document.createElement('a')
  link.href = downloadUrl
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
}

function defaultAddressSource(draft: OatiLetterDraft): AddressSource {
  const geocode = (draft.address_geocode ?? '').trim()
  const mos = (draft.address_mos ?? '').trim()
  if (geocode && draft.address_has_house) return 'geocode'
  if (mos) return 'mos'
  if (geocode) return 'geocode'
  return 'manual'
}

function defaultEngineeringSource(value: string): EngineeringSource {
  const text = value.trim().toLowerCase()
  if (text === ENGINEERING_UNDEFINED) return 'undefined'
  if (text === ENGINEERING_ABSENT) return 'absent'
  return 'list'
}

function addressSourceHint(source: AddressSource, draft: OatiLetterDraft): string {
  if (source === 'geocode') {
    if (draft.address_has_house) return ' (ближайший адрес)'
    return ' (ближайший адрес, без номера дома)'
  }
  if (source === 'mos') return ' (реестр адресов)'
  return ' (вручную)'
}

export function OatiLetterForm({ taskKey, reportId, onClose }: OatiLetterFormProps) {
  const [draft, setDraft] = useState<OatiLetterDraft | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [customer, setCustomer] = useState('')
  const [executor, setExecutor] = useState('')
  const [address, setAddress] = useState('')
  const [addressSource, setAddressSource] = useState<AddressSource>('manual')
  const [engineering, setEngineering] = useState('')
  const [engineeringSource, setEngineeringSource] = useState<EngineeringSource>('list')
  const [description, setDescription] = useState('')
  const [selectedViolations, setSelectedViolations] = useState<string[]>([])
  const [selectedPhotoIds, setSelectedPhotoIds] = useState<number[]>([])
  const [mapScale, setMapScale] = useState(1000)
  const [mapPreviewUrl, setMapPreviewUrl] = useState<string | null>(null)
  const [mapPreviewLoading, setMapPreviewLoading] = useState(false)
  const [mapPreviewError, setMapPreviewError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchOatiLetterDraft(taskKey, reportId)
      .then((data) => {
        if (cancelled) return
        setDraft(data)
        setCustomer(data.customer ?? '')
        setExecutor(data.executor ?? '')
        setAddress(data.address ?? '')
        setAddressSource(defaultAddressSource(data))
        const eng = data.engineering ?? ''
        setEngineering(eng)
        setEngineeringSource(defaultEngineeringSource(eng))
        setDescription(data.description ?? '')
        setSelectedViolations([])
        setSelectedPhotoIds(data.photos.map((p) => p.id))
        setMapScale(data.map_scale_default ?? 1000)
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
    if (!draft) return
    let cancelled = false
    let objectUrl: string | null = null
    setMapPreviewLoading(true)
    setMapPreviewError(null)
    fetchOatiMapPreview(taskKey, reportId, mapScale)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url)
          return
        }
        objectUrl = url
        setMapPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev)
          return url
        })
      })
      .catch((e) => {
        if (cancelled) return
        const text = e instanceof Error ? e.message : String(e)
        setMapPreviewError(text.replace(/^Error:\s*/, ''))
        setMapPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev)
          return null
        })
      })
      .finally(() => {
        if (!cancelled) setMapPreviewLoading(false)
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [draft, taskKey, reportId, mapScale])

  useEffect(() => {
    return () => {
      setMapPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return null
      })
    }
  }, [])

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

  const mapScales = draft?.map_scales?.length
    ? draft.map_scales
    : [1000, 2000, 5000, 10000]

  const geocodeAvailable = Boolean((draft?.address_geocode ?? '').trim())
  const mosAvailable = Boolean((draft?.address_mos ?? '').trim())
  const violationOptions = draft?.violation_options ?? []

  const selectAddressSource = (source: AddressSource) => {
    if (!draft) return
    setAddressSource(source)
    if (source === 'geocode') setAddress(draft.address_geocode ?? '')
    else if (source === 'mos') setAddress(draft.address_mos ?? '')
  }

  const selectEngineeringSource = (source: EngineeringSource) => {
    setEngineeringSource(source)
    if (source === 'undefined') setEngineering(ENGINEERING_UNDEFINED)
    else if (source === 'absent') setEngineering(ENGINEERING_ABSENT)
  }

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

  const toggleViolation = (name: string) => {
    setSelectedViolations((prev) =>
      prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name],
    )
  }

  const handleGenerate = async () => {
    setSubmitting(true)
    setError(null)
    setMessage(null)
    try {
      const result = await generateOatiLetter(taskKey, reportId, {
        customer,
        executor,
        address,
        engineering,
        description,
        violation_names: selectedViolations,
        photo_ids: selectedPhotoIds,
        map_scale: mapScale,
      })
      triggerServerDownload(result.download_url)
      setMessage(`Письмо №${result.fid} сформировано и скачано`)
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
                <span>1. Заказчик (из источника задачи)</span>
                <input
                  type="text"
                  value={customer}
                  onChange={(e) => setCustomer(e.target.value)}
                  disabled={submitting}
                />
              </label>

              <label className="form-row">
                <span>1. Исполнитель (из источника задачи)</span>
                <input
                  type="text"
                  value={executor}
                  onChange={(e) => setExecutor(e.target.value)}
                  disabled={submitting}
                />
              </label>

              <div className="form-row oati-address-block">
                <span>3. Адрес{addressSourceHint(addressSource, draft)}</span>
                <div className="oati-address-sources" role="radiogroup" aria-label="Источник адреса">
                  <label className="oati-address-source">
                    <input
                      type="radio"
                      name="oati-address-source"
                      checked={addressSource === 'geocode'}
                      disabled={submitting || !geocodeAvailable}
                      onChange={() => selectAddressSource('geocode')}
                    />
                    <span>
                      Ближайший адрес
                      {geocodeAvailable ? `: ${draft.address_geocode}` : ' (не найден)'}
                    </span>
                  </label>
                  <label className="oati-address-source">
                    <input
                      type="radio"
                      name="oati-address-source"
                      checked={addressSource === 'mos'}
                      disabled={submitting || !mosAvailable}
                      onChange={() => selectAddressSource('mos')}
                    />
                    <span>
                      Адрес по реестру адресов
                      {mosAvailable ? `: ${draft.address_mos}` : ' (не найден)'}
                    </span>
                  </label>
                  <label className="oati-address-source">
                    <input
                      type="radio"
                      name="oati-address-source"
                      checked={addressSource === 'manual'}
                      disabled={submitting}
                      onChange={() => selectAddressSource('manual')}
                    />
                    <span>Ввести вручную</span>
                  </label>
                </div>
                <input
                  type="text"
                  value={address}
                  onChange={(e) => {
                    setAddressSource('manual')
                    setAddress(e.target.value)
                  }}
                  disabled={submitting}
                  placeholder="улица, дом"
                />
              </div>

              <div className="form-row oati-engineering-block">
                <span>5. Вид коммуникаций</span>
                <div
                  className="oati-address-sources"
                  role="radiogroup"
                  aria-label="Вид коммуникаций"
                >
                  <label className="oati-address-source">
                    <input
                      type="radio"
                      name="oati-engineering-source"
                      checked={engineeringSource === 'undefined'}
                      disabled={submitting}
                      onChange={() => selectEngineeringSource('undefined')}
                    />
                    <span>не определено</span>
                  </label>
                  <label className="oati-address-source">
                    <input
                      type="radio"
                      name="oati-engineering-source"
                      checked={engineeringSource === 'absent'}
                      disabled={submitting}
                      onChange={() => selectEngineeringSource('absent')}
                    />
                    <span>отсутствует</span>
                  </label>
                  <label className="oati-address-source">
                    <input
                      type="radio"
                      name="oati-engineering-source"
                      checked={engineeringSource === 'list'}
                      disabled={submitting}
                      onChange={() => selectEngineeringSource('list')}
                    />
                    <span>из справочника / вручную</span>
                  </label>
                </div>
                <input
                  type="text"
                  list="oati-comms-options"
                  value={engineering}
                  onChange={(e) => {
                    setEngineeringSource('list')
                    setEngineering(e.target.value)
                  }}
                  disabled={submitting || engineeringSource !== 'list'}
                  placeholder="Выберите или введите вручную"
                />
                {draft.engineering_options.length > 0 && (
                  <datalist id="oati-comms-options">
                    {draft.engineering_options.map((name) => (
                      <option key={name} value={name} />
                    ))}
                  </datalist>
                )}
              </div>

              <label className="form-row">
                <span>6. Описание характера работ</span>
                <textarea
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={submitting}
                />
              </label>

              <div className="form-row oati-violation-block">
                <span>7. Признаки незаконности</span>
                {violationOptions.length === 0 ? (
                  <p className="muted">Справочник признаков пуст</p>
                ) : (
                  <div className="oati-violation-options">
                    {violationOptions.map((name) => {
                      const checked = selectedViolations.includes(name)
                      return (
                        <label key={name} className="oati-violation-option">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={submitting}
                            onChange={() => toggleViolation(name)}
                          />
                          <span>{name}</span>
                        </label>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>

            <section className="oati-letter-map-scale">
              <h3 className="field-materials-section-title">Масштаб ситуационного плана</h3>
              <div
                className="oati-map-scale-options"
                role="radiogroup"
                aria-label="Масштаб карты"
              >
                {mapScales.map((scale) => (
                  <label key={scale} className="oati-map-scale-option">
                    <input
                      type="radio"
                      name="oati-map-scale"
                      checked={mapScale === scale}
                      disabled={submitting}
                      onChange={() => setMapScale(scale)}
                    />
                    <span>1:{scale}</span>
                  </label>
                ))}
              </div>
              <div className="oati-map-preview">
                {mapPreviewLoading && <p className="muted">Загрузка превью карты…</p>}
                {mapPreviewError && (
                  <p className="error-banner">Превью: {mapPreviewError}</p>
                )}
                {mapPreviewUrl && !mapPreviewLoading && (
                  <img
                    src={mapPreviewUrl}
                    alt={`Ситуационный план 1:${mapScale}`}
                    className="oati-map-preview-img"
                  />
                )}
              </div>
            </section>

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
