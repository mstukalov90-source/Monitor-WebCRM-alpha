import { useCallback, useEffect, useState } from 'react'
import {
  buildOrderRoute,
  downloadOrderRouteFile,
  fetchOrderRoute,
  orderRouteGeoJsonUrl,
  orderRouteGpxUrl,
} from '../api/client'
import {
  DEFAULT_ORDER_ROUTE_PROFILE,
  orderRouteDurationLabel,
  orderRouteProfileMeta,
} from '../lib/orderRouteProfile'
import type { OrderRouteContext, OrderRouteProfile } from '../types'
import { OrderRouteProfileSelect } from './OrderRouteProfileSelect'

interface OrderRouteModalProps {
  orderKey: string
  taskNumber?: string | null
  rayon?: string | null
  /** If true, load saved route on mount. Build only after the user picks a graph. */
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

function fallbackExportName(
  taskNumber: string | null | undefined,
  orderKey: string,
  profile: string,
  ext: string,
): string {
  const meta = orderRouteProfileMeta(profile)
  const stem = taskNumber?.trim() || orderKey.slice(0, 8)
  return `${stem}_${meta.letter}.${ext}`
}

export function OrderRouteModal({
  orderKey,
  taskNumber,
  rayon,
  onClose,
  onRouteReady,
}: OrderRouteModalProps) {
  const [data, setData] = useState<OrderRouteContext | null>(null)
  const [profile, setProfile] = useState<OrderRouteProfile>(DEFAULT_ORDER_ROUTE_PROFILE)
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const heading = [taskNumber?.trim(), rayon?.trim()].filter(Boolean).join(' · ') || orderKey.slice(0, 8)

  const doLoad = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchOrderRoute(orderKey)
      setData(result)
      if (result.profile) setProfile(result.profile)
      onRouteReady?.(result)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [orderKey, onRouteReady])

  const doBuild = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await buildOrderRoute(orderKey, null, profile)
      setData(result)
      if (result.profile) setProfile(result.profile)
      onRouteReady?.(result)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [orderKey, onRouteReady, profile])

  useEffect(() => {
    void doLoad()
  }, [doLoad])

  const handleDownload = async (kind: 'gpx' | 'geojson') => {
    setDownloading(true)
    setError(null)
    const usedProfile = data?.profile || profile
    const name = fallbackExportName(taskNumber ?? data?.order.task_number, orderKey, usedProfile, kind === 'gpx' ? 'gpx' : 'geojson')
    try {
      await downloadOrderRouteFile(
        kind === 'gpx' ? orderRouteGpxUrl(orderKey) : orderRouteGeoJsonUrl(orderKey),
        name,
      )
    } catch (e) {
      setError(String(e))
    } finally {
      setDownloading(false)
    }
  }

  const savedMeta = data ? orderRouteProfileMeta(data.profile) : null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal order-route-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <h2>Маршрут обследования</h2>
        <p className="muted small">{heading}</p>

        <OrderRouteProfileSelect value={profile} disabled={loading} onChange={setProfile} />

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
                    <td className="muted">{orderRouteDurationLabel(data.profile)}</td>
                    <td>{formatDuration(data.total_duration_s)}</td>
                  </tr>
                  <tr>
                    <td className="muted">Граф</td>
                    <td>
                      {savedMeta
                        ? `${savedMeta.label} (${savedMeta.letter})`
                        : data.profile || 'foot'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {data.polygon_coverage_pct != null && data.polygon_coverage_pct < 95 && (
              <p className="error-banner small">
                Покрытие &lt; 95%. Возможно, часть полигона не охвачена выбранной
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
              <button
                type="button"
                className="btn"
                disabled={loading || downloading}
                onClick={() => void handleDownload('gpx')}
              >
                Скачать GPX
              </button>
              <button
                type="button"
                className="btn"
                disabled={loading || downloading}
                onClick={() => void handleDownload('geojson')}
              >
                Скачать GeoJSON
              </button>
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
