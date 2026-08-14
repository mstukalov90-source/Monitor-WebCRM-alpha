import type { OfficeWorkMode } from '../types'

interface OfficeWorkModeModalProps {
  rayon?: string
  onSelect: (mode: OfficeWorkMode) => void
}

export function OfficeWorkModeModal({ rayon, onSelect }: OfficeWorkModeModalProps) {
  return (
    <div className="modal-backdrop modal-backdrop-blocking">
      <div className="modal office-work-mode-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Режим работы</h2>
        <p className="muted small">
          {rayon
            ? `Район: ${rayon}. Выберите ступень анализа заказов этого района или перейдите к карте`
            : 'Выберите ступень анализа площадных заказов выбранного района или перейдите к карте'}
        </p>
        <div className="office-work-mode-actions">
          <button type="button" className="btn primary" onClick={() => onSelect('pre_analise')}>
            Подготовка данных в поле
          </button>
          <button type="button" className="btn primary" onClick={() => onSelect('analise')}>
            Анализ полевых данных
          </button>
          <button type="button" className="btn" onClick={() => onSelect('map')}>
            К карте
          </button>
        </div>
      </div>
    </div>
  )
}
