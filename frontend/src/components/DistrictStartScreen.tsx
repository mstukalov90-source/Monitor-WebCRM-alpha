import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchAllTasksAreaGeoJson, fetchDistricts, fetchEmployeeLocations } from '../api/client'
import { DistrictPickerMap } from './DistrictPickerMap'
import {
  areaOrderDisplayName,
  geoJsonToAreaTaskFeatures,
  groupAreaOrdersByRayon,
} from '../lib/areaOrders'
import type { DistrictHoodMeta } from '../lib/hoodLayer'
import type { CollectProgress, EmployeeLocationFeature } from '../types'
import {
  analiseWorkflowStatus,
  analiseWorkflowStatusClass,
  areaStatusFromAttributes,
  formatAnaliseWorkflowStatus,
  formatAreaStatus,
  normalizeRayonName,
} from '../types'

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
  const [okrug, setOkrug] = useState('')
  const [hoodMeta, setHoodMeta] = useState<DistrictHoodMeta>({ okrugs: [], rayonToOkrug: {} })
  const [employeeLocations, setEmployeeLocations] = useState<EmployeeLocationFeature[]>([])
  const [areaOrdersLoading, setAreaOrdersLoading] = useState(false)
  const [areaOrdersError, setAreaOrdersError] = useState<string | null>(null)
  const [areaOrdersByRayon, setAreaOrdersByRayon] = useState<ReturnType<typeof groupAreaOrdersByRayon>>([])

  useEffect(() => {
    fetchDistricts()
      .then((d) => setDistricts(d.districts))
      .catch(() => setDistricts([]))
  }, [])

  const filteredDistricts = useMemo(() => {
    const okrugNorm = normalizeRayonName(okrug)
    if (!okrugNorm) return districts
    return districts.filter(
      (d) => hoodMeta.rayonToOkrug[normalizeRayonName(d)] === okrugNorm,
    )
  }, [districts, okrug, hoodMeta.rayonToOkrug])

  const handleOkrugChange = (value: string) => {
    setOkrug(value)
    if (!value) return
    const okrugNorm = normalizeRayonName(value)
    const rayonStillValid =
      rayon && hoodMeta.rayonToOkrug[normalizeRayonName(rayon)] === okrugNorm
    if (!rayonStillValid) {
      onRayonChange('')
    }
  }

  const handleRayonChange = (value: string) => {
    onRayonChange(value)
    if (!value) return
    const matchedOkrug = hoodMeta.rayonToOkrug[normalizeRayonName(value)]
    if (matchedOkrug && matchedOkrug !== normalizeRayonName(okrug)) {
      setOkrug(matchedOkrug)
    }
  }

  const handleHoodMeta = useCallback((meta: DistrictHoodMeta) => {
    setHoodMeta(meta)
  }, [])

  useEffect(() => {
    if (!rayon || okrug) return
    const matched = hoodMeta.rayonToOkrug[normalizeRayonName(rayon)]
    if (matched) setOkrug(matched)
  }, [rayon, okrug, hoodMeta.rayonToOkrug])

  useEffect(() => {
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
  }, [])

  useEffect(() => {
    if (!canManagePersonnel) {
      setEmployeeLocations([])
      return
    }

    let cancelled = false
    fetchEmployeeLocations()
      .then((result) => {
        if (!cancelled) setEmployeeLocations(result.locations)
      })
      .catch(() => {
        if (!cancelled) setEmployeeLocations([])
      })

    return () => {
      cancelled = true
    }
  }, [canManagePersonnel])

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
              ? 'Выберите округ и район для загрузки задач'
              : 'Выберите округ и район для загрузки задач в поле'}
          </p>

          <label className="district-field">
            <span>Округ</span>
            <select
              value={okrug}
              onChange={(e) => handleOkrugChange(e.target.value)}
              disabled={loading}
            >
              <option value="">— выберите округ —</option>
              {hoodMeta.okrugs.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>

          <label className="district-field">
            <span>Район</span>
            <select
              value={rayon}
              onChange={(e) => handleRayonChange(e.target.value)}
              disabled={loading}
            >
              <option value="">— выберите район —</option>
              {filteredDistricts.map((d) => (
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
                          const surveyStatus = areaStatusFromAttributes(attrs)
                          const surveyLabel = formatAreaStatus(surveyStatus) || '—'
                          const workflow = analiseWorkflowStatus(attrs)
                          const analiseLabel = formatAnaliseWorkflowStatus(attrs)
                          return (
                            <li key={key} className="district-orders-item">
                              <span className="district-orders-name" title={name}>
                                {name}
                              </span>
                              <span className="district-orders-statuses">
                                <span
                                  className={`area-survey-status area-survey-status-${surveyStatus}`}
                                  title={`Полевое обследование: ${surveyLabel}`}
                                >
                                  {surveyLabel}
                                </span>
                                <span
                                  className={`area-analise-status ${analiseWorkflowStatusClass(workflow)}`}
                                  title={`Анализ: ${analiseLabel}`}
                                >
                                  {analiseLabel}
                                </span>
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
          selectedOkrug={okrug}
          districts={filteredDistricts}
          onRayonSelect={handleRayonChange}
          onHoodMeta={handleHoodMeta}
          disabled={loading}
          employeeLocations={employeeLocations}
          areaOrdersByRayon={areaOrdersByRayon}
          areaOrdersReady={!areaOrdersLoading}
        />
      </div>
    </div>
  )
}
