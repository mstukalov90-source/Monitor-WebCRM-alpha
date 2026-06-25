import { useCallback, useEffect, useMemo, useState } from 'react'
import { collectTasksByLayers, fetchLayersConfig, fetchSnapshotTasks, fetchTasksArea } from './api/client'
import { AreaTaskViewModal } from './components/AreaTaskViewModal'
import { DistrictStartScreen } from './components/DistrictStartScreen'
import { LoginScreen } from './components/LoginScreen'
import { MapView } from './components/MapView'
import { MapLegend } from './components/MapLegend'
import { PersonnelScreen } from './components/PersonnelScreen'
import { flattenLayers } from './components/LayerControl'
import { TaskEditModal } from './components/TaskEditModal'
import { ResizeHandle } from './components/ResizeHandle'
import { TaskPanel } from './components/TaskPanel'
import { TaskSourceTabs } from './components/TaskSourceTabs'
import { useWorkspaceLayout } from './hooks/useWorkspaceLayout'
import { useAuth } from './context/AuthContext'
import { useTaskCollection } from './components/Toolbar'
import { allTaskFeaturesOnMap, layerConfigMap } from './lib/taskFeatures'
import { buildTaskExecutionContext } from './lib/openTaskExecution'
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
  const [appView, setAppView] = useState<AppView>('workspace')
  const [areaViewFeature, setAreaViewFeature] = useState<TaskFeature | null>(null)
  const [areaPolygonsOnMap, setAreaPolygonsOnMap] = useState(false)
  const [lastTaskSource, setLastTaskSource] = useState<TaskSource>('active')
  const [taskFilterSelection, setTaskFilterSelection] = useState<TaskFilterSelection>(TASK_FILTER_NONE)

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

  const taskFeatures = useMemo(() => {
    if (!taskResult) return []
    if (isAreaSource(taskSource)) return allTaskFeaturesOnMap(taskResult.groups)
    if (taskFilterSelection === TASK_FILTER_NONE) return []
    return allTaskFeaturesOnMap(taskResult.groups)
  }, [taskResult, taskSource, taskFilterSelection])

  const panelTaskResult = useMemo((): TaskResult | null => {
    if (!taskResult) return null
    if (isAreaSource(taskSource)) return taskResult
    if (taskFilterSelection === TASK_FILTER_NONE) {
      return { ...taskResult, groups: [] }
    }
    return taskResult
  }, [taskResult, taskSource, taskFilterSelection])

  const loadTasks = useCallback(
    async (rayon: string, source: TaskSource, applyDateFilter: boolean) => {
      setSourceLoading(true)
      setLoadError(null)
      try {
        if (source === 'active') {
          const result = await collectTasksByLayers(rayon, applyDateFilter)
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
      setTaskFilterSelection(TASK_FILTER_NONE)
      setAreaPolygonsOnMap(false)
      setPanelHighlight(null)
      setModalHighlight(null)
      setLoadError(null)
    }
  }

  const handleLoadFieldTasks = async () => {
    if (!collection.rayon) return
    setSourceLoading(true)
    setLoadError(null)
    try {
      const result = await fetchSnapshotTasks(collection.rayon, 'field')
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
    setLoadError(null)
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
        userLogin={user.login}
        onRayonChange={collection.setRayon}
        onApplyDateFilterChange={collection.setApplyDateFilter}
        onCollect={handleCollect}
        onLoadFieldTasks={handleLoadFieldTasks}
        onOpenPersonnel={() => setAppView('personnel')}
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
      setAreaPolygonsOnMap(true)
      await handleSourceChange('area')
    }
  }

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
            tasksHidden={taskFilterSelection === TASK_FILTER_NONE && !isAreaSource(taskSource)}
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
              {activeHighlight && activeHighlight.linked.length > 0 && (
                <div className="linked-banner">
                  Привязанные объекты: {activeHighlight.linked.length}
                </div>
              )}
              {pickMode && <div className="pick-banner">Режим выбора на карте — кликните объект</div>}
              <MapView
                taskFeatures={taskFeatures}
                layerConfigByKey={layerConfigByKey}
                districtName={taskResult.district_name}
                taskSource={taskSource}
                showTasksAreaOverlay={areaPolygonsOnMap && !isAreaSource(taskSource)}
                showAreaPolygons={areaPolygonsOnMap}
                showAreaPopups={isAreaSource(taskSource)}
                taskHighlight={activeHighlight}
                pickMode={pickMode}
                pickLayers={pickLayers}
                onFeaturePicked={handleFeaturePicked}
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
        canManagePersonnel={user.can_manage_personnel}
        userRole={user.role}
        onClose={() => setEditContext(null)}
        onSaved={handleRefresh}
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
        onSaved={handleRefresh}
      />

    </div>
  )
}

export default App
