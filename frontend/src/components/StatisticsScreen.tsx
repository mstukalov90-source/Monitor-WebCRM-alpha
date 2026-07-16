import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchPersonnelStatistics, fetchPersonnelUsers } from '../api/client'
import {
  defaultStatisticsDateRange,
  formatStatisticsAction,
  formatStatisticsObjectType,
} from '../lib/statisticsLabels'
import type {
  FieldStatisticsSummary,
  OfficeStatisticsBreakdown,
  PersonnelStatistics,
  PersonnelUser,
  UserRole,
} from '../types'

interface StatisticsScreenProps {
  userLogin: string
  userRole: UserRole
  canViewAll: boolean
  onBack: () => void
  onLogout: () => Promise<void>
}

type RoleFilter = '' | 'field' | 'office'
type ObjectTypeFilter = '' | 'task' | 'order'

function formatHa(value: number): string {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}

export function StatisticsScreen({
  userLogin,
  userRole,
  canViewAll,
  onBack,
  onLogout,
}: StatisticsScreenProps) {
  const initialRange = useMemo(() => defaultStatisticsDateRange(), [])
  const [dateFrom, setDateFrom] = useState(initialRange.dateFrom)
  const [dateTo, setDateTo] = useState(initialRange.dateTo)
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('')
  const [objectTypeFilter, setObjectTypeFilter] = useState<ObjectTypeFilter>('')
  const [userLoginFilter, setUserLoginFilter] = useState('')
  const [users, setUsers] = useState<PersonnelUser[]>([])
  const [data, setData] = useState<PersonnelStatistics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const employeeUsers = useMemo(
    () => users.filter((u) => u.role === 'field' || u.role === 'office'),
    [users],
  )

  const showFieldSection =
    canViewAll ? roleFilter !== 'office' : userRole === 'field'
  const showOfficeSection =
    canViewAll ? roleFilter !== 'field' : userRole === 'office'

  useEffect(() => {
    if (!canViewAll) return
    fetchPersonnelUsers()
      .then(setUsers)
      .catch(() => setUsers([]))
  }, [canViewAll])

  const loadStatistics = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchPersonnelStatistics({
        dateFrom,
        dateTo,
        userRole: canViewAll && roleFilter ? roleFilter : undefined,
        objectType: canViewAll && objectTypeFilter ? objectTypeFilter : undefined,
        userLogin: canViewAll && userLoginFilter ? userLoginFilter : undefined,
      })
      setData(result)
    } catch (e) {
      setError(String(e))
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [canViewAll, dateFrom, dateTo, objectTypeFilter, roleFilter, userLoginFilter])

  useEffect(() => {
    void loadStatistics()
  }, [loadStatistics])

  const fieldRows = data?.field_summary ?? []
  const officeRows = data?.office_breakdown ?? []
  const selfFieldRow = fieldRows.find((r) => r.user_login === userLogin) ?? fieldRows[0]
  const hasData =
    (showFieldSection && fieldRows.length > 0) ||
    (showOfficeSection && officeRows.length > 0)

  return (
    <div className="district-screen statistics-screen">
      <div className="statistics-layout">
        <div className="district-card statistics-card">
          <div className="workspace-meta district-user-meta">
            <span className="muted">
              {userLogin}
              {canViewAll ? ' (статистика персонала)' : ' (моя статистика)'}
            </span>
            <button type="button" className="btn" onClick={onBack}>
              К карте
            </button>
            <button type="button" className="btn" onClick={() => void onLogout()}>
              Выйти
            </button>
          </div>

          <h1>Статистика</h1>

          <div className="personnel-filters statistics-filters">
            <label className="district-field">
              <span>С</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </label>
            <label className="district-field">
              <span>По</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </label>
            {canViewAll && (
              <>
                <label className="district-field">
                  <span>Роль</span>
                  <select
                    value={roleFilter}
                    onChange={(e) => setRoleFilter(e.target.value as RoleFilter)}
                  >
                    <option value="">Все</option>
                    <option value="field">Полевые</option>
                    <option value="office">Офис</option>
                  </select>
                </label>
                <label className="district-field">
                  <span>Сотрудник</span>
                  <select
                    value={userLoginFilter}
                    onChange={(e) => setUserLoginFilter(e.target.value)}
                  >
                    <option value="">Все</option>
                    {employeeUsers.map((u) => (
                      <option key={u.uuid} value={u.login}>
                        {u.login} ({u.role})
                      </option>
                    ))}
                  </select>
                </label>
                <label className="district-field">
                  <span>Тип объекта</span>
                  <select
                    value={objectTypeFilter}
                    onChange={(e) => setObjectTypeFilter(e.target.value as ObjectTypeFilter)}
                  >
                    <option value="">Все</option>
                    <option value="task">Задачи</option>
                    <option value="order">Заказы</option>
                  </select>
                </label>
              </>
            )}
            <button
              type="button"
              className="btn primary"
              disabled={loading}
              onClick={() => void loadStatistics()}
            >
              {loading ? 'Загрузка…' : 'Показать'}
            </button>
          </div>

          {error && <p className="error-banner">{error}</p>}
          {!loading && !error && !hasData && (
            <p className="personnel-message">Нет данных за выбранный период</p>
          )}

          {showFieldSection && (
            <section className="statistics-section">
              <h2>{canViewAll ? 'Полевые сотрудники' : 'Мои показатели'}</h2>
              {!canViewAll && selfFieldRow ? (
                <FieldMetricsCards row={selfFieldRow} />
              ) : (
                <div className="personnel-table-wrap">
                  <table className="personnel-table statistics-table">
                    <thead>
                      <tr>
                        <th>Сотрудник</th>
                        <th>Обследование камеральной задачи</th>
                        <th>Отсутствие разрытия</th>
                        <th>Обнаружение разрытия</th>
                        <th>Закрытие заказа</th>
                        <th>Площадь закрытых, га</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fieldRows.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="muted">
                            Нет данных
                          </td>
                        </tr>
                      ) : (
                        fieldRows.map((row) => (
                          <tr key={row.user_login}>
                            <td>{row.user_login}</td>
                            <td>{row.camera_surveys}</td>
                            <td>{row.disruption_absent}</td>
                            <td>{row.disruption_found}</td>
                            <td>{row.orders_closed}</td>
                            <td>{formatHa(row.orders_closed_ha)}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {showOfficeSection && (
            <section className="statistics-section">
              <h2>{canViewAll ? 'Офис' : 'Мои действия'}</h2>
              <div className="personnel-table-wrap">
                <table className="personnel-table statistics-table">
                  <thead>
                    <tr>
                      {canViewAll && <th>Сотрудник</th>}
                      <th>Тип</th>
                      <th>Действие</th>
                      <th>Количество</th>
                      <th>Площадь, га</th>
                    </tr>
                  </thead>
                  <tbody>
                    {officeRows.length === 0 ? (
                      <tr>
                        <td colSpan={canViewAll ? 5 : 4} className="muted">
                          Нет данных
                        </td>
                      </tr>
                    ) : (
                      officeRows.map((row) => (
                        <OfficeBreakdownRow
                          key={`${row.user_login}-${row.object_type}-${row.action}`}
                          row={row}
                          showLogin={canViewAll}
                        />
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}

function FieldMetricsCards({ row }: { row: FieldStatisticsSummary }) {
  return (
    <div className="statistics-metrics">
      <div className="statistics-metric-card">
        <span className="statistics-metric-value">{row.camera_surveys}</span>
        <span className="statistics-metric-label">Обследование камеральной задачи</span>
      </div>
      <div className="statistics-metric-card">
        <span className="statistics-metric-value">{row.disruption_absent}</span>
        <span className="statistics-metric-label">Отсутствие разрытия по задаче</span>
      </div>
      <div className="statistics-metric-card">
        <span className="statistics-metric-value">{row.disruption_found}</span>
        <span className="statistics-metric-label">Обнаружение разрытия в поле</span>
      </div>
      <div className="statistics-metric-card">
        <span className="statistics-metric-value">{row.orders_closed}</span>
        <span className="statistics-metric-label">Закрытие заказа</span>
      </div>
      <div className="statistics-metric-card">
        <span className="statistics-metric-value">{formatHa(row.orders_closed_ha)}</span>
        <span className="statistics-metric-label">Площадь закрытых, га</span>
      </div>
    </div>
  )
}

function formatOfficeAreaHa(row: OfficeStatisticsBreakdown): string {
  if (row.object_type === 'task' || row.area_hectares === 0) return '—'
  return formatHa(row.area_hectares)
}

function OfficeBreakdownRow({
  row,
  showLogin,
}: {
  row: OfficeStatisticsBreakdown
  showLogin: boolean
}) {
  return (
    <tr>
      {showLogin && <td>{row.user_login}</td>}
      <td>{formatStatisticsObjectType(row.object_type)}</td>
      <td>{formatStatisticsAction(row.action)}</td>
      <td>{row.action_count}</td>
      <td>{formatOfficeAreaHa(row)}</td>
    </tr>
  )
}
