import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchDistricts, fetchOznMatch } from '../api/client'
import { useWorkspaceLayout } from '../hooks/useWorkspaceLayout'
import type { OznMatchOrder, OznMatchResult } from '../types'
import {
  formatAreaHectares,
  formatAreaStatus,
  normalizeRayonName,
} from '../types'
import { OznMatchMapView } from './OznMatchMapView'
import { OznMatchOrderModal } from './OznMatchOrderModal'
import { ResizeHandle } from './ResizeHandle'

interface OznMatchScreenProps {
  userLogin: string
  initialRayon?: string
  onBack: () => void
  onLogout: () => Promise<void>
}

function matchCountLabel(count: number): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return `${count} пересечение`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${count} пересечения`
  }
  return `${count} пересечений`
}

function orderTitle(order: OznMatchOrder): string {
  const number = order.task_number?.trim()
  return number || order.order_key.slice(0, 8)
}

export function OznMatchScreen({
  userLogin,
  initialRayon = '',
  onBack,
  onLogout,
}: OznMatchScreenProps) {
  const workspace = useWorkspaceLayout()
  const [districts, setDistricts] = useState<string[]>([])
  const [rayon, setRayon] = useState(initialRayon)
  const [data, setData] = useState<OznMatchResult | null>(null)
  const [selectedOrderKey, setSelectedOrderKey] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selectedRowRef = useRef<HTMLLIElement | null>(null)
  const selectFromMapRef = useRef(false)

  useEffect(() => {
    fetchDistricts()
      .then((d) => setDistricts(d.districts))
      .catch(() => setDistricts([]))
  }, [])

  const loadMatches = useCallback(async (district: string) => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchOznMatch(district || undefined)
      setData(result)
      setSelectedOrderKey(null)
      setModalOpen(false)
      if (result.errors.length) {
        setError(result.errors.join('; '))
      }
    } catch (e) {
      setError(String(e))
      setData(null)
      setSelectedOrderKey(null)
      setModalOpen(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadMatches(rayon)
  }, [rayon, loadMatches])

  useEffect(() => {
    if (!selectFromMapRef.current) return
    selectFromMapRef.current = false
    selectedRowRef.current?.scrollIntoView({ block: 'nearest' })
  }, [selectedOrderKey])

  const handleRayonChange = (value: string) => {
    setRayon(value)
    setSelectedOrderKey(null)
    setModalOpen(false)
  }

  const openOrder = useCallback((orderKey: string, fromMap = false) => {
    if (fromMap) selectFromMapRef.current = true
    setSelectedOrderKey(orderKey)
    setModalOpen(true)
  }, [])

  const handleSelectFromMap = useCallback((orderKey: string) => {
    openOrder(orderKey, true)
  }, [openOrder])

  const patchOrder = useCallback(
    (orderKey: string, patch: Partial<Pick<OznMatchOrder, 'status' | 'executor'>>) => {
      setData((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          orders: prev.orders.map((order) =>
            order.order_key === orderKey ? { ...order, ...patch } : order,
          ),
        }
      })
    },
    [],
  )

  const orders = data?.orders ?? []
  const oznObjects = data?.ozn_objects ?? []
  const matches = data?.matches ?? {}

  const selectedOrder = useMemo(
    () => orders.find((order) => order.order_key === selectedOrderKey) ?? null,
    [orders, selectedOrderKey],
  )

  const selectedOznObjects = useMemo(() => {
    if (!selectedOrderKey) return []
    const ids = new Set(matches[selectedOrderKey] ?? [])
    return oznObjects.filter((item) => ids.has(item.id))
  }, [matches, oznObjects, selectedOrderKey])

  const selectedOznCount = selectedOznObjects.length

  return (
    <div className="app">
      <header className="app-header">
        <div className="workspace-header">
          <h1>Сопоставление заказов ОЗН и Мониторинг</h1>
          <div className="workspace-meta">
            <span className="muted">{userLogin}</span>
            <label className="district-field district-field-inline">
              <span>Район</span>
              <select
                value={rayon}
                onChange={(e) => handleRayonChange(e.target.value)}
                disabled={loading}
              >
                <option value="">— все районы —</option>
                {districts.map((d) => (
                  <option key={d} value={d}>
                    {normalizeRayonName(d)}
                  </option>
                ))}
              </select>
            </label>
            <span className="muted">
              {loading ? 'загрузка…' : `заказов: ${orders.length}`}
            </span>
            <button type="button" className="btn" onClick={onBack}>
              К карте
            </button>
            <button type="button" className="btn" onClick={() => void onLogout()}>
              Выйти
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={loading}
              onClick={() => void loadMatches(rayon)}
            >
              {loading ? 'Обновление…' : 'Обновить'}
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
          <div className="task-panel ozn-match-panel">
            <p className="muted small">
              Свободные и полевые заказы Мониторинга с пересечениями ОЗН, от большего числа к меньшему.
              {selectedOrderKey
                ? ` Выбрано пересечений: ${selectedOznCount}.`
                : ''}
            </p>
            {loading && !data ? (
              <p className="muted">Загрузка…</p>
            ) : orders.length === 0 ? (
              <p className="muted">Нет пересекающихся заказов</p>
            ) : (
              <ul className="ozn-match-list">
                {orders.map((order) => (
                  <li
                    key={order.order_key}
                    ref={selectedOrderKey === order.order_key ? selectedRowRef : undefined}
                  >
                    <button
                      type="button"
                      className={`ozn-match-item${
                        selectedOrderKey === order.order_key ? ' selected' : ''
                      }`}
                      onClick={() => openOrder(order.order_key)}
                    >
                      <span className="ozn-match-item-title">{orderTitle(order)}</span>
                      <span className="muted small">
                        {order.rayon || '—'}
                        {order.status ? ` · ${formatAreaStatus(order.status) || order.status}` : ''}
                        {order.area != null ? ` · ${formatAreaHectares(order.area)}` : ''}
                      </span>
                      <span className="ozn-match-count">{matchCountLabel(order.match_count)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
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
              {orders.length > 0 ? (
                <OznMatchMapView
                  orders={orders}
                  oznObjects={oznObjects}
                  matches={matches}
                  selectedOrderKey={selectedOrderKey}
                  onSelectOrder={handleSelectFromMap}
                />
              ) : (
                <div className="task-panel empty map-placeholder">
                  <p className="muted">
                    {loading
                      ? 'Загрузка пересечений…'
                      : 'На карте появятся только пересекающиеся объекты'}
                  </p>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>

      {modalOpen && selectedOrder && (
        <OznMatchOrderModal
          order={selectedOrder}
          oznObjects={selectedOznObjects}
          onClose={() => setModalOpen(false)}
          onPatched={patchOrder}
        />
      )}
    </div>
  )
}
