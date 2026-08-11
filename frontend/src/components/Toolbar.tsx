import { useEffect, useState } from 'react'
import { collectTasksByLayers, fetchDistricts } from '../api/client'
import type { CollectProgress } from '../types'

interface ToolbarProps {
  rayon: string
  loading: boolean
  onRayonChange: (v: string) => void
  onCollect: () => void
}

export function Toolbar({
  rayon,
  loading,
  onRayonChange,
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
      <button type="button" className="btn primary" disabled={!rayon || loading} onClick={onCollect}>
        {loading ? 'Загрузка…' : 'Обновить активные'}
      </button>
    </div>
  )
}

export function useTaskCollection() {
  const [rayon, setRayon] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<CollectProgress | null>(null)

  const runCollect = async () => {
    if (!rayon) return null
    setLoading(true)
    setError(null)
    setProgress(null)
    try {
      return await collectTasksByLayers(rayon, setProgress)
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
    loading,
    error,
    progress,
    runCollect,
  }
}
