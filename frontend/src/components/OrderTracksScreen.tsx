import { useCallback, useEffect, useState } from 'react'
import { fetchDistricts, fetchOrderTracks } from '../api/client'
import { useWorkspaceLayout } from '../hooks/useWorkspaceLayout'
import type { TrackFeature } from '../types'
import { normalizeRayonName } from '../types'
import { ResizeHandle } from './ResizeHandle'
import { TracksMapView } from './TracksMapView'
import { TracksPanel } from './TracksPanel'

interface OrderTracksScreenProps {
  userLogin: string
  initialRayon?: string
  onBack: () => void
  onLogout: () => Promise<void>
}

export function OrderTracksScreen({
  userLogin,
  initialRayon = '',
  onBack,
  onLogout,
}: OrderTracksScreenProps) {
  const workspace = useWorkspaceLayout()
  const [districts, setDistricts] = useState<string[]>([])
  const [rayon, setRayon] = useState(initialRayon)
  const [tracks, setTracks] = useState<TrackFeature[]>([])
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchDistricts()
      .then((d) => setDistricts(d.districts))
      .catch(() => setDistricts([]))
  }, [])

  const loadTracks = useCallback(async (district: string) => {
    if (!district) {
      setTracks([])
      setSelectedTrackId(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await fetchOrderTracks(district)
      setTracks(result.tracks)
      setSelectedTrackId(null)
      if (result.errors.length) {
        setError(result.errors.join('; '))
      }
    } catch (e) {
      setError(String(e))
      setTracks([])
      setSelectedTrackId(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (rayon) {
      void loadTracks(rayon)
    }
  }, [rayon, loadTracks])

  const handleRayonChange = (value: string) => {
    setRayon(value)
    setSelectedTrackId(null)
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="workspace-header">
          <h1>Треки заказов</h1>
          <div className="workspace-meta">
            <span className="muted">{userLogin}</span>
            <label className="district-field district-field-inline">
              <span>Район</span>
              <select
                value={rayon}
                onChange={(e) => handleRayonChange(e.target.value)}
                disabled={loading}
              >
                <option value="">— выберите район —</option>
                {districts.map((d) => (
                  <option key={d} value={d}>
                    {normalizeRayonName(d)}
                  </option>
                ))}
              </select>
            </label>
            {rayon && <span className="muted">На карте: {tracks.length}</span>}
            <button type="button" className="btn" onClick={onBack}>
              К карте
            </button>
            <button type="button" className="btn" onClick={() => void onLogout()}>
              Выйти
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={!rayon || loading}
              onClick={() => void loadTracks(rayon)}
            >
              {loading ? 'Обновление…' : 'Обновить'}
            </button>
          </div>
        </div>
        {error && <div className="error-banner">{error}</div>}
      </header>

      <div
        ref={workspace.appBodyRef}
        className={`app-body${workspace.resizing ? ' app-body--resizing' : ''}`}
        style={workspace.layoutStyle}
      >
        <aside className="sidebar">
          {!rayon ? (
            <div className="task-panel empty">
              <p>Выберите район для просмотра треков</p>
            </div>
          ) : (
            <TracksPanel
              districtName={rayon}
              tracks={tracks}
              selectedTrackId={selectedTrackId}
              loading={loading}
              onSelect={setSelectedTrackId}
            />
          )}
        </aside>
        <ResizeHandle
          orientation="vertical"
          onResize={workspace.handleSidebarResize}
          onResizeStart={() => workspace.setResizing(true)}
          onResizeEnd={() => workspace.setResizing(false)}
        />
        <main ref={workspace.mapAreaRef} className="map-area">
          <div className="map-area-stack">
            <div className={`map-viewport${workspace.resizing ? ' map-viewport--resizing' : ''}`}>
              {rayon ? (
                <TracksMapView
                  tracks={tracks}
                  districtName={rayon}
                  selectedTrackId={selectedTrackId}
                  onSelectTrack={setSelectedTrackId}
                />
              ) : (
                <div className="task-panel empty map-placeholder">
                  <p className="muted">Карта появится после выбора района</p>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
