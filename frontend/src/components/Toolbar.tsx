import { useEffect, useState } from 'react'
import { collectTasksByLayers, fetchDistricts } from '../api/client'
import type { CollectProgress } from '../types'

interface ToolbarProps {
  rayon: string
  applyDateFilter: boolean
  loading: boolean
  onRayonChange: (v: string) => void
  onApplyDateFilterChange: (v: boolean) => void
  onCollect: () => void
}

export function Toolbar({
  rayon,
  applyDateFilter,
  loading,
  onRayonChange,
  onApplyDateFilterChange,
  onCollect,
}: ToolbarProps) {
  const [districts, setDistricts] = useState<string[]>([])

  useEffect(() => {
    fetchDistricts()
      .then((d) => setDistricts(d.districts))
      .catch(() => setDistricts([]))
  }, [])

  return (
    <div className="toolbar">
      <label>
        Район:
        <select value={rayon} onChange={(e) => onRayonChange(e.target.value)} disabled={loading}>
          <option value="">— выберите —</option>
          {districts.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </label>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={applyDateFilter}
          onChange={(e) => onApplyDateFilterChange(e.target.checked)}
          disabled={loading}
        />
        Фильтр по дате (ордера/уведомления)
      </label>
      <button type="button" className="btn primary" disabled={!rayon || loading} onClick={onCollect}>
        {loading ? 'Сбор…' : 'Получить задачу'}
      </button>
    </div>
  )
}

export function useTaskCollection() {
  const [rayon, setRayon] = useState('')
  const [applyDateFilter, setApplyDateFilter] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<CollectProgress | null>(null)

  const runCollect = async () => {
    if (!rayon) return null
    setLoading(true)
    setError(null)
    setProgress(null)
    try {
      return await collectTasksByLayers(rayon, applyDateFilter, setProgress)
    } catch (e) {
      setError(String(e))
      return null
    } finally {
      setLoading(false)
      setProgress(null)
    }
  }

  return {
    rayon,
    setRayon,
    applyDateFilter,
    setApplyDateFilter,
    loading,
    error,
    progress,
    runCollect,
  }
}
