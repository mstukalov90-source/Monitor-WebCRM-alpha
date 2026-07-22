import { useCallback, useEffect, useMemo, useState } from 'react'
import { AreaTaskNumberField } from './AreaTaskNumberField'
import {
  bulkAssignPersonnelTasks,
  bulkChangePersonnelTaskStatus,
  createPersonnelUser,
  fetchPersonnelActiveTasks,
  fetchPersonnelAreaTasks,
  fetchPersonnelClearTasks,
  fetchPersonnelDistricts,
  fetchPersonnelFieldTasks,
  fetchPersonnelUsers,
  updatePersonnelUserWorkZones,
} from '../api/client'
import type {
  AssignableTask,
  DistrictOption,
  PersonnelUser,
  UserRole,
  WorkflowTargetStatus,
} from '../types'
import { normalizeRayonName } from '../types'

type TaskTab = 'active' | 'field' | 'clear' | 'area'
type CreatableRole = 'field' | 'office' | 'manager'

const TAB_LABELS: Record<TaskTab, string> = {
  active: 'Активные',
  field: 'В поле',
  clear: 'Разрытие отсутствует',
  area: 'Площадные',
}

const STATUS_CONFIRM: Record<WorkflowTargetStatus, string> = {
  active: 'Вернуть выбранные задачи в активные?',
  field: 'Отправить выбранные задачи в поле?',
  clear: 'Отметить выбранные задачи: разрытие отсутствует?',
}

const STATUS_ACTIONS: Record<TaskTab, WorkflowTargetStatus[]> = {
  active: ['field', 'clear'],
  field: ['active', 'clear'],
  clear: ['active', 'field'],
  area: [],
}

interface PersonnelScreenProps {
  userLogin: string
  canCreateUsers: boolean
  onBack: () => void
  onLogout: () => Promise<void>
}

