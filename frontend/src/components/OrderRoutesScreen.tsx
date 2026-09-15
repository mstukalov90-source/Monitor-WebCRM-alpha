import { useCallback, useEffect, useState } from 'react'
import {
  buildOrderRoute,
  fetchDistricts,
  fetchOrderRoute,
  fetchTasksArea,
  orderRouteGeoJsonUrl,
  orderRouteGpxUrl,
} from '../api/client'
import { useWorkspaceLayout } from '../hooks/useWorkspaceLayout'
import { areaOrderDisplayName } from '../lib/areaOrders'
import type { OrderRouteContext, TaskFeature } from '../types'
import { formatAreaHectares, formatAreaStatus, normalizeRayonName } from '../types'
import { areaStatusFromAttributes } from '../types'
import { OrderRouteMapView } from './OrderRouteMapView'
import { ResizeHandle } from './ResizeHandle'

interface OrderRoutesScreenProps {
  userLogin: string
  initialRayon?: string
  onBack: () => void
  onLogout: () => Promise<void>
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const mins = Math.round(seconds / 60)
  if (mins < 60) return `${mins} мин`
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return `${h} ч ${m} мин`
}

function formatDistance(metres: number | null | undefined): string {
  if (metres == null) return '—'
  if (metres < 1000) return `${Math.round(metres)} м`
  return `${(metres / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} км`
}

function formatPct(pct: number | null | undefined): string {
  if (pct == null) return '—'
  return `${pct.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`
}

function orderKeyOf(order: TaskFeature): string {
  return order.task_key ?? String(order.attributes.key ?? '')
}

