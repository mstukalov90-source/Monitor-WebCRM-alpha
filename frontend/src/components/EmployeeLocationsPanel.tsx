import { useEffect, useState } from 'react'
import { fetchPersonnelUsers } from '../api/client'
import type { EmployeeLocationFeature, PersonnelUser } from '../types'
import {
  EMPLOYEE_LOCATION_TABLE_COLUMNS,
  displayAreaOrderTitle,
  displayUserNameByLogin,
  formatEmployeeLocationTableCell,
} from '../types'

interface EmployeeLocationsPanelProps {
  locations: EmployeeLocationFeature[]
  selectedLocationId: string | null
  loading?: boolean
  onSelect: (locationId: string) => void
}

function locationCell(
  attrs: Record<string, unknown>,
  field: string,
  format: 'datetime_short' | undefined,
  users: PersonnelUser[],
): string {
  if (field === 'user') {
    return displayUserNameByLogin(String(attrs.user ?? ''), users)
  }
  if (field === 'number') {
    return displayAreaOrderTitle(attrs)
  }
  return formatEmployeeLocationTableCell(attrs[field], format)
}

export function EmployeeLocationsPanel({
  locations,
  selectedLocationId,
  loading,
  onSelect,
}: EmployeeLocationsPanelProps) {
  const [users, setUsers] = useState<PersonnelUser[]>([])

  useEffect(() => {
    fetchPersonnelUsers()
      .then(setUsers)
      .catch(() => setUsers([]))
  }, [])

  return (
    <div className="task-panel">
      <div className="task-panel-header">
        <strong>Все сотрудники</strong>
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
                  Нет данных о местоположении
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
                      {locationCell(location.attributes, col.field, col.format, users)}
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