export function PersonnelScreen({
  userLogin,
  canCreateUsers,
  onBack,
  onLogout,
}: PersonnelScreenProps) {
  const [users, setUsers] = useState<PersonnelUser[]>([])
  const [districts, setDistricts] = useState<DistrictOption[]>([])
  const [selectedUuid, setSelectedUuid] = useState('')
  const [draftZones, setDraftZones] = useState<number[]>([])
  const [zonesSaving, setZonesSaving] = useState(false)
  const [zonesMessage, setZonesMessage] = useState<string | null>(null)

  const [taskTab, setTaskTab] = useState<TaskTab>('active')
  const [filterRayon, setFilterRayon] = useState('')
  const [filterStatus, setFilterStatus] = useState('wip')
  const [filterUnassigned, setFilterUnassigned] = useState(false)
  const [tasks, setTasks] = useState<AssignableTask[]>([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [tasksError, setTasksError] = useState<string | null>(null)
  const [tasksMessage, setTasksMessage] = useState<string | null>(null)
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [actionLoading, setActionLoading] = useState(false)
  const [executorLogin, setExecutorLogin] = useState('')
  const [pendingStatus, setPendingStatus] = useState<WorkflowTargetStatus | null>(null)

  const [showAddUser, setShowAddUser] = useState(false)
  const [newLogin, setNewLogin] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState<CreatableRole>('field')
  const [newZones, setNewZones] = useState<number[]>([])
  const [addSaving, setAddSaving] = useState(false)
  const [addMessage, setAddMessage] = useState<string | null>(null)

  const selectedUser = useMemo(
    () => users.find((u) => u.uuid === selectedUuid) ?? null,
    [users, selectedUuid],
  )

  const executorUsers = useMemo(
    () => users.filter((u) => u.role === 'field' || u.role === 'office'),
    [users],
  )

  const selectedTaskKeys = useMemo(
    () =>
      tasks
        .filter((t) => selectedKeys.has(t.key))
        .map((t) => t.task_key ?? t.key),
    [tasks, selectedKeys],
  )

  const statusActions = STATUS_ACTIONS[taskTab]
  const showExecutorActions = taskTab === 'field' || taskTab === 'area'
  const showUnassignedFilter = taskTab === 'field' || taskTab === 'area'

  useEffect(() => {
    void Promise.all([fetchPersonnelUsers(), fetchPersonnelDistricts()])
      .then(([u, d]) => {
        setUsers(u)
        setDistricts(d)
        if (u.length > 0) {
          setSelectedUuid(u[0].uuid)
          setDraftZones(u[0].work_zones)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (selectedUser) {
      setDraftZones(selectedUser.work_zones)
    }
  }, [selectedUser])

  const loadTasks = useCallback(async () => {
    setTasksLoading(true)
    setTasksError(null)
    setTasksMessage(null)
    setSelectedKeys(new Set())
    setPendingStatus(null)
    try {
      const rayon = filterRayon || undefined
      let list: AssignableTask[]
      if (taskTab === 'active') {
        list = await fetchPersonnelActiveTasks({ rayon })
      } else if (taskTab === 'field') {
        list = await fetchPersonnelFieldTasks({ rayon, unassignedOnly: filterUnassigned })
      } else if (taskTab === 'clear') {
        list = await fetchPersonnelClearTasks({ rayon })
      } else {
        list = await fetchPersonnelAreaTasks({
          rayon,
          status: filterStatus || undefined,
          unassignedOnly: filterUnassigned,
        })
      }
      setTasks(list)
    } catch (e) {
      setTasksError(String(e))
      setTasks([])
    } finally {
      setTasksLoading(false)
    }
  }, [taskTab, filterRayon, filterStatus, filterUnassigned])

  useEffect(() => {
    void loadTasks()
  }, [loadTasks])

  const toggleZone = (gid: number) => {
    setDraftZones((prev) =>
      prev.includes(gid) ? prev.filter((g) => g !== gid) : [...prev, gid],
    )
  }

  const toggleNewZone = (gid: number) => {
    setNewZones((prev) =>
      prev.includes(gid) ? prev.filter((g) => g !== gid) : [...prev, gid],
    )
  }

  const resetAddForm = () => {
    setNewLogin('')
    setNewPassword('')
    setNewRole('field')
    setNewZones([])
    setAddMessage(null)
  }

  const handleOpenAddUser = () => {
    resetAddForm()
    setShowAddUser(true)
  }

  const handleCreateUser = async () => {
    setAddSaving(true)
    setAddMessage(null)
    try {
      const created = await createPersonnelUser({
        login: newLogin.trim(),
        password: newPassword,
        role: newRole as UserRole,
        work_zones: newZones,
      })
      setUsers((prev) => [...prev, created].sort((a, b) => a.login.localeCompare(b.login)))
      setSelectedUuid(created.uuid)
      setDraftZones(created.work_zones)
      setShowAddUser(false)
      resetAddForm()
    } catch (e) {
      setAddMessage(String(e))
    } finally {
      setAddSaving(false)
    }
  }

  const handleSaveZones = async () => {
    if (!selectedUser) return
    setZonesSaving(true)
    setZonesMessage(null)
    try {
      const updated = await updatePersonnelUserWorkZones(selectedUser.uuid, draftZones)
      setUsers((prev) => prev.map((u) => (u.uuid === updated.uuid ? updated : u)))
      setZonesMessage('Районы сохранены')
    } catch (e) {
      setZonesMessage(String(e))
    } finally {
      setZonesSaving(false)
    }
  }

  const toggleTaskKey = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedKeys.size === tasks.length) {
      setSelectedKeys(new Set())
    } else {
      setSelectedKeys(new Set(tasks.map((t) => t.key)))
    }
  }

  const handleBulkAssign = async (executor: string | null) => {
    if (selectedKeys.size === 0 || (taskTab !== 'field' && taskTab !== 'area')) return
    setActionLoading(true)
    setTasksError(null)
    setTasksMessage(null)
    try {
      const result = await bulkAssignPersonnelTasks(taskTab, [...selectedKeys], executor)
      setTasksMessage(`Назначено: ${result.updated}, не найдено: ${result.not_found}`)
      await loadTasks()
    } catch (e) {
      setTasksError(String(e))
    } finally {
      setActionLoading(false)
    }
  }

  const handleBulkStatus = async (target: WorkflowTargetStatus) => {
    if (selectedTaskKeys.length === 0) return
    setPendingStatus(null)
    setActionLoading(true)
    setTasksError(null)
    setTasksMessage(null)
    try {
      const result = await bulkChangePersonnelTaskStatus(
        selectedTaskKeys,
        target,
        filterRayon || undefined,
      )
      const failedCount = result.failed.length
      const parts = [
        `Обновлено: ${result.updated}`,
        result.skipped > 0 ? `пропущено: ${result.skipped}` : null,
        result.not_found > 0 ? `не найдено: ${result.not_found}` : null,
        failedCount > 0 ? `ошибок: ${failedCount}` : null,
      ].filter(Boolean)
      setTasksMessage(parts.join(', '))
      if (failedCount > 0) {
        setTasksError(result.failed.map((f) => `${f.task_key.slice(0, 8)}…: ${f.error}`).join('; '))
      }
      await loadTasks()
    } catch (e) {
      setTasksError(String(e))
    } finally {
      setActionLoading(false)
    }
  }

  const requestStatusChange = (target: WorkflowTargetStatus) => {
    if (selectedTaskKeys.length === 0) return
    setPendingStatus(target)
  }

  const statusButtonLabel = (target: WorkflowTargetStatus): string => {
    if (target === 'active') return 'В активные'
    if (target === 'field') return 'В поле'
    return 'Разрытие отсутствует'
  }

  const statusButtonClass = (target: WorkflowTargetStatus): string => {
    if (target === 'active') return 'btn btn-status-active'
    if (target === 'field') return 'btn btn-status-field'
    return 'btn btn-status-clear'
  }

  return (
    <div className="district-screen personnel-screen">
      <div className="personnel-layout">
        <div className="district-card personnel-card">
          <div className="workspace-meta district-user-meta">
            <span className="muted">
              {userLogin} (управление персоналом)
            </span>
            <button type="button" className="btn" onClick={onBack}>
              К карте
            </button>
            <button type="button" className="btn" onClick={() => void onLogout()}>
              Выйти
            </button>
          </div>

          <h1>Персонал</h1>

          {canCreateUsers && (
            <button type="button" className="btn primary" onClick={handleOpenAddUser}>
              Добавить сотрудника
            </button>
          )}

          <label className="district-field">
            <span>Сотрудник</span>
            <select
              value={selectedUuid}
              onChange={(e) => setSelectedUuid(e.target.value)}
            >
              {users.map((u) => (
                <option key={u.uuid} value={u.uuid}>
                  {u.login} ({u.role})
                </option>
              ))}
            </select>
          </label>

          {selectedUser && (
            <p className="district-hint">
              Текущие районы:{' '}
              {selectedUser.district_names.length > 0
                ? selectedUser.district_names.map(normalizeRayonName).join(', ')
                : 'не назначены'}
            </p>
          )}

          <div className="personnel-zones">
            <span className="personnel-zones-label">Районы работ</span>
            <div className="personnel-zones-list">
              {districts.map((d) => (
                <label key={d.gid} className="checkbox-label personnel-zone-item">
                  <input
                    type="checkbox"
                    checked={draftZones.includes(d.gid)}
                    onChange={() => toggleZone(d.gid)}
                  />
                  {normalizeRayonName(d.rayon)}
                </label>
              ))}
            </div>
          </div>

          <button
            type="button"
            className="btn primary"
            disabled={!selectedUser || zonesSaving}
            onClick={() => void handleSaveZones()}
          >
            {zonesSaving ? 'Сохранение…' : 'Сохранить районы'}
          </button>
          {zonesMessage && <div className="personnel-message">{zonesMessage}</div>}
        </div>

        <div className="district-card personnel-tasks-card">
          <h2>Управление задачами</h2>

          <div className="personnel-task-tabs">
            {(['active', 'field', 'clear', 'area'] as TaskTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                className={`btn${taskTab === tab ? ' primary' : ''}`}
                onClick={() => setTaskTab(tab)}
              >
                {TAB_LABELS[tab]}
              </button>
            ))}
          </div>

          <div className="personnel-filters">
            <label className="district-field">
              <span>Район</span>
              <select value={filterRayon} onChange={(e) => setFilterRayon(e.target.value)}>
                <option value="">— все —</option>
                {districts.map((d) => (
                  <option key={d.gid} value={d.rayon}>
                    {normalizeRayonName(d.rayon)}
                  </option>
                ))}
              </select>
            </label>

            {taskTab === 'area' && (
              <label className="district-field">
                <span>Статус</span>
                <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
                  <option value="free">Свободные</option>
                  <option value="wip">На обследовании</option>
                  <option value="done">Завершённые</option>
                </select>
              </label>
            )}

            {showUnassignedFilter && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={filterUnassigned}
                  onChange={(e) => setFilterUnassigned(e.target.checked)}
                />
                Только неназначенные
              </label>
            )}
          </div>

          {pendingStatus ? (
            <div className="status-confirm personnel-status-confirm">
              <p>{STATUS_CONFIRM[pendingStatus]}</p>
              <div className="personnel-actions">
                <button
                  type="button"
                  className="btn primary"
                  disabled={actionLoading}
                  onClick={() => void handleBulkStatus(pendingStatus)}
                >
                  Подтвердить ({selectedKeys.size})
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={actionLoading}
                  onClick={() => setPendingStatus(null)}
                >
                  Отмена
                </button>
              </div>
            </div>
          ) : (
            <div className="personnel-actions">
              {statusActions.map((target) => (
                <button
                  key={target}
                  type="button"
                  className={statusButtonClass(target)}
                  disabled={selectedKeys.size === 0 || actionLoading}
                  onClick={() => requestStatusChange(target)}
                >
                  {statusButtonLabel(target)} ({selectedKeys.size})
                </button>
              ))}

              {showExecutorActions && (
                <>
                  <label className="district-field personnel-executor-field">
                    <span>Исполнитель</span>
                    <select
                      value={executorLogin}
                      onChange={(e) => setExecutorLogin(e.target.value)}
                    >
                      <option value="">— выберите —</option>
                      {executorUsers.map((u) => (
                        <option key={u.uuid} value={u.login}>
                          {u.login} ({u.role})
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    className="btn primary"
                    disabled={!executorLogin || selectedKeys.size === 0 || actionLoading}
                    onClick={() => void handleBulkAssign(executorLogin)}
                  >
                    Назначить исполнителя
                  </button>
                  <button
                    type="button"
                    className="btn"
                    disabled={selectedKeys.size === 0 || actionLoading}
                    onClick={() => void handleBulkAssign(null)}
                  >
                    Снять назначение
                  </button>
                </>
              )}

              <button
                type="button"
                className="btn"
                disabled={tasksLoading}
                onClick={() => void loadTasks()}
              >
                Обновить
              </button>
            </div>
          )}

          {tasksMessage && <div className="personnel-message">{tasksMessage}</div>}
          {tasksError && <div className="error-banner">{tasksError}</div>}

          <div className="personnel-table-wrap">
            {tasksLoading ? (
              <p className="district-hint">Загрузка задач…</p>
            ) : tasks.length === 0 ? (
              <p className="district-hint">Задачи не найдены</p>
            ) : (
              <table className="personnel-table">
                <thead>
                  <tr>
                    <th>
                      <input
                        type="checkbox"
                        checked={tasks.length > 0 && selectedKeys.size === tasks.length}
                        onChange={toggleSelectAll}
                        aria-label="Выбрать все"
                      />
                    </th>
                    <th>Ключ</th>
                    <th>Тип</th>
                    <th>Район</th>
                    {taskTab === 'field' && <th>Исполнитель</th>}
                    {taskTab === 'area' && <th>Статус</th>}
                    {taskTab === 'area' && <th>Номер задачи</th>}
                    {taskTab === 'area' && <th>Исполнитель</th>}
                    {(taskTab === 'field' || taskTab === 'clear') && <th>Отправлено</th>}
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t) => (
                    <tr key={t.key}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedKeys.has(t.key)}
                          onChange={() => toggleTaskKey(t.key)}
                        />
                      </td>
                      <td className="personnel-key" title={t.task_key ?? t.key}>
                        {(t.task_key ?? t.key).slice(0, 8)}…
                      </td>
                      <td>{t.type || '—'}</td>
                      <td>{t.rayon ? normalizeRayonName(t.rayon) : '—'}</td>
                      {taskTab === 'field' && <td>{t.executor || '—'}</td>}
                      {taskTab === 'area' && <td>{t.status || '—'}</td>}
                      {taskTab === 'area' && (
                        <td>
                          {canCreateUsers ? (
                            <AreaTaskNumberField
                              taskKey={t.key}
                              value={t.task_number}
                              onSaved={() => void loadTasks()}
                              onError={setTasksError}
                            />
                          ) : (
                            t.task_number || '—'
                          )}
                        </td>
                      )}
                      {taskTab === 'area' && <td>{t.executor || '—'}</td>}
                      {(taskTab === 'field' || taskTab === 'clear') && (
                        <td>{t.sent_at ? t.sent_at.slice(0, 10) : '—'}</td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {showAddUser && (
        <div className="modal-backdrop" onClick={() => setShowAddUser(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Добавить сотрудника</h2>

            <label className="district-field">
              <span>Логин</span>
              <input
                type="text"
                value={newLogin}
                onChange={(e) => setNewLogin(e.target.value)}
                disabled={addSaving}
                autoComplete="off"
              />
            </label>

            <label className="district-field">
              <span>Пароль</span>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                disabled={addSaving}
                autoComplete="new-password"
              />
            </label>

            <label className="district-field">
              <span>Роль</span>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as CreatableRole)}
                disabled={addSaving}
              >
                <option value="field">field</option>
                <option value="office">office</option>
                <option value="manager">manager</option>
              </select>
            </label>

            <div className="personnel-zones">
              <span className="personnel-zones-label">Районы работ</span>
              <div className="personnel-zones-list">
                {districts.map((d) => (
                  <label key={d.gid} className="checkbox-label personnel-zone-item">
                    <input
                      type="checkbox"
                      checked={newZones.includes(d.gid)}
                      onChange={() => toggleNewZone(d.gid)}
                      disabled={addSaving}
                    />
                    {normalizeRayonName(d.rayon)}
                  </label>
                ))}
              </div>
            </div>

            {addMessage && <div className="error-banner">{addMessage}</div>}

            <div className="modal-action-buttons">
              <button
                type="button"
                className="btn primary"
                disabled={!newLogin.trim() || !newPassword || addSaving}
                onClick={() => void handleCreateUser()}
              >
                {addSaving ? 'Создание…' : 'Создать'}
              </button>
              <button
                type="button"
                className="btn"
                disabled={addSaving}
                onClick={() => setShowAddUser(false)}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
