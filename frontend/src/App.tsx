import { useCallback, useEffect, useMemo, useState } from 'react'
import { collectTasksByLayers, fetchLayersConfig, fetchSnapshotTasks, fetchTasksArea } from './api/client'
import { DistrictStartScreen } from './components/DistrictStartScreen'
import { MapView } from './components/MapView'
import { flattenLayers } from './components/LayerControl'
import { PhotoViewModal } from './components/PhotoViewModal'
import { TaskEditModal } from './components/TaskEditModal'
import { TaskPanel } from './components/TaskPanel'
import { TaskSourceTabs } from './components/TaskSourceTabs'
import { useTaskCollection } from './components/Toolbar'
import { allTaskFeaturesOnMap, layerConfigMap } from './lib/taskFeatures'
import { buildTaskExecutionContext } from './lib/openTaskExecution'
import type { LayerGroupConfig, LinkLayerInfo, SelectedTaskContext, TaskHighlight, TaskResult, TaskSource } from './types'
import { areaStatusFromSource, isAreaSource } from './types'
import './App.css'

function App() {
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
  const [photoViewUuid, setPhotoViewUuid] = useState<string | null>(null)

  const activeHighlight = editContext ? modalHighlight : panelHighlight
  const collection = useTaskCollection()

  useEffect(() => {
    fetchLayersConfig()
      .then((cfg) => setLayerGroups(cfg.groups))
      .catch(() => {})
  }, [])

  const allLayers = useMemo(() => flattenLayers(layerGroups), [layerGroups])
  const layerConfigByKey = useMemo(() => layerConfigMap(allLayers), [allLayers])

  const taskFeatures = useMemo(
    () => (taskResult ? allTaskFeaturesOnMap(taskResult.groups) : []),
    [taskResult],
  )

  const loadTasks = useCallback(
    async (rayon: string, source: TaskSource, applyDateFilter: boolean) => {
      setSourceLoading(true)
      setLoadError(null)
      try {
        if (source === 'active') {
          const result = await collectTasksByLayers(rayon, applyDateFilter)
          setTaskResult(result)
        } else if (isAreaSource(source)) {
          const status = areaStatusFromSource(source)
          if (!status) throw new Error('Неизвестный статус площадного заказа')
          const result = await fetchTasksArea(rayon, status)
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
      setPanelHighlight(null)
      setModalHighlight(null)
      setLoadError(null)
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
    await handleSourceChange(taskSource)
  }

  const handleChangeDistrict = () => {
    setTaskResult(null)
    setTaskSource('active')
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
      alert('Задача не найдена в crm.tasks.')
      throw new Error('task not found')
    }
  }, [])

  if (!taskResult) {
    return (
      <DistrictStartScreen
        rayon={collection.rayon}
        applyDateFilter={collection.applyDateFilter}
        loading={collection.loading}
        error={collection.error}
        progress={collection.progress}
        onRayonChange={collection.setRayon}
        onApplyDateFilterChange={collection.setApplyDateFilter}
        onCollect={handleCollect}
      />
    )
  }

  const loading = collection.loading || sourceLoading

  return (
    <div className="app">
      <header className="app-header">
        <div className="workspace-header">
          <h1>Monitor Web CRM</h1>
          <div className="workspace-meta">
            <span>
              Район: <strong>{taskResult.district_name}</strong>
            </span>
            <span className="muted">На карте: {taskFeatures.length}</span>
            <button type="button" className="btn" onClick={handleChangeDistrict}>
              Сменить район
            </button>
            <button type="button" className="btn primary" disabled={loading} onClick={handleRefresh}>
              {loading ? 'Обновление…' : 'Обновить'}
            </button>
          </div>
        </div>
        <TaskSourceTabs value={taskSource} onChange={handleSourceChange} loading={loading} />
        {loadError && <div className="error-banner">{loadError}</div>}
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <TaskPanel
            taskResult={taskResult}
            taskSource={taskSource}
            onExecute={handleExecuteTask}
            onSelectHighlight={setPanelHighlight}
            onRefresh={handleRefresh}
          />
        </aside>
        <main className="map-area">
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
            showTasksAreaOverlay={!isAreaSource(taskSource)}
            showAreaPopups={isAreaSource(taskSource)}
            taskHighlight={activeHighlight}
            pickMode={pickMode}
            pickLayers={pickLayers}
            onFeaturePicked={handleFeaturePicked}
            onExecuteTask={handleExecuteTask}
          />
        </main>
      </div>

      <TaskEditModal
        context={editContext}
        onClose={() => setEditContext(null)}
        onSaved={handleRefresh}
        onHighlightChange={setModalHighlight}
        onPickModeChange={handlePickModeChange}
        pickedValue={pickedValue}
        onPickedConsumed={() => setPickedValue(null)}
        onViewPhoto={setPhotoViewUuid}
      />

      <PhotoViewModal uuid={photoViewUuid} onClose={() => setPhotoViewUuid(null)} />
    </div>
  )
}

export default App
