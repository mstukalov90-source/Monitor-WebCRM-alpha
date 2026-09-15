import type { LetterReviewStatus } from '../types'

interface LetterReviewActionsProps {
  status: LetterReviewStatus | null
  disabled?: boolean
  onApprove: () => void
  onReject: () => void
  onHide: () => void
}

export function LetterReviewActions({
  status,
  disabled,
  onApprove,
  onReject,
  onHide,
}: LetterReviewActionsProps) {
  return (
    <div className="letter-review-actions" onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className={`letter-review-btn letter-review-btn--ok${status === 'approved' ? ' is-active' : ''}`}
        disabled={disabled}
        title={status === 'approved' ? 'Снять одобрение' : 'Одобрить'}
        aria-label={status === 'approved' ? 'Снять одобрение' : 'Одобрить'}
        onClick={onApprove}
      >
        ✓
      </button>
      <button
        type="button"
        className={`letter-review-btn letter-review-btn--no${status === 'rejected' ? ' is-active' : ''}`}
        disabled={disabled}
        title={status === 'rejected' ? 'Снять отклонение' : 'Отклонить'}
        aria-label={status === 'rejected' ? 'Снять отклонение' : 'Отклонить'}
        onClick={onReject}
      >
        ✕
      </button>
      <button
        type="button"
        className="letter-review-btn letter-review-btn--hide"
        disabled={disabled}
        title="Убрать из списка"
        aria-label="Убрать из списка"
        onClick={onHide}
      >
        🗑
      </button>
    </div>
  )
}
