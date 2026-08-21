import { useEffect, useState } from 'react'
import { searchOrderGroup } from '../api/client'
import { TaskGroupMapView } from './TaskGroupMapView'
import type { OrderSearchHit, TaskGroupMapFeature } from '../types'
import { CRM_GROUP_ORDERS, ORDER_GROUP_SEARCH_FIELDS, formatTaskTableCell } from '../types'

interface OrderGroupSearchModalProps {
  rayon: string
  onClose: () => void
  onShowOnMap: (hit: OrderSearchHit) => void
}

function attrText(attrs: Record<string, unknown>, field: string | undefined): string {
  if (!field) return ''
  return formatTaskTableCell(attrs[field])
}

function hitTitle(hit: OrderSearchHit): string {
  const fields = ORDER_GROUP_SEARCH_FIELDS[hit.subgroup_name]
  return attrText(hit.attributes, fields?.id) || hit.layer_name
}

export function OrderGroupSearchModal({ rayon, onClose, onShowOnMap }: OrderGroupSearchModalProps) {
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<OrderSearchHit[]>([])
  const [errors, setErrors] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  const runSearch = async () => {
    const q = query.trim()
    if (q.length < 2) {
      setMessage('Введите не меньше 2 символов')
      setHits([])
      return
    }
    setLoading(true)
    setMessage('')
    setErrors([])
    try {
      const result = await searchOrderGroup(q, rayon)
      setHits(result.hits)
      setErrors(result.errors ?? [])
      if (!result.hits.length) {
        setMessage('Ничего не найдено')
      }
    } catch (e) {
      setHits([])
      setMessage(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal order-group-search-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <h2>Поиск по ордерам</h2>
        <p className="muted small">{CRM_GROUP_ORDERS}</p>
        <form
          className="order-group-search-form"
          onSubmit={(e) => {
            e.preventDefault()
            void runSearch()
          }}
        >
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Номер, исполнитель, заказчик или адрес"
            aria-label="Поиск по ордерам"
          />
          <button type="submit" className="btn primary" disabled={loading}>
            {loading ? 'Поиск…' : 'Найти'}
          </button>
        </form>
        {message && <p className="muted small">{message}</p>}
        {errors.length > 0 && (
          <p className="error-banner small">{errors.join('; ')}</p>
        )}
        {hits.length > 0 && (
          <div className="order-group-search-table-wrap">
            <table className="task-table order-group-search-table">
              <thead>
                <tr>
                  <th />
                  <th>Район</th>
                  <th>Номер</th>
                  <th>Исполнитель</th>
                  <th>Заказчик</th>
                  <th>Адрес</th>
                  <th>Тип</th>
                </tr>
              </thead>
              <tbody>
                {hits.map((hit, index) => {
                  const fields = ORDER_GROUP_SEARCH_FIELDS[hit.subgroup_name]
                  return (
                    <tr key={`${hit.layer_key}-${hit.task_key ?? index}`}>
                      <td className="order-group-search-action">
                        <button
                          type="button"
                          className="btn"
                          onClick={() => onShowOnMap(hit)}
                        >
                          Показать на карте
                        </button>
                      </td>
                      <td>
                        {hit.in_selected_rayon ? 'Этот район' : 'Другой район'}
                      </td>
                      <td>{attrText(hit.attributes, fields?.id)}</td>
                      <td>{attrText(hit.attributes, fields?.executor)}</td>
                      <td>{attrText(hit.attributes, fields?.customer)}</td>
                      <td>{attrText(hit.attributes, fields?.address)}</td>
                      <td>{hit.subgroup_name}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  )
}

interface OrderMapPreviewModalProps {
  hit: OrderSearchHit
  onClose: () => void
}

export function OrderMapPreviewModal({ hit, onClose }: OrderMapPreviewModalProps) {
  const selectedKey = hit.task_key || `search:${hit.layer_key}`
  const features: TaskGroupMapFeature[] = [
    {
      task_key: selectedKey,
      subgroup_name: hit.subgroup_name,
      source: 'active',
      layer_name: hit.layer_name,
      layer_key: hit.layer_key,
      geometry: hit.geometry ?? null,
      attributes: hit.attributes,
    },
  ]

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal order-map-preview-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <h2>Объект вне выбранного района</h2>
        <p className="muted small">
          {hit.subgroup_name}
          {hitTitle(hit) ? ` · ${hitTitle(hit)}` : ''}
        </p>
        {hit.geometry ? (
          <div className="task-group-map-wrap order-map-preview-wrap">
            <TaskGroupMapView features={features} selectedTaskKey={selectedKey} />
          </div>
        ) : (
          <p className="muted small">Нет геометрии у объекта</p>
        )}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  )
}
