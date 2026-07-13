import { useCallback, useEffect, useState } from 'react'
import { fetchDistricts, fetchEmployeeLocations } from '../api/client'
import { useWorkspaceLayout } from '../hooks/useWorkspaceLayout'
import type { EmployeeLocationFeature } from '../types'
import { normalizeRayonName } from '../types'
import { EmployeeLocationsMapView } from './EmployeeLocationsMapView'
import { EmployeeLocationsPanel } from './EmployeeLocationsPanel'
import { ResizeHandle } from './ResizeHandle'

interface EmployeeLocationsScreenProps {
  userLogin: string
  initialRayon?: string
  onBack: () => void
  onLogout: () => Promise<void>
}

export function EmployeeLocationsScreen({
  userLogin,
  initialRayon = '',
  onBack,
  onLogout,
}: EmployeeLocationsScreenProps) {
  const workspace = useWorkspaceLayout()
  const [districts, setDistricts] = useState<string[]>([])
  const [rayon, setRayon] = useState(initialRayon)
  const [locations, setLocations] = useState<EmployeeLocationFeature[]>([])
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchDistricts()
      .then((d) => setDistricts(d.districts))
      .catch(() => setDistricts([]))
  }, [])

  const loadLocations = useCallback(async (district: string) => {
    if (!district) {
      setLocations([])
      setSelectedLocationId(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await fetchEmployeeLocations(district)
      setLocations(result.locations)
      setSelectedLocationId(null)
      if (result.errors.length) {
        setError(result.errors.join('; '))
      }
    } catch (e) {
      setError(String(e))
      setLocations([])
      setSelectedLocationId(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (rayon) {
      void loadLocations(rayon)
    }
  }, [rayon, loadLocations])

  const handleRayonChange = (value: string) => {
    setRayon(value)
    setSelectedLocationId(null)
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="workspace-header">
          <h1>Местоположение сотрудника</h1>
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
            {rayon && <span className="muted">На карте: {locations.length}</span>}
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
              onClick={() => void loadLocations(rayon)}
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
              <p>Выберите район для просмотра местоположений</p>
            </div>
          ) : (
            <EmployeeLocationsPanel
              districtName={rayon}
              locations={locations}
              selectedLocationId={selectedLocationId}
              loading={loading}
              onSelect={setSelectedLocationId}
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
                <EmployeeLocationsMapView
                  locations={locations}
                  districtName={rayon}
                  selectedLocationId={selectedLocationId}
                  onSelectLocation={setSelectedLocationId}
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
