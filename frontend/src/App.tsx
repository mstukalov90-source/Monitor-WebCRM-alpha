import { useCallback, useEffect, useMemo, useState } from 'react'
import { completeAreaAnalise, createOfficeTask, fetchActiveTasks, fetchLayersConfig, fetchSnapshotTasks, fetchTasksArea, pauseAreaAnalise, startAreaAnalise } from './api/client'
import { AreaOrderPickerModal } from './components/AreaOrderPickerModal'
import { AreaTaskViewModal } from './components/AreaTaskViewModal'
import { DistrictStartScreen } from './components/DistrictStartScreen'
import { LoginScreen } from './components/LoginScreen'
import { MapView } from './components/MapView'
import { MapLegend } from './components/MapLegend'
import { EmployeeLocationsScreen } from './components/EmployeeLocationsScreen'
import { OrderTracksScreen } from './components/OrderTracksScreen'
import { PersonnelScreen } from './components/PersonnelScreen'
import { StatisticsScreen } from './components/StatisticsScreen'
import { flattenLayers } from './components/LayerControl'
import { TaskEditModal } from './components/TaskEditModal'
import { ResizeHandle } from './components/ResizeHandle'
import { TaskPanel } from './components/TaskPanel'
import { TaskSourceTabs } from './components/TaskSourceTabs'
import { useWorkspaceLayout } from './hooks/useWorkspaceLayout'
import { useAuth } from './context/AuthContext'
import { useTaskCollection } from './components/Toolbar'
import { allTaskFeaturesOnMap, layerConfigMap } from './lib/taskFeatures'
import { countTaskResultFeatures, filterTaskResultByArea } from './lib/filterTasksByArea'
import { geometryInsideArea } from './lib/geometry'
import { buildTaskExecutionContext } from './lib/openTaskExecution'
import {
  patchAreaViewFeature,
  patchTaskAttributes,
  removeTaskByKey,
} from './lib/taskResultMutations'
import type { LayerGroupConfig, LinkLayerInfo, SelectedTaskContext, TaskFeature, TaskHighlight, TaskResult, TaskSource, TaskFilterSelection, AppView } from './types'
import { isAreaSource, TASK_FILTER_NONE } from './types'
import './App.css'

