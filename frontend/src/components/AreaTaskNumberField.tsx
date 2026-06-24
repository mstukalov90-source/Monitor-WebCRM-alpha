import { useEffect, useState } from 'react'
import { updateAreaTaskNumber } from '../api/client'

interface AreaTaskNumberFieldProps {
  taskKey: string
  value: string | null | undefined
  onSaved?: () => void
  onError?: (message: string) => void
  className?: string
}

export function AreaTaskNumberField({
  taskKey,
  value,
  onSaved,
  onError,
  className,
}: AreaTaskNumberFieldProps) {
  const [draft, setDraft] = useState(value ?? '')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setDraft(value ?? '')
  }, [value, taskKey])

  const save = async () => {
    const normalized = draft.trim()
    const current = (value ?? '').trim()
    if (normalized === current) return

    setSaving(true)
    try {
      await updateAreaTaskNumber(taskKey, normalized || null)
      onSaved?.()
    } catch (e) {
      onError?.(String(e))
      setDraft(value ?? '')
    } finally {
      setSaving(false)
    }
  }

  return (
    <input
      type="text"
      className={className ?? 'personnel-task-number-input'}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => void save()}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.currentTarget.blur()
        }
      }}
      disabled={saving}
      placeholder="—"
      aria-label="Номер задачи"
    />
  )
}
