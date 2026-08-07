import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchOrderStatusFeed } from '../api/client'
import {
  defaultOrderStatusDateRange,
  formatStatisticsAction,
} from '../lib/statisticsLabels'
import type { StatisticsActionDetail } from '../types'

interface OrderStatusModalProps {
  onClose: () => void
  onSelectEvent: (event: StatisticsActionDetail) => void | Promise<void>
}

const SURVEYED_ACTIONS = new Set(['field_order_closed'])
const PREPARED_ACTIONS = new Set(['office_pre_analise_completed'])
const CLOSED_ACTIONS = new Set(['office_closed_legal', 'office_closed_illegal'])

function formatEventDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ru-RU')
}

function eventLabel(event: StatisticsActionDetail): string {
  const parts: string[] = []
  if (event.task_number?.trim()) parts.push(event.task_number.trim())
  if (event.rayon?.trim()) parts.push(event.rayon.trim())
  if (!parts.length) parts.push(event.object_key.slice(0, 8))
  return parts.join(' · ')
}

function EventList({
  title,
  events,
  busy,
  onSelect,
}: {
  title: string
  events: StatisticsActionDetail[]
  busy: boolean
  onSelect: (event: StatisticsActionDetail) => void
}) {
  return (
    <section className="order-status-section">
      <h3 className="order-status-section-title">
        {title} <span className="muted">({events.length})</span>
      </h3>
      {events.length === 0 ? (
        <p className="muted small">Нет событий</p>
      ) : (
        <ul className="order-status-list">
          {events.map((event) => (
            <li key={`${event.action}-${event.object_key}-${event.created_at}`}>
              <button
                type="button"
                className="order-status-item"
                disabled={busy}
                onClick={() => onSelect(event)}
              >
                <span className="order-status-item-main">{eventLabel(event)}</span>
                <span className="order-status-item-meta muted small">
                  {formatEventDate(event.created_at)} · {event.user_login} ·{' '}
                  {formatStatisticsAction(event.action)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function OrderStatusModal({ onClose, onSelectEvent }: OrderStatusModalProps) {
  const initialRange = useMemo(() => defaultOrderStatusDateRange(), [])
  const [events, setEvents] = useState<StatisticsActionDetail[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchOrderStatusFeed({
        dateFrom: initialRange.dateFrom,
        dateTo: initialRange.dateTo,
      })
      setEvents(result.events)
    } catch (e) {
      setError(String(e))
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [initialRange.dateFrom, initialRange.dateTo])

  useEffect(() => {
    void load()
  }, [load])

  const surveyed = useMemo(
    () => events.filter((e) => SURVEYED_ACTIONS.has(e.action)),
    [events],
  )
  const prepared = useMemo(
    () => events.filter((e) => PREPARED_ACTIONS.has(e.action)),
    [events],
  )
  const closed = useMemo(
    () => events.filter((e) => CLOSED_ACTIONS.has(e.action)),
    [events],
  )

  const handleSelect = async (event: StatisticsActionDetail) => {
    setBusy(true)
    setError(null)
    try {
      await onSelectEvent(event)
    } catch (e) {
      setError(String(e))
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal order-status-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <h2>Состояние заказов</h2>
        <p className="muted small">
          События за последние 7 дней ({initialRange.dateFrom} — {initialRange.dateTo})
        </p>

        {error && <p className="error-banner small">{error}</p>}
        {loading ? (
          <p className="muted">Загрузка…</p>
        ) : (
          <div className="order-status-sections">
            <EventList
              title="Обследованы в поле"
              events={surveyed}
              busy={busy}
              onSelect={(e) => void handleSelect(e)}
            />
            <EventList
              title="Подготовлены в поле"
              events={prepared}
              busy={busy}
              onSelect={(e) => void handleSelect(e)}
            />
            <EventList
              title="Закрыты легально / нелегально"
              events={closed}
              busy={busy}
              onSelect={(e) => void handleSelect(e)}
            />
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="btn" disabled={loading || busy} onClick={() => void load()}>
            {loading ? 'Обновление…' : 'Обновить'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  )
}
