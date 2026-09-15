import { useState } from 'react'
import { uploadTasksAreaGpkg } from '../api/client'
import type { GpkgAreaImportResult } from '../types'

interface GpkgAreaUploadModalProps {
  onClose: () => void
  onSuccess?: () => void
}

export function GpkgAreaUploadModal({ onClose, onSuccess }: GpkgAreaUploadModalProps) {
  const [file, setFile] = useState<File | null>(null)
  const [inputKey, setInputKey] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<GpkgAreaImportResult | null>(null)

  const handleFile = (list: FileList | null) => {
    const next = list?.[0] ?? null
    setFile(next)
    setResult(null)
    setError(null)
  }

  const handleUpload = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const imported = await uploadTasksAreaGpkg(file)
      setResult(imported)
      setFile(null)
      setInputKey((n) => n + 1)
      onSuccess?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal zip-close-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Загрузить GeoPackage</h2>
        <p className="muted small">
          Новые полигоны попадут в площадные заказы со статусом «свободные». Номер задания
          назначит база. Не записывайте task_number и area из файла.
        </p>

        <label className="district-field">
          <span>Файл .gpkg</span>
          <input
            key={inputKey}
            type="file"
            accept=".gpkg,application/geopackage+sqlite3"
            disabled={loading}
            onChange={(e) => handleFile(e.target.files)}
          />
          <span className="muted small">{file ? file.name : 'файл не выбран'}</span>
        </label>

        {error && <p className="error-banner small">{error}</p>}

        {result && (
          <p className="muted small">
            Слой {result.layer} · CRS {result.srid} · создано: {result.inserted} · пропуск:{' '}
            {result.skipped}
          </p>
        )}

        {result && result.items.length > 0 && (
          <div className="zip-close-table-wrap">
            <table className="zip-close-table">
              <thead>
                <tr>
                  <th>номер</th>
                  <th>район</th>
                  <th>округ</th>
                  <th>статус</th>
                  <th>площадь, м²</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((item) => (
                  <tr key={item.key}>
                    <td>{item.task_number || item.key.slice(0, 8)}</td>
                    <td>{item.rayon || '—'}</td>
                    <td>{item.okrug_shor || '—'}</td>
                    <td>{item.status || '—'}</td>
                    <td>
                      {item.area != null
                        ? item.area.toLocaleString('ru-RU', { maximumFractionDigits: 1 })
                        : '—'}
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
            className="btn primary"
            disabled={loading || !file}
            onClick={() => void handleUpload()}
          >
            {loading ? 'Загрузка…' : 'Загрузить'}
          </button>
          <button type="button" className="btn" disabled={loading} onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  )
}
