import type { TaskSource } from '../types'
import { TASK_SOURCE_LABELS } from '../types'

interface TaskSourceTabsProps {
  value: TaskSource
  allowedSources: TaskSource[]
  onChange: (source: TaskSource) => void
  loading?: boolean
}

export function TaskSourceTabs({ value, allowedSources, onChange, loading }: TaskSourceTabsProps) {
  return (
    <div className="task-source-tabs">
      {allowedSources.map((source) => (
        <button
          key={source}
          type="button"
          className={`task-source-tab ${value === source ? 'active' : ''}`}
          disabled={loading}
          onClick={() => onChange(source)}
        >
          {TASK_SOURCE_LABELS[source]}
        </button>
      ))}
    </div>
  )
}