function App() {
  const { user, loading: authLoading, logout } = useAuth()
  const [layerGroups, setLayerGroups] = useState<LayerGroupConfig[]>([])
  const [taskResult, setTaskResult] = useState<TaskResult | null>(null)
  const [taskSource, setTaskSource] = useState<TaskSource>('active')
  const [sourceLoading, setSourceLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [panelHighlight, setPanelHighlight] = useState<TaskHighlight | null>(null)
  const [modalHighlight, setModalHighlight] = useState<TaskHighlight | null>(null)
  const [editContext, setEditContext] = useState<SelectedTaskContext | null>(null)
  const [pickMode, setPickMode] = useState(false)
  const [pickLayers, setPickLayers] = useState<LinkLayerInfo[]>([])
  const [pickedValue, setPickedValue] = useState<{ column: string; value: string } | null>(null)
  const [placePointMode, setPlacePointMode] = useState(false)
  const [pendingOfficeLinkPrefill, setPendingOfficeLinkPrefill] = useState<Record<string, string> | null>(null)
  const [placePointBusy, setPlacePointBusy] = useState(false)
  const [appView, setAppView] = useState<AppView>('workspace')
  const [areaViewFeature, setAreaViewFeature] = useState<TaskFeature | null>(null)
  const [areaPolygonsOnMap, setAreaPolygonsOnMap] = useState(false)
  const [lastTaskSource, setLastTaskSource] = useState<TaskSource>('active')
  const [taskFilterSelection, setTaskFilterSelection] = useState<TaskFilterSelection>(TASK_FILTER_NONE)
  const [officeAreaOrder, setOfficeAreaOrder] = useState<TaskFeature | null>(null)
  const [officeOrderPickerOpen, setOfficeOrderPickerOpen] = useState(false)
  const [areaOrders, setAreaOrders] = useState<TaskFeature[]>([])
  const [areaOrdersLoading, setAreaOrdersLoading] = useState(false)

  const isOfficeUser = user?.role === 'office'

  const activeHighlight = editContext ? modalHighlight : panelHighlight
  const collection = useTaskCollection()
  const workspace = useWorkspaceLayout()

  useEffect(() => {
    if (!user) return
    fetchLayersConfig()
      .then((cfg) => setLayerGroups(cfg.groups))
      .catch(() => {})
  }, [user])

  useEffect(() => {
    if (user?.default_task_source) {
      setTaskSource(user.default_task_source)
      if (!isAreaSource(user.default_task_source)) {
        setLastTaskSource(user.default_task_source)
      }
    }
  }, [user?.default_task_source, user?.login])

  useEffect(() => {
    if (!isAreaSource(taskSource)) {
      setLastTaskSource(taskSource)
    }
  }, [taskSource])

  const allLayers = useMemo(() => flattenLayers(layerGroups), [layerGroups])
  const layerConfigByKey = useMemo(() => layerConfigMap(allLayers), [allLayers])

  const loadAreaOrders = useCallback(async (rayon: string) => {
    setAreaOrdersLoading(true)
    try {
      const result = await fetchTasksArea(rayon)
      setAreaOrders(
        result.groups.flatMap((group) => group.subgroups.flatMap((subgroup) => subgroup.features)),
      )
    } catch (e) {
      setLoadError(String(e))
      setAreaOrders([])
    } finally {
      setAreaOrdersLoading(false)
    }
  }, [])

  const officeFilteredTaskResult = useMemo((): TaskResult | null => {
    if (!taskResult || !officeAreaOrder) return null
    return filterTaskResultByArea(taskResult, officeAreaOrder)
  }, [taskResult, officeAreaOrder])

  const officeRemainingCount = useMemo(
    () => countTaskResultFeatures(officeFilteredTaskResult),
    [officeFilteredTaskResult],
  )

  const taskFeatures = useMemo(() => {
    if (!taskResult) return []
    if (isAreaSource(taskSource)) return allTaskFeaturesOnMap(taskResult.groups)
    if (taskFilterSelection === TASK_FILTER_NONE) return []
    if (isOfficeUser) {
      if (!officeAreaOrder || !officeFilteredTaskResult) return []
      return allTaskFeaturesOnMap(officeFilteredTaskResult.groups)
    }
    return allTaskFeaturesOnMap(taskResult.groups)
  }, [taskResult, taskSource, taskFilterSelection, isOfficeUser, officeAreaOrder, officeFilteredTaskResult])

  const modalSubgroupFeatures = useMemo(() => {
    if (!editContext || !taskResult) return []
    for (const group of taskResult.groups) {
      if (group.name !== editContext.groupName) continue
      for (const subgroup of group.subgroups) {
        if (subgroup.name === editContext.subgroupName) return subgroup.features
      }
    }
    return []
  }, [editContext, taskResult])

  const sessionRayon = taskResult?.district_name ?? collection.rayon ?? ''

  const editTaskInCurrentResult = useMemo(() => {
    if (!editContext || !taskResult || taskSource !== 'active') return false
    const taskKey = editContext.feature.task_key ?? String(editContext.feature.attributes._task_key ?? '')
    if (!taskKey) return false
    for (const group of taskResult.groups) {
      for (const subgroup of group.subgroups) {
        for (const feat of subgroup.features) {
          const key = feat.task_key ?? String(feat.attributes._task_key ?? '')
          if (key === taskKey) return true
        }
      }
    }
    return false
  }, [editContext, taskResult, taskSource])

  const panelTaskResult = useMemo((): TaskResult | null => {
    if (!taskResult) return null
    if (isAreaSource(taskSource)) return taskResult
    if (isOfficeUser && officeAreaOrder && officeFilteredTaskResult) {
      return officeFilteredTaskResult
    }
    if (taskFilterSelection === TASK_FILTER_NONE) {
      return { ...taskResult, groups: [] }
    }
    return taskResult
  }, [taskResult, taskSource, taskFilterSelection, isOfficeUser, officeAreaOrder, officeFilteredTaskResult])

  const loadTasks = useCallback(
    async (rayon: string, source: TaskSource, applyDateFilter: boolean) => {
      setSourceLoading(true)
      setLoadError(null)
      try {
        if (source === 'active') {
          const result = await fetchActiveTasks(rayon, applyDateFilter)
          setTaskResult(result)
        } else if (isAreaSource(source)) {
          const result = await fetchTasksArea(rayon)
          setTaskResult(result)
        } else if (
          source === 'field' ||
          source === 'done_legal' ||
          source === 'done_illegal' ||
          source === 'clear'
        ) {
          const result = await fetchSnapshotTasks(rayon, source)
          setTaskResult(result)
        } else {
          throw new Error(`Неизвестный источник: ${source}`)
        }
        setTaskSource(source)
        setPanelHighlight(null)
        setModalHighlight(null)
      } catch (e) {
        setLoadError(String(e))
        throw e
      } finally {
        setSourceLoading(false)
      }
    },
    [],
  )

  const handleCollect = async () => {
    const result = await collection.runCollect()
    if (result) {
      setTaskResult(result)
      setTaskSource('active')
      setAreaPolygonsOnMap(false)
      setPanelHighlight(null)
      setModalHighlight(null)
      setLoadError(null)
      setOfficeAreaOrder(null)

      if (isOfficeUser && collection.rayon) {
        setTaskFilterSelection('active')
        setOfficeOrderPickerOpen(true)
        void loadAreaOrders(collection.rayon)
      } else {
        setTaskFilterSelection(TASK_FILTER_NONE)
        setOfficeOrderPickerOpen(false)
      }
    }
  }

  const handleLoadFieldTasks = async () => {
    const rayon = taskResult?.district_name ?? collection.rayon
    if (!rayon) return
    setSourceLoading(true)
    setLoadError(null)
    try {
      const result = await fetchSnapshotTasks(rayon, 'field')
      setTaskResult(result)
      setTaskSource('field')
      setTaskFilterSelection('field')
      setAreaPolygonsOnMap(false)
      setPanelHighlight(null)
      setModalHighlight(null)
    } catch (e) {
      setLoadError(String(e))
    } finally {
      setSourceLoading(false)
    }
  }

  const handleSourceChange = async (source: TaskSource) => {
    if (!taskResult?.district_name) return
    try {
      await loadTasks(taskResult.district_name, source, collection.applyDateFilter)
    } catch {
      /* loadError set in loadTasks */
    }
  }

  const handleRefresh = async () => {
    if (!taskResult?.district_name) return
    if (isAreaSource(taskSource)) {
      await handleSourceChange('area')
      return
    }
    if (taskFilterSelection === TASK_FILTER_NONE) return
    await handleSourceChange(taskFilterSelection)
  }

  const clearHighlightForTask = useCallback((taskKey: string) => {
    const clearIfMatches = (highlight: TaskHighlight | null) => {
      if (!highlight) return highlight
      const popupKey = highlight.popup?.taskKey
      if (popupKey === taskKey) return null
      return highlight
    }
    setPanelHighlight((prev) => clearIfMatches(prev))
    setModalHighlight((prev) => clearIfMatches(prev))
  }, [])

  const handleTaskRemoved = useCallback(
    (taskKey: string) => {
      setTaskResult((prev) => (prev ? removeTaskByKey(prev, taskKey) : prev))
      clearHighlightForTask(taskKey)
    },
    [clearHighlightForTask],
  )

  const handleTaskAttributesPatched = useCallback(
    (taskKey: string, patch: Record<string, unknown>) => {
      setTaskResult((prev) => (prev ? patchTaskAttributes(prev, taskKey, patch) : prev))
      setAreaViewFeature((prev) => {
        if (!prev) return prev
        const key = prev.task_key ?? String(prev.attributes.key ?? '')
        if (key !== taskKey) return prev
        return patchAreaViewFeature(prev, patch)
      })
    },
    [],
  )

  const handleChangeDistrict = () => {
    setTaskResult(null)
    setTaskSource(user?.default_task_source ?? 'active')
    setTaskFilterSelection(TASK_FILTER_NONE)
    setAreaPolygonsOnMap(false)
    setPanelHighlight(null)
    setModalHighlight(null)
    setEditContext(null)
    setPickMode(false)
    setPickLayers([])
    setPlacePointMode(false)
    setPendingOfficeLinkPrefill(null)
    setLoadError(null)
    setOfficeAreaOrder(null)
    setOfficeOrderPickerOpen(false)
    setAreaOrders([])
  }

  const handlePickModeChange = useCallback((active: boolean, layers: LinkLayerInfo[]) => {
    setPickMode(active)
    setPickLayers(layers)
  }, [])

  const handleFeaturePicked = useCallback((taskColumn: string, value: string) => {
    setPickedValue({ column: taskColumn, value })
    setPickMode(false)
    setPickLayers([])
  }, [])

  const resetPlacePointMode = useCallback(() => {
    setPlacePointMode(false)
    setPendingOfficeLinkPrefill(null)
  }, [])

  const handleStartPlaceOfficePoint = useCallback((linkPrefill: Record<string, string> | null) => {
    setEditContext(null)
    setModalHighlight(null)
    setPickMode(false)
    setPickLayers([])
    setPendingOfficeLinkPrefill(linkPrefill)
    setPlacePointMode(true)
  }, [])

  const handleTogglePlacePointMode = useCallback(() => {
    if (placePointMode) {
      resetPlacePointMode()
      return
    }
    setEditContext(null)
    setModalHighlight(null)
    setPickMode(false)
    setPickLayers([])
    setPendingOfficeLinkPrefill(null)
    setPlacePointMode(true)
  }, [placePointMode, resetPlacePointMode])

  const handleMapPointPlaced = useCallback(
    async (lng: number, lat: number) => {
      if (!officeAreaOrder || placePointBusy) return
      const areaKey = officeAreaOrder.task_key ?? String(officeAreaOrder.attributes.key ?? '')
      if (!areaKey) return

      const point: GeoJSON.Point = { type: 'Point', coordinates: [lng, lat] }
      if (
        officeAreaOrder.geometry &&
        !geometryInsideArea(point, officeAreaOrder.geometry)
      ) {
        alert('Точка должна находиться внутри полигона площадного заказа.')
        return
      }

      setPlacePointBusy(true)
      try {
        await createOfficeTask({
          geometry: point,
          area_task_key: areaKey,
          link_prefill: pendingOfficeLinkPrefill,
        })
        resetPlacePointMode()
        if (taskResult?.district_name) {
          await loadTasks(taskResult.district_name, 'active', collection.applyDateFilter)
        }
      } catch (e) {
        alert(String(e))
      } finally {
        setPlacePointBusy(false)
      }
    },
    [
      officeAreaOrder,
      placePointBusy,
      pendingOfficeLinkPrefill,
      resetPlacePointMode,
      taskResult?.district_name,
      loadTasks,
      collection.applyDateFilter,
    ],
  )

  const handleExecuteTask = useCallback(async (ctx: SelectedTaskContext) => {
    try {
      const verified = await buildTaskExecutionContext(
        ctx.groupName,
        ctx.subgroupName,
        ctx.feature,
        ctx.taskSource,
      )
      setEditContext(verified)
    } catch {
      alert('Задача не найдена.')
      throw new Error('task not found')
    }
  }, [])

  if (authLoading) {
    return (
      <div className="district-screen">
        <div className="district-card login-card">
          <p className="district-hint">Загрузка…</p>
        </div>
      </div>
    )
  }

  if (!user) {
    return <LoginScreen />
  }

  if (appView === 'personnel' && user.can_manage_personnel) {
    return (
      <PersonnelScreen
        userLogin={user.login}
        canCreateUsers={user.can_create_users}
        onBack={() => setAppView('workspace')}
        onLogout={logout}
      />
    )
  }

  if (appView === 'statistics') {
    return (
      <StatisticsScreen
        userLogin={user.login}
        userRole={user.role}
        canViewAll={user.can_manage_personnel}
        onBack={() => setAppView('workspace')}
        onLogout={logout}
      />
    )
  }

  if (appView === 'order_tracks' && user.can_manage_personnel) {
    return (
      <OrderTracksScreen
        userLogin={user.login}
        initialRayon={collection.rayon || taskResult?.district_name || ''}
        onBack={() => setAppView('workspace')}
        onLogout={logout}
      />
    )
  }

  if (appView === 'employee_locations' && user.can_manage_personnel) {
    return (
      <EmployeeLocationsScreen
        userLogin={user.login}
        initialRayon={collection.rayon || taskResult?.district_name || ''}
        onBack={() => setAppView('workspace')}
        onLogout={logout}
      />
    )
  }

  if (!taskResult) {
    return (
      <DistrictStartScreen
        rayon={collection.rayon}
        applyDateFilter={collection.applyDateFilter}
        loading={collection.loading || sourceLoading}
        error={collection.error || loadError}
        progress={collection.progress}
        canCollect={user.can_collect}
        canManagePersonnel={user.can_manage_personnel}
        showAreaOrders={user.allowed_task_sources.includes('area')}
        userLogin={user.login}
        onRayonChange={collection.setRayon}
        onApplyDateFilterChange={collection.setApplyDateFilter}
        onCollect={handleCollect}
        onLoadFieldTasks={handleLoadFieldTasks}
        onOpenPersonnel={() => setAppView('personnel')}
        onOpenEmployeeLocations={() => setAppView('employee_locations')}
        onOpenOrderTracks={() => setAppView('order_tracks')}
        onOpenStatistics={() => setAppView('statistics')}
        onLogout={logout}
      />
    )
  }

  const loading = collection.loading || sourceLoading

  const handleTaskFilterChange = async (source: TaskFilterSelection) => {
    setTaskFilterSelection(source)
    setAreaPolygonsOnMap(false)
    setPanelHighlight(null)
    setModalHighlight(null)

    if (source === TASK_FILTER_NONE) {
      if (isAreaSource(taskSource)) {
        setTaskSource(lastTaskSource)
      }
      return
    }

    await handleSourceChange(source)
  }

  const handleOrdersToggle = async () => {
    if (isOfficeUser && officeAreaOrder) {
      setAreaPolygonsOnMap((value) => !value)
      return
    }

    if (areaPolygonsOnMap) {
      setAreaPolygonsOnMap(false)
      if (isAreaSource(taskSource)) {
        setTaskSource(lastTaskSource)
        setPanelHighlight(null)
        if (taskFilterSelection !== TASK_FILTER_NONE) {
          await handleSourceChange(taskFilterSelection)
        }
      }
    } else {
      setTaskFilterSelection(TASK_FILTER_NONE)
      setAreaPolygonsOnMap(true)
      setPanelHighlight(null)
      setModalHighlight(null)
      await handleSourceChange('area')
    }
  }

  const handleOfficeOrderSelect = async (order: TaskFeature) => {
    const key = order.task_key ?? String(order.attributes.key ?? '')
    if (!key) return

    setSourceLoading(true)
    setLoadError(null)
    try {
      await startAreaAnalise(key)
      setOfficeAreaOrder(order)
      setOfficeOrderPickerOpen(false)
      setAreaPolygonsOnMap(false)
      setTaskFilterSelection('active')
      setTaskSource('active')
      setPanelHighlight(null)
      setModalHighlight(null)
      setEditContext(null)
      if (taskResult?.district_name) {
        await loadAreaOrders(taskResult.district_name)
      }
    } catch (e) {
      const message = String(e)
      setLoadError(message)
      alert(message)
      if (taskResult?.district_name) {
        await loadAreaOrders(taskResult.district_name)
      }
    } finally {
      setSourceLoading(false)
    }
  }

  const handlePauseOfficeOrder = async () => {
    if (!officeAreaOrder || !taskResult?.district_name) return
    const key = officeAreaOrder.task_key ?? String(officeAreaOrder.attributes.key ?? '')
    if (!key) return

    setSourceLoading(true)
    setLoadError(null)
    try {
      await pauseAreaAnalise(key)
      await loadAreaOrders(taskResult.district_name)
      setOfficeAreaOrder(null)
      setAreaPolygonsOnMap(false)
      setOfficeOrderPickerOpen(true)
      setPanelHighlight(null)
      setModalHighlight(null)
      setEditContext(null)
    } catch (e) {
      setLoadError(String(e))
    } finally {
      setSourceLoading(false)
    }
  }

  const handleCompleteOfficeOrder = async () => {
    if (!officeAreaOrder || !taskResult?.district_name) return
    const key = officeAreaOrder.task_key ?? String(officeAreaOrder.attributes.key ?? '')
    if (!key) return

    setSourceLoading(true)
    setLoadError(null)
    try {
      await completeAreaAnalise(key)
      await loadTasks(taskResult.district_name, 'active', collection.applyDateFilter)
      await loadAreaOrders(taskResult.district_name)
      setOfficeAreaOrder(null)
      setAreaPolygonsOnMap(false)
      setOfficeOrderPickerOpen(true)
      setPanelHighlight(null)
      setModalHighlight(null)
      setEditContext(null)
    } catch (e) {
      setLoadError(String(e))
    } finally {
      setSourceLoading(false)
    }
  }

  const handleRefreshAreaOrders = () => {
    if (taskResult?.district_name) {
      void loadAreaOrders(taskResult.district_name)
    }
  }

  const officeAwaitingOrder = isOfficeUser && !officeAreaOrder
  const officeWorking = isOfficeUser && officeAreaOrder != null

  return (
    <div className="app">
      <header className="app-header">
        <div className="workspace-header">
          <h1>Monitor Web CRM</h1>
          <div className="workspace-meta">
            <span>
              Район: <strong>{taskResult.district_name}</strong>
            </span>
            <span className="muted">{user.login}</span>
            <span className="muted">На карте: {taskFeatures.length}</span>
            <button type="button" className="btn" onClick={handleChangeDistrict}>
              Сменить район
            </button>
            {user.can_manage_personnel && (
              <button type="button" className="btn" onClick={() => setAppView('personnel')}>
                Персонал
              </button>
            )}
            {user.can_manage_personnel && (
              <button type="button" className="btn" onClick={() => setAppView('employee_locations')}>
                Местоположение сотрудника
              </button>
            )}
            {user.can_manage_personnel && (
              <button type="button" className="btn" onClick={() => setAppView('order_tracks')}>
                Треки заказов
              </button>
            )}
            <button type="button" className="btn" onClick={() => setAppView('statistics')}>
              Статистика
            </button>
            <button type="button" className="btn" onClick={() => void logout()}>
              Выйти
            </button>
            <button type="button" className="btn primary" disabled={loading} onClick={handleRefresh}>
              {loading ? 'Обновление…' : 'Обновить'}
            </button>
          </div>
        </div>
        <TaskSourceTabs
          taskFilterValue={taskFilterSelection}
          allowedSources={user.allowed_task_sources}
          onTaskFilterChange={handleTaskFilterChange}
          ordersOnMap={areaPolygonsOnMap}
          onOrdersToggle={() => void handleOrdersToggle()}
          loading={loading}
          showPauseOrder={officeWorking}
          onPauseOrder={() => void handlePauseOfficeOrder()}
          showCompleteOrder={officeWorking}
          canCompleteOrder={officeRemainingCount === 0}
          completeOrderTitle={
            officeRemainingCount > 0
              ? `В полигоне остались активные задачи: ${officeRemainingCount}`
              : 'Завершить анализ заказа'
          }
          onCompleteOrder={() => void handleCompleteOfficeOrder()}
        />
        {loadError && <div className="error-banner">{loadError}</div>}
      </header>

      <div
        ref={workspace.appBodyRef}
        className={`app-body${workspace.resizing ? ' app-body--resizing' : ''}`}
        style={workspace.layoutStyle}
      >
        <aside className="sidebar">
          <TaskPanel
            taskResult={panelTaskResult}
            taskSource={taskSource}
            tasksHidden={
              (taskFilterSelection === TASK_FILTER_NONE && !isAreaSource(taskSource)) ||
              officeAwaitingOrder
            }
            officeWorking={officeWorking}
            placePointMode={placePointMode}
            placePointDisabled={loading || placePointBusy || pickMode}
            onTogglePlacePoint={handleTogglePlacePointMode}
            onExecute={handleExecuteTask}
            onViewArea={setAreaViewFeature}
            onSelectHighlight={setPanelHighlight}
            onRefresh={handleRefresh}
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
              {activeHighlight?.notificationGroup && (
                <div className="linked-banner notification-banner">
                  Объекты по номеру {activeHighlight.notificationGroup.value}:{' '}
                  {activeHighlight.notificationGroup.total}
                </div>
              )}
              {activeHighlight &&
                !activeHighlight.notificationGroup &&
                activeHighlight.linked.length > 0 && (
                <div className="linked-banner">
                  Привязанные объекты: {activeHighlight.linked.length}
                </div>
              )}
              {pickMode && <div className="pick-banner">Режим выбора на карте — кликните объект</div>}
              {placePointMode && (
                <div className="place-point-banner">
                  Кликните на карте для добавления точки камерального анализа
                </div>
              )}
              <MapView
                taskFeatures={taskFeatures}
                layerConfigByKey={layerConfigByKey}
                districtName={taskResult.district_name}
                taskSource={taskSource}
                showTasksAreaOverlay={areaPolygonsOnMap && !isAreaSource(taskSource)}
                showAreaPolygons={areaPolygonsOnMap}
                showAreaPopups={isAreaSource(taskSource)}
                areaOverlayOrder={officeWorking ? officeAreaOrder : null}
                areaOverlayFilled={officeWorking && areaPolygonsOnMap}
                taskHighlight={activeHighlight}
                pickMode={pickMode}
                pickLayers={pickLayers}
                onFeaturePicked={handleFeaturePicked}
                placePointMode={placePointMode}
                onPointPlaced={(lng, lat) => void handleMapPointPlaced(lng, lat)}
                onExecuteTask={handleExecuteTask}
                onViewArea={setAreaViewFeature}
              />
            </div>
            <MapLegend
              taskFeatures={taskFeatures}
              layerConfigByKey={layerConfigByKey}
              showAreaOverlay={areaPolygonsOnMap && !isAreaSource(taskSource)}
              isAreaMode={isAreaSource(taskSource) && areaPolygonsOnMap}
            />
          </div>
        </main>
      </div>

      <TaskEditModal
        context={editContext}
        subgroupFeatures={modalSubgroupFeatures}
        sessionRayon={sessionRayon}
        taskInCurrentResult={editTaskInCurrentResult}
        canManagePersonnel={user.can_manage_personnel}
        userRole={user.role}
        officeWorking={officeWorking}
        onStartPlaceOfficePoint={handleStartPlaceOfficePoint}
        onClose={() => setEditContext(null)}
        onTaskRemoved={handleTaskRemoved}
        onTaskAttributesPatched={handleTaskAttributesPatched}
        onHighlightChange={setModalHighlight}
        onPickModeChange={handlePickModeChange}
        pickedValue={pickedValue}
        onPickedConsumed={() => setPickedValue(null)}
      />

      <AreaTaskViewModal
        feature={areaViewFeature}
        taskSource={taskSource}
        canManagePersonnel={user.can_manage_personnel}
        canEditTaskNumber={user.can_create_users}
        userRole={user.role}
        onClose={() => setAreaViewFeature(null)}
        onAttributesPatched={handleTaskAttributesPatched}
      />

      {isOfficeUser && officeOrderPickerOpen && (
        <AreaOrderPickerModal
          orders={areaOrders}
          currentUserLogin={user.login}
          loading={areaOrdersLoading || loading}
          onSelect={(order) => void handleOfficeOrderSelect(order)}
          onRefresh={handleRefreshAreaOrders}
        />
      )}

    </div>
  )
}

export default App
