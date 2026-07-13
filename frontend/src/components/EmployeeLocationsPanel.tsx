import type { EmployeeLocationFeature } from '../types'
import {
  EMPLOYEE_LOCATION_TABLE_COLUMNS,
  formatEmployeeLocationTableCell,
} from '../types'

interface EmployeeLocationsPanelProps {
  districtName: string
  locations: EmployeeLocationFeature[]
  selectedLocationId: string | null
  loading?: boolean
  onSelect: (locationId: string) => void
}

export function EmployeeLocationsPanel({
  districtName,
  locations,
  selectedLocationId,
  loading,
  onSelect,
}: EmployeeLocationsPanelProps) {
  return (
    <div className="task-panel">
      <div className="task-panel-header">
        <strong>{districtName}</strong>
        <span className="muted">Сотрудников: {locations.length}</span>
        {loading && <div className="muted small">Загрузка…</div>}
      </div>

      <div className="task-table-wrap">
        <table className="task-table">
          <thead>
            <tr>
              {EMPLOYEE_LOCATION_TABLE_COLUMNS.map((col) => (
                <th key={col.field}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {locations.length === 0 && !loading ? (
              <tr>
                <td colSpan={EMPLOYEE_LOCATION_TABLE_COLUMNS.length} className="muted">
                  Нет сотрудников в выбранном районе
                </td>
              </tr>
            ) : (
              locations.map((location) => (
                <tr
                  key={location.id}
                  className={selectedLocationId === location.id ? 'selected' : ''}
                  onClick={() => onSelect(location.id)}
                >
                  {EMPLOYEE_LOCATION_TABLE_COLUMNS.map((col) => (
                    <td key={col.field}>
                      {formatEmployeeLocationTableCell(location.attributes[col.field])}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