export function OrderRoutesScreen({
  userLogin,
  initialRayon = '',
  onBack,
  onLogout,
}: OrderRoutesScreenProps) {
  const workspace = useWorkspaceLayout()
  const [districts, setDistricts] = useState<string[]>([])
  const [rayon, setRayon] = useState(initialRayon)
  const [orders, setOrders] = useState<TaskFeature[]>([])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [route, setRoute] = useState<OrderRouteContext | null>(null)
  const [loadingOrders, setLoadingOrders] = useState(false)
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectedOrder = orders.find((o) => orderKeyOf(o) === selectedKey) ?? null

  useEffect(() => {
    fetchDistricts()
      .then((d) => setDistricts(d.districts))
      .catch(() => setDistricts([]))
  }, [])

  const loadOrders = useCallback(async (district: string) => {
    if (!district) {
      setOrders([])
      setSelectedKey(null)
      setRoute(null)
      return
    }
    setLoadingOrders(true)
    setError(null)
    try {
      const result = await fetchTasksArea(district)
      const features = result.groups.flatMap((g) =>
        g.subgroups.flatMap((s) => s.features),
      )
      setOrders(features)
      setSelectedKey(features[0] ? orderKeyOf(features[0]) : null)
      setRoute(null)
      if (result.errors.length) setError(result.errors.join('; '))
    } catch (e) {
      setError(String(e))
      setOrders([])
      setSelectedKey(null)
      setRoute(null)
    } finally {
      setLoadingOrders(false)
    }
  }, [])

  useEffect(() => {
    if (rayon) void loadOrders(rayon)
  }, [rayon, loadOrders])

  useEffect(() => {
    if (!selectedKey) {
      setRoute(null)
      return
    }
    let cancelled = false
    fetchOrderRoute(selectedKey)
      .then((data) => {
        if (!cancelled) setRoute(data)
      })
      .catch(() => {
        if (!cancelled) setRoute(null)
      })
    return () => {
      cancelled = true
    }
  }, [selectedKey])

  const handleBuild = async () => {
    if (!selectedKey) return
    setBuilding(true)
    setError(null)
    try {
      const data = await buildOrderRoute(selectedKey)
      setRoute(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setBuilding(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="workspace-header">
          <h1>Маршруты обследования</h1>
          <div className="workspace-meta">
            <span className="muted">{userLogin}</span>
            <label className="district-field district-field-inline">
              <span>Район</span>
              <select
                value={rayon}
                onChange={(e) => setRayon(e.target.value)}
                disabled={loadingOrders || building}
              >
                <option value="">— выберите район —</option>
                {districts.map((d) => (
                  <option key={d} value={d}>
                    {normalizeRayonName(d)}
                  </option>
                ))}
              </select>
            </label>
            {rayon && <span className="muted">Заказов: {orders.length}</span>}
            <button type="button" className="btn" onClick={onBack}>
              Назад
            </button>
            <button type="button" className="btn" onClick={() => void onLogout()}>
              Выйти
            </button>
            <button
              type="button"
              className="btn"
              disabled={!rayon || loadingOrders || building}
              onClick={() => void loadOrders(rayon)}
            >
              {loadingOrders ? 'Обновление…' : 'Обновить'}
            </button>
          </div>
        </div>
        {error && <div className="error-banner">{error}</div>}
      </header>

      <div
        ref={workspace.appBodyRef}
        className={`app-body${workspace.resizing ? ' app-body--resizing' : ''}`}
        style={workspace.layoutStyle}
      >
        <aside className="sidebar">
          {!rayon ? (
            <div className="task-panel empty">
              <p>Выберите район, затем заказ — и постройте маршрут</p>
            </div>
          ) : (
            <div className="task-panel order-routes-panel">
              <h2 className="task-panel-title">Площадные заказы</h2>
              {loadingOrders ? (
                <p className="muted">Загрузка…</p>
              ) : orders.length === 0 ? (
                <p className="muted small">Нет заказов в районе</p>
              ) : (
                <ul className="order-status-list">
                  {orders.map((order) => {
                    const key = orderKeyOf(order)
                    const attrs = order.attributes
                    const selected = key === selectedKey
                    const survey = formatAreaStatus(areaStatusFromAttributes(attrs)) || '—'
                    return (
                      <li key={key}>
                        <button
                          type="button"
                          className={`order-status-item${selected ? ' selected' : ''}`}
                          disabled={building}
                          onClick={() => setSelectedKey(key)}
                        >
                          <span className="order-status-item-main">
                            {areaOrderDisplayName(attrs)}
                          </span>
                          <span className="order-status-item-meta muted small">
                            {survey}
                            {attrs.area != null ? ` · ${formatAreaHectares(attrs.area)}` : ''}
                          </span>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}

              {selectedOrder && (
                <div className="order-routes-actions">
                  <button
                    type="button"
                    className="btn primary"
                    disabled={building || !selectedKey}
                    onClick={() => void handleBuild()}
                  >
                    {building ? 'Строим маршрут…' : route ? 'Перестроить маршрут' : 'Построить маршрут'}
                  </button>
                  {route && selectedKey && (
                    <>
                      <a
                        href={orderRouteGpxUrl(selectedKey)}
                        className="btn"
                        download
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Скачать GPX
                      </a>
                      <a
                        href={orderRouteGeoJsonUrl(selectedKey)}
                        className="btn"
                        download
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Скачать GeoJSON
                      </a>
                    </>
                  )}
                </div>
              )}

              {route && (
                <table className="order-route-metrics-table">
                  <tbody>
                    <tr>
                      <td className="muted">Покрытие полигона</td>
                      <td>
                        <strong>{formatPct(route.polygon_coverage_pct)}</strong>
                      </td>
                    </tr>
                    <tr>
                      <td className="muted">Задачи в {route.buffer_m} м</td>
                      <td>
                        <strong>{formatPct(route.task_coverage_pct)}</strong>
                        {' '}
                        <span className="muted small">
                          ({route.tasks_covered ?? '?'} / {route.tasks_total})
                        </span>
                      </td>
                    </tr>
                    <tr>
                      <td className="muted">Длина</td>
                      <td>{formatDistance(route.total_distance_m)}</td>
                    </tr>
                    <tr>
                      <td className="muted">Время</td>
                      <td>{formatDuration(route.total_duration_s)}</td>
                    </tr>
                  </tbody>
                </table>
              )}
            </div>
          )}
        </aside>
        <ResizeHandle
          orientation="vertical"
          onResize={workspace.handleSidebarResize}
          onResizeStart={() => workspace.setResizing(true)}
          onResizeEnd={() => workspace.setResizing(false)}
        />
        <main ref={workspace.mapAreaRef} className="map-area">
          <div className="map-area-stack">
            <div className={`map-viewport${workspace.resizing ? ' map-viewport--resizing' : ''}`}>
              {selectedOrder?.geometry ? (
                <OrderRouteMapView
                  orderGeometry={selectedOrder.geometry}
                  routeGeometry={route?.route_geometry}
                  bufferGeometry={route?.buffer_geometry}
                  uncoveredGeometry={route?.uncovered_geometry}
                />
              ) : (
                <div className="task-panel empty map-placeholder">
                  <p className="muted">
                    {rayon
                      ? 'Выберите заказ слева'
                      : 'Карта появится после выбора района и заказа'}
                  </p>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
