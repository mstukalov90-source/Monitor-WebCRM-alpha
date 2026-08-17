import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchOrderStatusFeed, fetchPersonnelUsers } from '../api/client'
import { formatStatisticsAction, orderStatusDateRange } from '../lib/statisticsLabels'
import type { FieldScoreValue, PersonnelUser, StatisticsActionDetail } from '../types'
import { displayUserNameByLogin, FIELD_SCORE_LABELS } from '../types'

interface OrderStatusModalProps {
  onClose: () => void
  onSelectEvent: (event: StatisticsActionDetail) => void | Promise<void>
  onQualityAssessment?: (event: StatisticsActionDetail) => void
}

type OrderStatusTab = 'surveyed' | 'prepared' | 'closed'
type PeriodDays = 3 | 7 | 14 | 30

const PERIOD_OPTIONS: PeriodDays[] = [3, 7, 14, 30]

const TAB_ACTIONS: Record<OrderStatusTab, string[]> = {
  surveyed: ['field_order_closed'],
  prepared: ['office_pre_analise_completed'],
  closed: ['office_closed_legal', 'office_closed_illegal'],
}

const TAB_LABELS: Record<OrderStatusTab, string> = {
  surveyed: 'Обследованы в поле',
  prepared: 'Подготовлены в поле',
  closed: 'Закрыты легально / нелегально',
}

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

function qualityButtonLabel(orderScore: FieldScoreValue | null | undefined): string {
  if (!orderScore) return 'Оценка качества'
  return `Оценка: ${FIELD_SCORE_LABELS[orderScore]}`
}

function tabCount(counts: Record<string, number>, tab: OrderStatusTab): number {
  return TAB_ACTIONS[tab].reduce((sum, action) => sum + (counts[action] ?? 0), 0)
}

function EventList({
  events,
  users,
  busy,
  onSelect,
  onQualityAssessment,
}: {
  events: StatisticsActionDetail[]
  users: PersonnelUser[]
  busy: boolean
  onSelect: (event: StatisticsActionDetail) => void
  onQualityAssessment?: (event: StatisticsActionDetail) => void
}) {
  if (events.length === 0) {
    return <p className="muted small">Нет событий</p>
  }

  return (
    <ul className="order-status-list">
      {events.map((event) => {
        const scored = Boolean(event.order_score)
        return (
          <li key={`${event.action}-${event.object_key}-${event.created_at}`}>
            <div className="order-status-item-row">
              <button
                type="button"
                className="order-status-item"
                disabled={busy}
                onClick={() => onSelect(event)}
              >
                <span className="order-status-item-main">{eventLabel(event)}</span>
                <span className="order-status-item-meta muted small">
                  {formatEventDate(event.created_at)} ·{' '}
                  {displayUserNameByLogin(event.user_login, users)} ·{' '}
                  {formatStatisticsAction(event.action)}
                </span>
              </button>
              {onQualityAssessment && (
                <button
                  type="button"
                  className={`btn order-status-quality-btn${
                    scored ? ' order-status-quality-btn--scored' : ''
                  }`}
                  disabled={busy}
                  title={
                    scored && event.order_score
                      ? `Оценка заказа: ${FIELD_SCORE_LABELS[event.order_score]}`
                      : undefined
                  }
                  onClick={(e) => {
                    e.stopPropagation()
                    onQualityAssessment(event)
                  }}
                >
                  {qualityButtonLabel(event.order_score)}
                </button>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export function OrderStatusModal({
  onClose,
  onSelectEvent,
  onQualityAssessment,
}: OrderStatusModalProps) {
  const [periodDays, setPeriodDays] = useState<PeriodDays>(7)
  const [activeTab, setActiveTab] = useState<OrderStatusTab>('surveyed')
  const [events, setEvents] = useState<StatisticsActionDetail[]>([])
  const [users, setUsers] = useState<PersonnelUser[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dateRange = useMemo(() => orderStatusDateRange(periodDays), [periodDays])

  useEffect(() => {
    fetchPersonnelUsers()
      .then(setUsers)
      .catch(() => setUsers([]))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchOrderStatusFeed({
        dateFrom: dateRange.dateFrom,
        dateTo: dateRange.dateTo,
        actions: TAB_ACTIONS[activeTab],
      })
      setEvents(result.events)
      setCounts(result.counts ?? {})
    } catch (e) {
      setError(String(e))
      setEvents([])
      setCounts({})
    } finally {
      setLoading(false)
    }
  }, [activeTab, dateRange.dateFrom, dateRange.dateTo])

  useEffect(() => {
    void load()
  }, [load])

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
      <div className="modal order-status-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Состояние заказов</h2>
        <p className="muted small">
          События за последние {periodDays} дн. ({dateRange.dateFrom} — {dateRange.dateTo})
        </p>

        <div className="statistics-view-toggle" role="tablist" aria-label="Период">
          {PERIOD_OPTIONS.map((days) => (
            <button
              key={days}
              type="button"
              role="tab"
              className={`btn${periodDays === days ? ' primary' : ''}`}
              aria-selected={periodDays === days}
              disabled={loading || busy}
              onClick={() => setPeriodDays(days)}
            >
              {days} дн.
            </button>
          ))}
        </div>

        <div className="statistics-view-toggle" role="tablist" aria-label="Тип событий">
          {(Object.keys(TAB_LABELS) as OrderStatusTab[]).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              className={`btn${activeTab === tab ? ' primary' : ''}`}
              aria-selected={activeTab === tab}
              disabled={loading || busy}
              onClick={() => setActiveTab(tab)}
            >
              {TAB_LABELS[tab]} ({tabCount(counts, tab)})
            </button>
          ))}
        </div>

        {error && <p className="error-banner small">{error}</p>}
        {loading ? (
          <p className="muted">Загрузка…</p>
        ) : (
          <section className="order-status-section">
            <EventList
              events={events}
              users={users}
              busy={busy}
              onSelect={(e) => void handleSelect(e)}
              onQualityAssessment={
                activeTab === 'surveyed' ? onQualityAssessment : undefined
              }
            />
          </section>
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
