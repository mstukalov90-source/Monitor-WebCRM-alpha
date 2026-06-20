import { useEffect, useState } from 'react'
import { fetchDistricts } from '../api/client'
import type { CollectProgress } from '../types'

interface DistrictStartScreenProps {
  rayon: string
  applyDateFilter: boolean
  loading: boolean
  error: string | null
  progress: CollectProgress | null
  onRayonChange: (v: string) => void
  onApplyDateFilterChange: (v: boolean) => void
  onCollect: () => void
}

export function DistrictStartScreen({
  rayon,
  applyDateFilter,
  loading,
  error,
  progress,
  onRayonChange,
  onApplyDateFilterChange,
  onCollect,
}: DistrictStartScreenProps) {
  const [districts, setDistricts] = useState<string[]>([])

  useEffect(() => {
    fetchDistricts()
      .then((d) => setDistricts(d.districts))
      .catch(() => setDistricts([]))
  }, [])

  return (
    <div className="district-screen">
      <div className="district-card">
        <h1>Monitor Web CRM</h1>
        <p className="district-hint">Выберите район для загрузки задач из crm.tasks</p>

        <label className="district-field">
          <span>Район</span>
          <select
            value={rayon}
            onChange={(e) => onRayonChange(e.target.value)}
            disabled={loading}
          >
            <option value="">— выберите район —</option>
            {districts.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>

        <label className="checkbox-label district-checkbox">
          <input
            type="checkbox"
            checked={applyDateFilter}
            onChange={(e) => onApplyDateFilterChange(e.target.checked)}
            disabled={loading}
          />
          Фильтр по дате (ордера и уведомления)
        </label>

        <button
          type="button"
          className="btn primary district-submit"
          disabled={!rayon || loading}
          onClick={onCollect}
        >
          {loading
            ? progress
              ? `Слой ${progress.current}/${progress.total}: ${progress.layerName}`
              : 'Подготовка…'
            : 'Получить задачу'}
        </button>

        {loading && progress && (
          <div className="collect-progress">
            <div
              className="collect-progress-bar"
              style={{ width: `${Math.round((progress.current / progress.total) * 100)}%` }}
            />
          </div>
        )}

        {error && <div className="error-banner">{error}</div>}
      </div>
    </div>
  )
}
