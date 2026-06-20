import type { TaskSource } from '../types'
import { TASK_SOURCE_LABELS } from '../types'

interface TaskSourceTabsProps {
  value: TaskSource
  onChange: (source: TaskSource) => void
  loading?: boolean
}

const SOURCES: TaskSource[] = [
  'active',
  'field',
  'done_legal',
  'done_illegal',
  'area_free',
  'area_wip',
  'area_done',
]

export function TaskSourceTabs({ value, onChange, loading }: TaskSourceTabsProps) {
  return (
    <div className="task-source-tabs">
      {SOURCES.map((source) => (
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
