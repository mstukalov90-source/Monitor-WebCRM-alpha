import { useCallback, useEffect, useState } from 'react'
import { fetchEmployeeLocations } from '../api/client'
import { useWorkspaceLayout } from '../hooks/useWorkspaceLayout'
import type { EmployeeLocationFeature } from '../types'
import { EmployeeLocationsMapView } from './EmployeeLocationsMapView'
import { EmployeeLocationsPanel } from './EmployeeLocationsPanel'
import { ResizeHandle } from './ResizeHandle'

interface EmployeeLocationsScreenProps {
  userLogin: string
  onBack: () => void
  onLogout: () => Promise<void>
}

export function EmployeeLocationsScreen({
  userLogin,
  onBack,
  onLogout,
}: EmployeeLocationsScreenProps) {
  const workspace = useWorkspaceLayout()
  const [locations, setLocations] = useState<EmployeeLocationFeature[]>([])
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadLocations = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchEmployeeLocations()
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
    void loadLocations()
  }, [loadLocations])

  return (
    <div className="app">
      <header className="app-header">
        <div className="workspace-header">
          <h1>Местоположение сотрудника</h1>
          <div className="workspace-meta">
            <span className="muted">{userLogin}</span>
            <span className="muted">На карте: {locations.length}</span>
            <button type="button" className="btn" onClick={onBack}>
              К карте
            </button>
            <button type="button" className="btn" onClick={() => void onLogout()}>
              Выйти
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={loading}
              onClick={() => void loadLocations()}
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
          <EmployeeLocationsPanel
            locations={locations}
            selectedLocationId={selectedLocationId}
            loading={loading}
            onSelect={setSelectedLocationId}
          />
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
              <EmployeeLocationsMapView
                locations={locations}
                selectedLocationId={selectedLocationId}
                onSelectLocation={setSelectedLocationId}
              />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
