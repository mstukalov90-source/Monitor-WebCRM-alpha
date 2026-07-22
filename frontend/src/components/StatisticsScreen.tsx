import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchPersonnelGeoStatistics,
  fetchPersonnelStatistics,
  fetchPersonnelUsers,
} from '../api/client'
import {
  defaultStatisticsDateRange,
  formatDurationMinutes,
  formatStatisticsAction,
  formatStatisticsObjectType,
} from '../lib/statisticsLabels'
import type {
  FieldStatisticsSummary,
  GeoStatistics,
  GeoStatisticsRow,
  OfficeStatisticsBreakdown,
  PersonnelStatistics,
  PersonnelUser,
  StatisticsActionDetail,
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
type ViewMode = 'people' | 'geo'

function formatHa(value: number): string {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}

function geoPlaceLabel(value: string | null | undefined, emptyLabel: string): string {
  const text = (value || '').trim()
  return text || emptyLabel
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
  const [viewMode, setViewMode] = useState<ViewMode>('people')
  const [selectedOkrug, setSelectedOkrug] = useState<string | null>(null)
  const [users, setUsers] = useState<PersonnelUser[]>([])
  const [data, setData] = useState<PersonnelStatistics | null>(null)
  const [geoData, setGeoData] = useState<GeoStatistics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const employeeUsers = useMemo(
    () => users.filter((u) => u.role === 'field' || u.role === 'office'),
    [users],
  )

  const effectiveViewMode: ViewMode = canViewAll ? viewMode : 'people'

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

  useEffect(() => {
    if (!canViewAll && viewMode === 'geo') {
      setViewMode('people')
    }
  }, [canViewAll, viewMode])

  const filterParams = useMemo(
    () => ({
      dateFrom,
      dateTo,
      userRole: canViewAll && roleFilter ? roleFilter : undefined,
      objectType: canViewAll && objectTypeFilter ? objectTypeFilter : undefined,
      userLogin: canViewAll && userLoginFilter ? userLoginFilter : undefined,
    }),
    [canViewAll, dateFrom, dateTo, objectTypeFilter, roleFilter, userLoginFilter],
  )

  const loadStatistics = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (effectiveViewMode === 'geo') {
        const result = await fetchPersonnelGeoStatistics(filterParams)
        setGeoData(result)
        setData(null)
      } else {
        const result = await fetchPersonnelStatistics(filterParams)
        setData(result)
        setGeoData(null)
      }
    } catch (e) {
      setError(String(e))
      setData(null)
      setGeoData(null)
    } finally {
      setLoading(false)
    }
  }, [effectiveViewMode, filterParams])

  useEffect(() => {
    void loadStatistics()
  }, [loadStatistics])

  const fieldRows = data?.field_summary ?? []
  const officeRows = data?.office_breakdown ?? []
  const detailRows = data?.action_details ?? []
  const selfFieldRow = fieldRows.find((r) => r.user_login === userLogin) ?? fieldRows[0]
  const showDetails = Boolean(userLoginFilter) || !canViewAll

  const okrugRows = geoData?.okrugs ?? []
  const rayonRows = useMemo(() => {
    const all = geoData?.rayons ?? []
    if (selectedOkrug === null) return []
    if (selectedOkrug === '') {
      return all.filter((row) => !row.okrug)
    }
    return all.filter((row) => (row.okrug || '') === selectedOkrug)
  }, [geoData?.rayons, selectedOkrug])

  const maxOrdersClosed = useMemo(
    () => Math.max(0, ...okrugRows.map((row) => row.orders_closed)),
    [okrugRows],
  )
  const maxOrdersHa = useMemo(
    () => Math.max(0, ...okrugRows.map((row) => row.orders_closed_ha)),
    [okrugRows],
  )
  const maxOrdersOpen = useMemo(
    () => Math.max(0, ...okrugRows.map((row) => row.orders_open)),
    [okrugRows],
  )

  const hasPeopleData =
    (showFieldSection && fieldRows.length > 0) ||
    (showOfficeSection && officeRows.length > 0) ||
    (showDetails && detailRows.length > 0)
  const hasGeoData = okrugRows.length > 0
  const hasData = effectiveViewMode === 'geo' ? hasGeoData : hasPeopleData

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

          {canViewAll && (
            <div className="statistics-view-toggle" role="tablist" aria-label="Режим статистики">
              <button
                type="button"
                role="tab"
                className={`btn${effectiveViewMode === 'people' ? ' primary' : ''}`}
                aria-selected={effectiveViewMode === 'people'}
                onClick={() => {
                  setViewMode('people')
                  setSelectedOkrug(null)
                }}
              >
                Сотрудники
              </button>
              <button
                type="button"
                role="tab"
                className={`btn${effectiveViewMode === 'geo' ? ' primary' : ''}`}
                aria-selected={effectiveViewMode === 'geo'}
                onClick={() => setViewMode('geo')}
              >
                Территория
              </button>
            </div>
          )}

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

          {effectiveViewMode === 'people' && (
            <>
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

              {showDetails && (
                <section className="statistics-section">
                  <h2>Закрытия и анализ</h2>
                  <div className="personnel-table-wrap">
                    <table className="personnel-table statistics-table statistics-details-table">
                      <thead>
                        <tr>
                          <th>Дата</th>
                          <th>Тип</th>
                          <th>Действие</th>
                          <th>Объект</th>
                          <th>Площадь, га</th>
                          <th>Длительность</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detailRows.length === 0 ? (
                          <tr>
                            <td colSpan={6} className="muted">
                              Нет закрытий и анализов за период
                            </td>
                          </tr>
                        ) : (
                          detailRows.map((row) => (
                            <ActionDetailRow
                              key={`${row.action}-${row.object_key}-${row.created_at}`}
                              row={row}
                            />
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )}

          {effectiveViewMode === 'geo' && hasGeoData && (
            <>
              <section className="statistics-section">
                <h2>Округа</h2>
                <div className="statistics-bars">
                  <div className="statistics-bars-group">
                    <h3 className="statistics-bars-title">Закрытие заказов</h3>
                    {okrugRows.map((row) => (
                      <StatisticsBar
                        key={`orders-${row.okrug ?? ''}`}
                        label={geoPlaceLabel(row.okrug, 'Без округа')}
                        value={row.orders_closed}
                        max={maxOrdersClosed}
                        display={String(row.orders_closed)}
                        active={selectedOkrug !== null && (row.okrug ?? '') === selectedOkrug}
                        onClick={() =>
                          setSelectedOkrug((prev) =>
                            prev === (row.okrug ?? '') ? null : row.okrug ?? '',
                          )
                        }
                      />
                    ))}
                  </div>
                  <div className="statistics-bars-group">
                    <h3 className="statistics-bars-title">Площадь закрытых, га</h3>
                    {okrugRows.map((row) => (
                      <StatisticsBar
                        key={`ha-${row.okrug ?? ''}`}
                        label={geoPlaceLabel(row.okrug, 'Без округа')}
                        value={row.orders_closed_ha}
                        max={maxOrdersHa}
                        display={formatHa(row.orders_closed_ha)}
                        active={selectedOkrug !== null && (row.okrug ?? '') === selectedOkrug}
                        onClick={() =>
                          setSelectedOkrug((prev) =>
                            prev === (row.okrug ?? '') ? null : row.okrug ?? '',
                          )
                        }
                      />
                    ))}
                  </div>
                  <div className="statistics-bars-group">
                    <h3 className="statistics-bars-title">Незакрытые заказы</h3>
                    {okrugRows.map((row) => (
                      <StatisticsBar
                        key={`open-${row.okrug ?? ''}`}
                        label={geoPlaceLabel(row.okrug, 'Без округа')}
                        value={row.orders_open}
                        max={maxOrdersOpen}
                        display={String(row.orders_open)}
                        active={selectedOkrug !== null && (row.okrug ?? '') === selectedOkrug}
                        onClick={() =>
                          setSelectedOkrug((prev) =>
                            prev === (row.okrug ?? '') ? null : row.okrug ?? '',
                          )
                        }
                      />
                    ))}
                  </div>
                </div>

                <div className="personnel-table-wrap">
                  <table className="personnel-table statistics-table statistics-geo-table statistics-geo-table-selectable">
                    <thead>
                      <tr>
                        <th>Округ</th>
                        <th>Закрыто</th>
                        <th>Площадь закрытых, га</th>
                        <th>Незакрыто</th>
                        <th>Площадь незакрытых, га</th>
                        <th>Прогресс</th>
                        <th>Анализ завершён</th>
                      </tr>
                    </thead>
                    <tbody>
                      {okrugRows.map((row) => {
                        const key = row.okrug ?? ''
                        const selected = selectedOkrug === key
                        return (
                          <tr
                            key={`okrug-${key}`}
                            className={selected ? 'statistics-row-selected' : undefined}
                            onClick={() => setSelectedOkrug(selected ? null : key)}
                          >
                            <td>{geoPlaceLabel(row.okrug, 'Без округа')}</td>
                            <GeoMetricCells row={row} />
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="statistics-section">
                <div className="statistics-section-header">
                  <h2>
                    {selectedOkrug === null
                      ? 'Районы'
                      : `Районы: ${geoPlaceLabel(selectedOkrug, 'Без округа')}`}
                  </h2>
                  {selectedOkrug !== null && (
                    <button
                      type="button"
                      className="btn"
                      onClick={() => setSelectedOkrug(null)}
                    >
                      Все округа
                    </button>
                  )}
                </div>
                {selectedOkrug === null ? (
                  <p className="muted">Выберите округ в таблице или на диаграмме, чтобы увидеть районы.</p>
                ) : (
                  <div className="personnel-table-wrap">
                    <table className="personnel-table statistics-table statistics-geo-table">
                      <thead>
                        <tr>
                          <th>Район</th>
                          <th>Закрыто</th>
                          <th>Площадь закрытых, га</th>
                          <th>Незакрыто</th>
                          <th>Площадь незакрытых, га</th>
                          <th>Прогресс</th>
                          <th>Анализ завершён</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rayonRows.length === 0 ? (
                          <tr>
                            <td colSpan={7} className="muted">
                              Нет данных по районам
                            </td>
                          </tr>
                        ) : (
                          rayonRows.map((row) => (
                            <tr key={`rayon-${row.okrug ?? ''}-${row.rayon ?? ''}`}>
                              <td>{geoPlaceLabel(row.rayon, 'Без района')}</td>
                              <GeoMetricCells row={row} />
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function formatProgressPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`
}

function GeoMetricCells({ row }: { row: GeoStatisticsRow }) {
  return (
    <>
      <td>{row.orders_closed}</td>
      <td>{formatHa(row.orders_closed_ha)}</td>
      <td>{row.orders_open}</td>
      <td>{formatHa(row.orders_open_ha)}</td>
      <td>{formatProgressPct(row.progress_pct)}</td>
      <td>{row.analise_completed}</td>
    </>
  )
}

function StatisticsBar({
  label,
  value,
  max,
  display,
  active,
  onClick,
}: {
  label: string
  value: number
  max: number
  display: string
  active: boolean
  onClick: () => void
}) {
  const widthPct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0
  return (
    <button
      type="button"
      className={`statistics-bar${active ? ' statistics-bar-active' : ''}`}
      onClick={onClick}
      title={label}
    >
      <span className="statistics-bar-label">{label}</span>
      <span className="statistics-bar-track">
        <span className="statistics-bar-fill" style={{ width: `${widthPct}%` }} />
      </span>
      <span className="statistics-bar-value">{display}</span>
    </button>
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

function formatDetailObjectLabel(row: StatisticsActionDetail): string {
  const parts: string[] = []
  if (row.task_number) parts.push(row.task_number)
  if (row.rayon) parts.push(row.rayon)
  if (parts.length) return parts.join(' · ')
  return row.object_key.slice(0, 8)
}

function formatDetailDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('ru-RU')
}

function ActionDetailRow({ row }: { row: StatisticsActionDetail }) {
  const areaLabel =
    row.object_type === 'order' && row.area_hectares > 0 ? formatHa(row.area_hectares) : '—'
  return (
    <tr>
      <td>{formatDetailDate(row.created_at)}</td>
      <td>{formatStatisticsObjectType(row.object_type)}</td>
      <td>{formatStatisticsAction(row.action)}</td>
      <td title={row.object_key}>{formatDetailObjectLabel(row)}</td>
      <td>{areaLabel}</td>
      <td>{formatDurationMinutes(row.duration_minutes)}</td>
    </tr>
  )
}
