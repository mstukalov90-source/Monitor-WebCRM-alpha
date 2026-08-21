import { useState } from 'react'
import type { CameraBlockMode } from '../types'

function tomorrowIsoDate(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

function formatIsoDateRu(iso: string): string {
  const [y, m, d] = iso.split('-')
  if (!y || !m || !d) return iso
  return `${d}.${m}.${y}`
}

interface CameraBlockModalProps {
  camId: string
  orderEndDate: string | null
  busy: boolean
  error?: string | null
  onSelect: (mode: CameraBlockMode, untilDate?: string) => void
  onSkip: () => void
}

export function CameraBlockModal({
  camId,
  orderEndDate,
  busy,
  error,
  onSelect,
  onSkip,
}: CameraBlockModalProps) {
  const [pickingDate, setPickingDate] = useState(false)
  const [untilDate, setUntilDate] = useState(tomorrowIsoDate)
  const minDate = tomorrowIsoDate()
  const orderLabel = orderEndDate ? formatIsoDateRu(orderEndDate) : null

  return (
    <div className="modal-backdrop camera-block-backdrop" onClick={busy ? undefined : onSkip}>
      <div className="modal camera-block-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Блокировать камеру?</h3>
        <p>
          Задача отправлена в поле. Не создавать новые задачи ГенПлана для камеры{' '}
          <strong>{camId}</strong>?
        </p>
        {error && <p className="error-banner small">{error}</p>}
        {pickingDate ? (
          <div className="status-confirm">
            <p>До какой даты не создавать новые задачи по этой камере?</p>
            <label className="form-row status-confirm-comment">
              <span>Дата (включительно)</span>
              <input
                type="date"
                value={untilDate}
                min={minDate}
                disabled={busy}
                onChange={(e) => setUntilDate(e.target.value)}
              />
            </label>
            <div className="modal-action-buttons">
              <button
                type="button"
                className="btn primary"
                disabled={busy || !untilDate || untilDate < minDate}
                onClick={() => onSelect('until_date', untilDate)}
              >
                Заблокировать до даты
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => setPickingDate(false)}
              >
                Назад
              </button>
            </div>
          </div>
        ) : (
          <div className="status-confirm">
            <div className="modal-action-buttons camera-block-options">
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => onSelect('until_field_observed')}
              >
                До полевого обследования
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => onSelect('until_quarter')}
              >
                До конца квартала
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => setPickingDate(true)}
              >
                До определённой даты
              </button>
              <button
                type="button"
                className="btn"
                disabled={busy || !orderEndDate}
                title={
                  orderEndDate
                    ? `Окончание ордера: ${orderLabel}`
                    : 'Нет сопоставления с ордером или нет даты окончания'
                }
                onClick={() => onSelect('until_order_end')}
              >
                {orderLabel ? `До окончания ордера (${orderLabel})` : 'До окончания ордера'}
              </button>
            </div>
            <div className="modal-action-buttons">
              <button type="button" className="btn" disabled={busy} onClick={onSkip}>
                Не блокировать камеру
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
