import { useCallback, useEffect, useState } from 'react'
import { buildOrderRoute, fetchOrderRoute, orderRouteGpxUrl, orderRouteGeoJsonUrl } from '../api/client'
import type { OrderRouteContext } from '../types'

interface OrderRouteModalProps {
  orderKey: string
  taskNumber?: string | null
  rayon?: string | null
  /** If true, build a new route on mount; otherwise load the saved one. */
  autoBuild?: boolean
  onClose: () => void
  onRouteReady?: (route: OrderRouteContext) => void
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

export function OrderRouteModal({
  orderKey,
  taskNumber,
  rayon,
  autoBuild = true,
  onClose,
  onRouteReady,
}: OrderRouteModalProps) {
  const [data, setData] = useState<OrderRouteContext | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const heading = [taskNumber?.trim(), rayon?.trim()].filter(Boolean).join(' · ') || orderKey.slice(0, 8)

  const doLoad = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchOrderRoute(orderKey)
      setData(result)
      onRouteReady?.(result)
    } catch {
      // no saved route — will offer to build
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [orderKey, onRouteReady])

  const doBuild = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await buildOrderRoute(orderKey)
      setData(result)
      onRouteReady?.(result)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [orderKey, onRouteReady])

  useEffect(() => {
    if (autoBuild) {
      void doBuild()
    } else {
      void doLoad()
    }
  }, [autoBuild, doBuild, doLoad])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal order-route-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <h2>Маршрут обследования</h2>
        <p className="muted small">{heading}</p>

        {error && <p className="error-banner small">{error}</p>}

        {loading && <p className="muted">Строим маршрут… Это может занять до минуты.</p>}

        {data && !loading && (
          <>
            <div className="order-route-metrics">
              <table className="order-route-metrics-table">
                <tbody>
                  <tr>
                    <td className="muted">Покрытие полигона</td>
                    <td><strong>{formatPct(data.polygon_coverage_pct)}</strong></td>
                  </tr>
                  <tr>
                    <td className="muted">Задачи в радиусе {data.buffer_m} м</td>
                    <td>
                      <strong>{formatPct(data.task_coverage_pct)}</strong>
                      {' '}
                      <span className="muted small">
                        ({data.tasks_covered ?? '?'} / {data.tasks_total})
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <td className="muted">Длина маршрута</td>
                    <td>{formatDistance(data.total_distance_m)}</td>
                  </tr>
                  <tr>
                    <td className="muted">Время (пешком)</td>
                    <td>{formatDuration(data.total_duration_s)}</td>
                  </tr>
                  <tr>
                    <td className="muted">Профили</td>
                    <td>
                      {[...new Set(data.segments.map((s) => s.profile))].join(', ') || 'foot'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {data.polygon_coverage_pct != null && data.polygon_coverage_pct < 95 && (
              <p className="error-banner small">
                Покрытие &lt; 95%. Возможно, часть полигона не охвачена пешеходной
                сетью OSRM. Непокрытые зоны отмечены красным на карте.
              </p>
            )}

            {data.built_by && (
              <p className="muted small">
                Построил: {data.built_by}
                {data.built_at ? ` · ${new Date(data.built_at).toLocaleString('ru-RU')}` : ''}
              </p>
            )}
          </>
        )}

        <div className="modal-actions">
          {data && (
            <>
              <a
                href={orderRouteGpxUrl(orderKey)}
                className="btn"
                download
                target="_blank"
                rel="noopener noreferrer"
              >
                Скачать GPX
              </a>
              <a
                href={orderRouteGeoJsonUrl(orderKey)}
                className="btn"
                download
                target="_blank"
                rel="noopener noreferrer"
              >
                Скачать GeoJSON
              </a>
            </>
          )}
          <button
            type="button"
            className="btn primary"
            disabled={loading}
            onClick={() => void doBuild()}
          >
            {loading ? 'Строим…' : data ? 'Перестроить' : 'Построить маршрут'}
          </button>
          <button type="button" className="btn" disabled={loading} onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  )
}
