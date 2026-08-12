import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  completeAreaAnalise,
  completeAreaPreAnalise,
  collectTasksByLayers,
  createOfficeTask,
  fetchActiveTasks,
  fetchAllTasksAreaGeoJson,
  fetchLayersConfig,
  fetchSnapshotTasks,
  fetchTasksArea,
  fetchTaskViewContext,
  pauseAreaAnalise,
  pauseAreaPreAnalise,
  startAreaAnalise,
  startAreaPreAnalise,
} from './api/client'
import { AreaOrderPickerModal } from './components/AreaOrderPickerModal'
import { AreaTaskViewModal } from './components/AreaTaskViewModal'
import { DistrictStartScreen } from './components/DistrictStartScreen'
import { LoginScreen } from './components/LoginScreen'
import { MapView } from './components/MapView'
import { MapLegend } from './components/MapLegend'
import { EmployeeLocationsScreen } from './components/EmployeeLocationsScreen'
import { OrderTracksScreen } from './components/OrderTracksScreen'
import { OfficeWorkModeModal } from './components/OfficeWorkModeModal'
import { FieldScoreScreen } from './components/FieldScoreScreen'
import { OrderStatusModal } from './components/OrderStatusModal'
import { PersonnelScreen } from './components/PersonnelScreen'
import { StatisticsScreen } from './components/StatisticsScreen'
import { flattenLayers } from './components/LayerControl'
import { TaskEditModal } from './components/TaskEditModal'
import { FieldMaterialsModal } from './components/FieldMaterialsModal'
import { ResizeHandle } from './components/ResizeHandle'
import { TaskPanel } from './components/TaskPanel'
import { TaskSourceTabs } from './components/TaskSourceTabs'
import { useWorkspaceLayout } from './hooks/useWorkspaceLayout'
import { useAuth } from './context/AuthContext'
import { useTaskCollection } from './components/Toolbar'
import { geoJsonToAreaTaskFeatures } from './lib/areaOrders'
import { allTaskFeaturesOnMap, layerConfigMap } from './lib/taskFeatures'
import {
  countTaskResultFeatures,
  filterTaskResultByAreaAndStage,
  orderHasStageTasks,
} from './lib/filterTasksByArea'
import { geometryInsideArea } from './lib/geometry'
import { buildTaskExecutionContext } from './lib/openTaskExecution'
import {
  patchAreaViewFeature,
  patchTaskAttributes,
  removeTaskByKey,
} from './lib/taskResultMutations'
import type {
  AppView,
  LayerGroupConfig,
  LinkLayerInfo,
  OfficeAnaliseStage,
  OfficeWorkMode,
  SelectedTaskContext,
  StatisticsActionDetail,
  TaskFeature,
  TaskFilterSelection,
  TaskHighlight,
  TaskResult,
  TaskSource,
} from './types'
import { isAreaSource, normalizeRayonName, TASK_FILTER_NONE } from './types'
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
  const [panelSelectFromMap, setPanelSelectFromMap] = useState<SelectedTaskContext | null>(null)
  const [pickMode, setPickMode] = useState(false)
  const [pickLayers, setPickLayers] = useState<LinkLayerInfo[]>([])
  const [pickedValue, setPickedValue] = useState<{ column: string; value: string } | null>(null)
  const [placePointMode, setPlacePointMode] = useState(false)
  const [pendingOfficeLinkPrefill, setPendingOfficeLinkPrefill] = useState<Record<string, string> | null>(null)
  const [placePointBusy, setPlacePointBusy] = useState(false)
  const [appView, setAppView] = useState<AppView>('workspace')
  const [areaViewFeature, setAreaViewFeature] = useState<TaskFeature | null>(null)
  const [orderStatusOpen, setOrderStatusOpen] = useState(false)
  const [fieldScoreOrderKey, setFieldScoreOrderKey] = useState<string | null>(null)
  const [areaPolygonsOnMap, setAreaPolygonsOnMap] = useState(false)
  const [lastTaskSource, setLastTaskSource] = useState<TaskSource>('active')
  const [taskFilterSelection, setTaskFilterSelection] = useState<TaskFilterSelection>(TASK_FILTER_NONE)
  const [officeAreaOrder, setOfficeAreaOrder] = useState<TaskFeature | null>(null)
  const [officeOrderPickerOpen, setOfficeOrderPickerOpen] = useState(false)
  const [officeWorkMode, setOfficeWorkMode] = useState<OfficeWorkMode | null>(null)
  const [officeStage, setOfficeStage] = useState<OfficeAnaliseStage | null>(null)
  const [areaOrders, setAreaOrders] = useState<TaskFeature[]>([])
  const [areaOrdersLoading, setAreaOrdersLoading] = useState(false)
  const [stageTasksByRayon, setStageTasksByRayon] = useState<Record<string, TaskResult>>({})
  const [fieldMaterials, setFieldMaterials] = useState<{
    taskKey: string
    reportId?: number | null
  } | null>(null)

  const isOfficeUser = user?.role === 'office'
  const canPlaceOfficePoints = user?.role === 'office' || user?.role === 'manager'

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
    setOfficeWorkMode(null)
    setOfficeStage(null)
    setOfficeAreaOrder(null)
    setOfficeOrderPickerOpen(false)
    setAreaOrders([])
    setStageTasksByRayon({})
  }, [user?.login])

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

  const loadStageOrders = useCallback(async (stage: OfficeAnaliseStage) => {
    setAreaOrdersLoading(true)
    setLoadError(null)
    try {
      const geojson = await fetchAllTasksAreaGeoJson()
      const allOrders = geoJsonToAreaTaskFeatures(geojson)
      const rayons = [
        ...new Set(
          allOrders
            .map((order) => normalizeRayonName(String(order.attributes.rayon ?? '')))
            .filter(Boolean),
        ),
      ]
      const byRayon: Record<string, TaskResult> = {}
      await Promise.all(
        rayons.map(async (rayon) => {
          try {
            byRayon[rayon] = await fetchActiveTasks(rayon)
          } catch {
            /* skip rayon on error */
          }
        }),
      )
      setStageTasksByRayon(byRayon)
      setAreaOrders(
        allOrders.filter((order) => {
          const rayon = normalizeRayonName(String(order.attributes.rayon ?? ''))
          const tasks = byRayon[rayon]
          return tasks ? orderHasStageTasks(tasks, order, stage) : false
        }),
      )
    } catch (e) {
      setLoadError(String(e))
      setAreaOrders([])
      setStageTasksByRayon({})
    } finally {
      setAreaOrdersLoading(false)
    }
  }, [])

  const officeFilteredTaskResult = useMemo((): TaskResult | null => {
    if (!taskResult || !officeAreaOrder || !officeStage) return null
    return filterTaskResultByAreaAndStage(taskResult, officeAreaOrder, officeStage)
  }, [taskResult, officeAreaOrder, officeStage])

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
    async (rayon: string, source: TaskSource) => {
      setSourceLoading(true)
      setLoadError(null)
      try {
        if (source === 'active') {
          const result = await fetchActiveTasks(rayon)
          setTaskResult(result)
        } else if (isAreaSource(source)) {
          const result = await fetchTasksArea(rayon)
          setTaskResult(result)
        } else if (
          source === 'field' ||
          source === 'delay' ||
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

      if (isOfficeUser && collection.rayon && officeWorkMode === 'map') {
        setTaskFilterSelection('active')
        setOfficeOrderPickerOpen(false)
      } else if (isOfficeUser && collection.rayon && officeStage) {
        setTaskFilterSelection('active')
        setOfficeOrderPickerOpen(true)
        void loadAreaOrders(collection.rayon)
      } else {
        setTaskFilterSelection(TASK_FILTER_NONE)
        setOfficeOrderPickerOpen(false)
      }
    }
  }

  const findAreaFeatureByKey = (result: TaskResult, orderKey: string): TaskFeature | null => {
    for (const group of result.groups) {
      for (const subgroup of group.subgroups) {
        for (const feature of subgroup.features) {
          const key = feature.task_key ?? String(feature.attributes.key ?? '')
          if (key === orderKey) return feature
        }
      }
    }
    return null
  }

  const handleOrderStatusSelect = async (event: StatisticsActionDetail) => {
    const isClosedTask =
      event.action === 'office_closed_legal' || event.action === 'office_closed_illegal'

    if (isClosedTask) {
      setOrderStatusOpen(false)
      const view = await fetchTaskViewContext(event.object_key)
      setEditContext({
        groupName: view.group_name,
        subgroupName: view.subgroup_name,
        feature: {
          ...view.feature,
          task_key: view.task_key,
        },
        taskKey: view.task_key,
        taskSource: event.action === 'office_closed_illegal' ? 'done_illegal' : 'done_legal',
      })
      return
    }

    const rayon = normalizeRayonName(event.rayon ?? '')
    if (!rayon) {
      throw new Error('У события нет района — нельзя загрузить заказ')
    }

    setOrderStatusOpen(false)
    collection.setRayon(rayon)
    setLoadError(null)
    setOfficeAreaOrder(null)
    setPanelHighlight(null)
    setModalHighlight(null)
    setEditContext(null)

    setSourceLoading(true)
    try {
      if (user?.can_collect) {
        const collected = await collectTasksByLayers(
          rayon,
          () => {},
        )
        setTaskResult(collected)
        setTaskSource('active')
      }

      const areaResult = await fetchTasksArea(rayon)
      setTaskResult(areaResult)
      setTaskSource('area')
      setTaskFilterSelection('area')
      setAreaPolygonsOnMap(true)
      setLastTaskSource('active')

      const order = findAreaFeatureByKey(areaResult, event.object_key)
      setAreaViewFeature(order)
    } catch (e) {
      setLoadError(String(e))
      throw e
    } finally {
      setSourceLoading(false)
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
      await loadTasks(taskResult.district_name, source)
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
      const popupKey = highlight.taskKey ?? highlight.popup?.taskKey
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
    if (
      isOfficeUser &&
      (officeWorkMode === 'pre_analise' || officeWorkMode === 'analise') &&
      officeStage
    ) {
      setOfficeOrderPickerOpen(true)
      void loadStageOrders(officeStage)
    } else {
      setOfficeOrderPickerOpen(false)
      setAreaOrders([])
    }
  }

  const handleOfficeModeSelect = (mode: OfficeWorkMode) => {
    setOfficeWorkMode(mode)
    setOfficeAreaOrder(null)
    setTaskResult(null)
    setLoadError(null)
    if (mode === 'pre_analise' || mode === 'analise') {
      setOfficeStage(mode)
      setOfficeOrderPickerOpen(true)
      void loadStageOrders(mode)
    } else {
      setOfficeStage(null)
      setOfficeOrderPickerOpen(false)
      setAreaOrders([])
      setStageTasksByRayon({})
    }
  }

  const handleChangeOfficeMode = () => {
    setOfficeWorkMode(null)
    setOfficeStage(null)
    setOfficeAreaOrder(null)
    setOfficeOrderPickerOpen(false)
    setTaskResult(null)
    setAreaOrders([])
    setStageTasksByRayon({})
    setTaskFilterSelection(TASK_FILTER_NONE)
    setAreaPolygonsOnMap(false)
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
      if (placePointBusy) return
      const isManagerPlace = user?.role === 'manager' || user?.role === 'admin'
      const areaKey = officeAreaOrder
        ? officeAreaOrder.task_key ?? String(officeAreaOrder.attributes.key ?? '')
        : null

      if (!isManagerPlace) {
        if (!officeAreaOrder || !areaKey) return
      }

      const point: GeoJSON.Point = { type: 'Point', coordinates: [lng, lat] }
      if (
        !isManagerPlace &&
        officeAreaOrder?.geometry &&
        !geometryInsideArea(point, officeAreaOrder.geometry)
      ) {
        alert('Точка должна находиться внутри полигона площадного заказа.')
        return
      }

      setPlacePointBusy(true)
      try {
        await createOfficeTask({
          geometry: point,
          area_task_key: areaKey || null,
          link_prefill: pendingOfficeLinkPrefill,
        })
        resetPlacePointMode()
        if (taskResult?.district_name) {
          await loadTasks(taskResult.district_name, 'active')
        }
      } catch (e) {
        alert(String(e))
      } finally {
        setPlacePointBusy(false)
      }
    },
    [
      user?.role,
      officeAreaOrder,
      placePointBusy,
      pendingOfficeLinkPrefill,
      resetPlacePointMode,
      taskResult?.district_name,
      loadTasks,
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

  const handleOfficeOrderSelect = async (order: TaskFeature) => {
    const key = order.task_key ?? String(order.attributes.key ?? '')
    if (!key || !officeStage) return

    const rayon = normalizeRayonName(String(order.attributes.rayon ?? ''))
    if (!rayon) {
      alert('У заказа не указан район')
      return
    }

    setSourceLoading(true)
    setLoadError(null)
    try {
      if (officeStage === 'pre_analise') {
        await startAreaPreAnalise(key)
      } else {
        await startAreaAnalise(key)
      }

      const cached = stageTasksByRayon[rayon]
      if (cached) {
        setTaskResult(cached)
      } else {
        await loadTasks(rayon, 'active')
      }
      collection.setRayon(rayon)

      setOfficeAreaOrder(order)
      setOfficeOrderPickerOpen(false)
      setAreaPolygonsOnMap(false)
      setTaskFilterSelection('active')
      setTaskSource('active')
      setPanelHighlight(null)
      setModalHighlight(null)
      setEditContext(null)
    } catch (e) {
      const message = String(e)
      setLoadError(message)
      alert(message)
      if (officeWorkMode === 'pre_analise' || officeWorkMode === 'analise') {
        await loadStageOrders(officeStage)
      } else if (taskResult?.district_name) {
        await loadAreaOrders(taskResult.district_name)
      }
    } finally {
      setSourceLoading(false)
    }
  }

  const handleStartOfficeStageFromMap = async (
    order: TaskFeature,
    stage: OfficeAnaliseStage,
  ) => {
    const key = order.task_key ?? String(order.attributes.key ?? '')
    const rayon = normalizeRayonName(String(order.attributes.rayon ?? '')) || collection.rayon
    if (!key || !rayon) return

    setSourceLoading(true)
    setLoadError(null)
    try {
      if (stage === 'pre_analise') {
        await startAreaPreAnalise(key)
      } else {
        await startAreaAnalise(key)
      }
      collection.setRayon(rayon)
      await loadTasks(rayon, 'active')
      setOfficeStage(stage)
      setOfficeWorkMode('map')
      setOfficeAreaOrder(order)
      setOfficeOrderPickerOpen(false)
      setAreaPolygonsOnMap(false)
      setTaskFilterSelection('active')
      setTaskSource('active')
      setPanelHighlight(null)
      setModalHighlight(null)
      setEditContext(null)
    } catch (e) {
      const message = String(e)
      setLoadError(message)
      alert(message)
    } finally {
      setSourceLoading(false)
    }
  }

  const handlePauseOfficeOrder = async () => {
    if (!officeAreaOrder || !officeStage) return
    const key = officeAreaOrder.task_key ?? String(officeAreaOrder.attributes.key ?? '')
    if (!key) return

    setSourceLoading(true)
    setLoadError(null)
    try {
      if (officeStage === 'pre_analise') {
        await pauseAreaPreAnalise(key)
      } else {
        await pauseAreaAnalise(key)
      }
      setOfficeAreaOrder(null)
      setAreaPolygonsOnMap(false)
      setPanelHighlight(null)
      setModalHighlight(null)
      setEditContext(null)
      if (officeWorkMode === 'pre_analise' || officeWorkMode === 'analise') {
        setTaskResult(null)
        setOfficeOrderPickerOpen(true)
        await loadStageOrders(officeStage)
      } else if (taskResult?.district_name) {
        const rayon = taskResult.district_name
        const result = await fetchTasksArea(rayon)
        const features = result.groups.flatMap((group) =>
          group.subgroups.flatMap((subgroup) => subgroup.features),
        )
        setAreaOrders(
          features.filter((order) => orderHasStageTasks(taskResult, order, officeStage)),
        )
        setOfficeOrderPickerOpen(true)
      }
    } catch (e) {
      setLoadError(String(e))
    } finally {
      setSourceLoading(false)
    }
  }

  const handleCompleteOfficeOrder = async () => {
    if (!officeAreaOrder || !officeStage) return
    const key = officeAreaOrder.task_key ?? String(officeAreaOrder.attributes.key ?? '')
    if (!key) return
    const rayon =
      taskResult?.district_name ??
      normalizeRayonName(String(officeAreaOrder.attributes.rayon ?? ''))

    setSourceLoading(true)
    setLoadError(null)
    try {
      if (officeStage === 'pre_analise') {
        await completeAreaPreAnalise(key)
      } else {
        await completeAreaAnalise(key)
      }
      setOfficeAreaOrder(null)
      setAreaPolygonsOnMap(false)
      setPanelHighlight(null)
      setModalHighlight(null)
      setEditContext(null)
      if (officeWorkMode === 'pre_analise' || officeWorkMode === 'analise') {
        setTaskResult(null)
        setOfficeOrderPickerOpen(true)
        await loadStageOrders(officeStage)
      } else if (rayon) {
        const refreshed = await fetchActiveTasks(rayon)
        setTaskResult(refreshed)
        setTaskSource('active')
        const result = await fetchTasksArea(rayon)
        const features = result.groups.flatMap((group) =>
          group.subgroups.flatMap((subgroup) => subgroup.features),
        )
        setAreaOrders(
          features.filter((order) => orderHasStageTasks(refreshed, order, officeStage)),
        )
        setOfficeOrderPickerOpen(true)
      }
    } catch (e) {
      setLoadError(String(e))
    } finally {
      setSourceLoading(false)
    }
  }

  const handleRefreshAreaOrders = () => {
    if (officeStage && (officeWorkMode === 'pre_analise' || officeWorkMode === 'analise')) {
      void loadStageOrders(officeStage)
    } else if (taskResult?.district_name) {
      void loadAreaOrders(taskResult.district_name)
    }
  }

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

  if (appView === 'field_score' && fieldScoreOrderKey && user.can_manage_personnel) {
    return (
      <FieldScoreScreen
        orderKey={fieldScoreOrderKey}
        userLogin={user.login}
        canGenerateLetters={user.can_generate_letters}
        onBack={() => {
          setFieldScoreOrderKey(null)
          setAppView('workspace')
          setOrderStatusOpen(true)
        }}
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
        onBack={() => setAppView('workspace')}
        onLogout={logout}
      />
    )
  }

  if (!taskResult) {
    if (isOfficeUser && officeWorkMode == null) {
      return <OfficeWorkModeModal onSelect={handleOfficeModeSelect} />
    }

    if (
      isOfficeUser &&
      (officeWorkMode === 'pre_analise' || officeWorkMode === 'analise') &&
      officeStage
    ) {
      return (
        <div className="district-screen">
          {loadError && <div className="error-banner">{loadError}</div>}
          <AreaOrderPickerModal
            orders={areaOrders}
            currentUserLogin={user.login}
            stage={officeStage}
            groupByRayon
            loading={areaOrdersLoading || sourceLoading}
            onSelect={(order) => void handleOfficeOrderSelect(order)}
            onRefresh={handleRefreshAreaOrders}
            onChangeMode={handleChangeOfficeMode}
          />
        </div>
      )
    }

    return (
      <>
        <DistrictStartScreen
          rayon={collection.rayon}
          loading={collection.loading || sourceLoading}
          error={collection.error || loadError}
          progress={collection.progress}
          canCollect={user.can_collect}
          canManagePersonnel={user.can_manage_personnel}
          showAreaOrders={user.allowed_task_sources.includes('area')}
          showOfficeStageButtons={isOfficeUser && officeWorkMode === 'map'}
          userLogin={user.login}
          onRayonChange={collection.setRayon}
          onCollect={handleCollect}
          onLoadFieldTasks={handleLoadFieldTasks}
          onStartOfficeStage={(order, stage) => void handleStartOfficeStageFromMap(order, stage)}
          onChangeOfficeMode={isOfficeUser ? handleChangeOfficeMode : undefined}
          onOpenPersonnel={() => setAppView('personnel')}
          onOpenEmployeeLocations={() => setAppView('employee_locations')}
          onOpenOrderTracks={() => setAppView('order_tracks')}
          onOpenStatistics={() => setAppView('statistics')}
          onOpenOrderStatus={
            user.can_manage_personnel ? () => setOrderStatusOpen(true) : undefined
          }
          onLogout={logout}
        />
        {orderStatusOpen && (
          <OrderStatusModal
            onClose={() => setOrderStatusOpen(false)}
            onSelectEvent={handleOrderStatusSelect}
            onQualityAssessment={(event) => {
              setOrderStatusOpen(false)
              setFieldScoreOrderKey(event.object_key)
              setAppView('field_score')
            }}
          />
        )}
        <TaskEditModal
          context={editContext}
          subgroupFeatures={[]}
          sessionRayon={collection.rayon}
          taskInCurrentResult={false}
          canManagePersonnel={user.can_manage_personnel}
          canGenerateLetters={user.can_generate_letters}
          canManageFieldStatus={user.can_manage_field_task_status}
          canPostponeTasks={user.can_postpone_tasks}
          userRole={user.role}
          showGroupMap
          onClose={() => setEditContext(null)}
          onTaskRemoved={() => setEditContext(null)}
          onHighlightChange={setModalHighlight}
          onPickModeChange={handlePickModeChange}
          pickedValue={pickedValue}
          onPickedConsumed={() => setPickedValue(null)}
        />
      </>
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

  const officeAwaitingOrder = isOfficeUser && !officeAreaOrder
  const officeWorking = isOfficeUser && officeAreaOrder != null
  const showPlaceOfficePoint =
    (isOfficeUser && officeWorking) || (canPlaceOfficePoints && !isOfficeUser && taskResult != null)

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
            {isOfficeUser && (
              <button type="button" className="btn" onClick={handleChangeOfficeMode}>
                Сменить режим
              </button>
            )}
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
              : officeStage === 'pre_analise'
                ? 'Завершить подготовку заказа'
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
            showPlacePoint={showPlaceOfficePoint}
            placePointMode={placePointMode}
            placePointDisabled={loading || placePointBusy || pickMode}
            onTogglePlacePoint={showPlaceOfficePoint ? handleTogglePlacePointMode : undefined}
            onExecute={handleExecuteTask}
            onViewArea={setAreaViewFeature}
            onSelectHighlight={setPanelHighlight}
            onRefresh={handleRefresh}
            selectFromMap={panelSelectFromMap}
            onSelectFromMapConsumed={() => setPanelSelectFromMap(null)}
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
                onViewFieldReport={(taskKey, reportId) =>
                  setFieldMaterials({ taskKey, reportId })
                }
                onSelectTaskFeature={setPanelSelectFromMap}
              />
            </div>
            <MapLegend
              taskFeatures={taskFeatures}
              layerConfigByKey={layerConfigByKey}
              showAreaOverlay={areaPolygonsOnMap && !isAreaSource(taskSource)}
              isAreaMode={isAreaSource(taskSource) && areaPolygonsOnMap}
              showFieldReports={Boolean(activeHighlight?.fieldReports?.length)}
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
        canGenerateLetters={user.can_generate_letters}
        canManageFieldStatus={user.can_manage_field_task_status}
        canPostponeTasks={user.can_postpone_tasks}
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

      {fieldMaterials && (
        <FieldMaterialsModal
          taskKey={fieldMaterials.taskKey}
          reportId={fieldMaterials.reportId}
          canGenerateLetter={user.can_generate_letters}
          onClose={() => setFieldMaterials(null)}
        />
      )}

      {isOfficeUser && officeOrderPickerOpen && officeStage && (
        <AreaOrderPickerModal
          orders={areaOrders}
          currentUserLogin={user.login}
          stage={officeStage}
          groupByRayon={officeWorkMode !== 'map'}
          loading={areaOrdersLoading || loading}
          onSelect={(order) => void handleOfficeOrderSelect(order)}
          onRefresh={handleRefreshAreaOrders}
          onChangeMode={handleChangeOfficeMode}
        />
      )}

    </div>
  )
}

export default App
