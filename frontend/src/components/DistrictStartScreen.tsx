import { useEffect, useMemo, useState } from 'react'
import { fetchAllTasksAreaGeoJson, fetchDistricts } from '../api/client'
import { DistrictPickerMap } from './DistrictPickerMap'
import {
  areaOrderDisplayName,
  geoJsonToAreaTaskFeatures,
  groupAreaOrdersByRayon,
} from '../lib/areaOrders'
import type { CollectProgress } from '../types'
import { formatAnaliseWorkflowStatus, analiseWorkflowStatus, analiseWorkflowStatusClass, normalizeRayonName } from '../types'

interface DistrictStartScreenProps {
  rayon: string
  applyDateFilter: boolean
  loading: boolean
  error: string | null
  progress: CollectProgress | null
  canCollect: boolean
  canManagePersonnel?: boolean
  showAreaOrders?: boolean
  userLogin: string
  onRayonChange: (v: string) => void
  onApplyDateFilterChange: (v: boolean) => void
  onCollect: () => void
  onLoadFieldTasks: () => void
  onOpenPersonnel?: () => void
  onOpenEmployeeLocations?: () => void
  onOpenOrderTracks?: () => void
  onOpenStatistics?: () => void
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
  showAreaOrders = false,
  userLogin,
  onRayonChange,
  onApplyDateFilterChange,
  onCollect,
  onLoadFieldTasks,
  onOpenPersonnel,
  onOpenEmployeeLocations,
  onOpenOrderTracks,
  onOpenStatistics,
  onLogout,
}: DistrictStartScreenProps) {
  const [districts, setDistricts] = useState<string[]>([])
  const [areaOrdersLoading, setAreaOrdersLoading] = useState(false)
  const [areaOrdersError, setAreaOrdersError] = useState<string | null>(null)
  const [areaOrdersByRayon, setAreaOrdersByRayon] = useState<ReturnType<typeof groupAreaOrdersByRayon>>([])

  useEffect(() => {
    fetchDistricts()
      .then((d) => setDistricts(d.districts))
      .catch(() => setDistricts([]))
  }, [])

  useEffect(() => {
    if (!showAreaOrders) {
      setAreaOrdersByRayon([])
      setAreaOrdersError(null)
      return
    }

    let cancelled = false
    setAreaOrdersLoading(true)
    setAreaOrdersError(null)

    fetchAllTasksAreaGeoJson()
      .then((geojson) => {
        if (cancelled) return
        const orders = geoJsonToAreaTaskFeatures(geojson)
        setAreaOrdersByRayon(groupAreaOrdersByRayon(orders))
      })
      .catch((e) => {
        if (cancelled) return
        setAreaOrdersByRayon([])
        setAreaOrdersError(String(e))
      })
      .finally(() => {
        if (!cancelled) setAreaOrdersLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [showAreaOrders])

  const totalOrdersCount = useMemo(
    () => areaOrdersByRayon.reduce((sum, group) => sum + group.orders.length, 0),
    [areaOrdersByRayon],
  )

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
            {canManagePersonnel && onOpenEmployeeLocations && (
              <button type="button" className="btn" onClick={onOpenEmployeeLocations}>
                Местоположение сотрудника
              </button>
            )}
            {canManagePersonnel && onOpenOrderTracks && (
              <button type="button" className="btn" onClick={onOpenOrderTracks}>
                Треки заказов
              </button>
            )}
            {onOpenStatistics && (
              <button type="button" className="btn" onClick={onOpenStatistics}>
                Статистика
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

          {showAreaOrders && (
            <div className="district-orders-list">
              <h3 className="district-orders-title">Площадные заказы</h3>
              {areaOrdersLoading ? (
                <p className="muted small">Загрузка заказов…</p>
              ) : areaOrdersError ? (
                <p className="error-banner small">{areaOrdersError}</p>
              ) : totalOrdersCount === 0 ? (
                <p className="muted small">Нет площадных заказов</p>
              ) : (
                <div className="district-orders-groups">
                  {areaOrdersByRayon.map((group) => (
                    <section key={group.rayon} className="district-orders-group">
                      <h4 className="district-orders-group-title">{group.rayon}</h4>
                      <ul className="district-orders-items">
                        {group.orders.map((order) => {
                          const attrs = order.attributes
                          const key = order.task_key ?? String(attrs.key ?? '')
                          const name = areaOrderDisplayName(attrs)
                          const workflow = analiseWorkflowStatus(attrs)
                          const statusLabel = formatAnaliseWorkflowStatus(attrs)
                          return (
                            <li key={key} className="district-orders-item">
                              <span className="district-orders-name" title={name}>
                                {name}
                              </span>
                              <span
                                className={`area-analise-status ${analiseWorkflowStatusClass(workflow)}`}
                                title={statusLabel}
                              >
                                {statusLabel}
                              </span>
                            </li>
                          )
                        })}
                      </ul>
                    </section>
                  ))}
                </div>
              )}
            </div>
          )}

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
