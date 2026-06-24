import { useEffect, useState } from 'react'
import { fetchDistricts } from '../api/client'
import { DistrictPickerMap } from './DistrictPickerMap'
import type { CollectProgress } from '../types'
import { normalizeRayonName } from '../types'

interface DistrictStartScreenProps {
  rayon: string
  applyDateFilter: boolean
  loading: boolean
  error: string | null
  progress: CollectProgress | null
  canCollect: boolean
  canManagePersonnel?: boolean
  userLogin: string
  onRayonChange: (v: string) => void
  onApplyDateFilterChange: (v: boolean) => void
  onCollect: () => void
  onLoadFieldTasks: () => void
  onOpenPersonnel?: () => void
  onLogout: () => Promise<void>
}

export function DistrictStartScreen({
  rayon,
  applyDateFilter,
  loading,
  error,
  progress,
  canCollect,
  canManagePersonnel,
  userLogin,
  onRayonChange,
  onApplyDateFilterChange,
  onCollect,
  onLoadFieldTasks,
  onOpenPersonnel,
  onLogout,
}: DistrictStartScreenProps) {
  const [districts, setDistricts] = useState<string[]>([])

  useEffect(() => {
    fetchDistricts()
      .then((d) => setDistricts(d.districts))
      .catch(() => setDistricts([]))
  }, [])

  const handleSubmit = () => {
    if (canCollect) {
      void onCollect()
    } else {
      onLoadFieldTasks()
    }
  }

  return (
    <div className="district-screen">
      <div className="district-layout">
        <div className="district-card">
          <div className="workspace-meta district-user-meta">
            <span className="muted">{userLogin}</span>
            {canManagePersonnel && onOpenPersonnel && (
              <button type="button" className="btn" onClick={onOpenPersonnel}>
                Персонал
              </button>
            )}
            <button type="button" className="btn" onClick={() => void onLogout()}>
              Выйти
            </button>
          </div>

          <h1>Monitor Web CRM</h1>
          <p className="district-hint">
            {canCollect
              ? 'Выберите район для загрузки задач'
              : 'Выберите район для загрузки задач в поле'}
          </p>

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
                  {normalizeRayonName(d)}
                </option>
              ))}
            </select>
          </label>

          {canCollect && (
            <label className="checkbox-label district-checkbox">
              <input
                type="checkbox"
                checked={applyDateFilter}
                onChange={(e) => onApplyDateFilterChange(e.target.checked)}
                disabled={loading}
              />
              Фильтр по дате (ордера и уведомления)
            </label>
          )}

          <button
            type="button"
            className="btn primary district-submit"
            disabled={!rayon || loading}
            onClick={handleSubmit}
          >
            {loading
              ? progress
                ? `Слой ${progress.current}/${progress.total}: ${progress.layerName}`
                : 'Подготовка…'
              : canCollect
                ? 'Получить задачу'
                : 'Загрузить задачи'}
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

        <DistrictPickerMap
          selectedRayon={rayon}
          districts={districts}
          onRayonSelect={onRayonChange}
          disabled={loading}
        />
      </div>
    </div>
  )
}
