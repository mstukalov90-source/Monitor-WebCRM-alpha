import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchFieldReports, fetchLinkedFeatures, lookupTaskByFeature, sendAreaToSurvey, releaseAreaFromSurvey, completeAreaSurvey } from '../api/client'
import {
  buildGroupedTableRows,
  countNotificationGroup,
  findSiblingFeatures,
  getSubgroupLinkField,
  normalizeLinkValue,
  siblingsToLinkedFeatures,
} from '../lib/notificationSiblings'
import type { SelectedTaskContext, TaskFeature, TaskGroup, TaskHighlight, TaskResult, TaskSource, TaskTableColumn } from '../types'
import { formatTaskTableCell, isAreaSource, isFieldObserved, resolveTaskTableColumns, TASK_SOURCE_LABELS, taskExecuteButtonLabel, areaStatusFromAttributes, AREA_STATUS_COLORS, CRM_GROUP_ORDERS } from '../types'

interface TaskPanelProps {
  taskResult: TaskResult | null
  taskSource: TaskSource
  tasksHidden?: boolean
  officeWorking?: boolean
  placePointMode?: boolean
  placePointDisabled?: boolean
  onTogglePlacePoint?: () => void
  onExecute: (ctx: SelectedTaskContext) => void | Promise<void>
  onViewArea?: (feature: TaskFeature) => void
  onSelectHighlight: (highlight: TaskHighlight | null) => void
  onRefresh: () => void | Promise<void>
  selectFromMap?: SelectedTaskContext | null
  onSelectFromMapConsumed?: () => void
}

export function TaskPanel({
  taskResult,
  taskSource,
  tasksHidden = false,
  officeWorking = false,
  placePointMode = false,
  placePointDisabled = false,
  onTogglePlacePoint,
  onExecute,
  onViewArea,
  onSelectHighlight,
  onRefresh,
  selectFromMap = null,
  onSelectFromMapConsumed,
}: TaskPanelProps) {
  const [selectedGroup, setSelectedGroup] = useState(0)
  const [selectedSub, setSelectedSub] = useState(0)
  const [selectedRow, setSelectedRow] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [linkLoading, setLinkLoading] = useState(false)
  const [linkInfo, setLinkInfo] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({})
  const selectFromMapRef = useRef(selectFromMap)
  selectFromMapRef.current = selectFromMap

  useEffect(() => {
    setSelectedGroup(0)
    setSelectedSub(0)
    setSelectedRow(null)
    setLinkInfo(null)
    setActionMessage(null)
  }, [taskSource])

  const isArea = isAreaSource(taskSource)
  const groups = taskResult?.groups ?? []
  const subgroup = groups[selectedGroup]?.subgroups[selectedSub]
  const features = subgroup?.features ?? []
  const groupName = groups[selectedGroup]?.name ?? ''

  const showSentAt = !isArea && taskSource !== 'active'

  const tableColumns = useMemo((): TaskTableColumn[] => {
    return resolveTaskTableColumns(subgroup?.name, isArea, features.map((f) => f.attributes), showSentAt)
  }, [subgroup?.name, isArea, features, showSentAt])

  const tableRows = useMemo(
    () =>
      buildGroupedTableRows(
        features,
        subgroup?.name ?? '',
        groupName,
        collapsedGroups,
        CRM_GROUP_ORDERS,
      ),
    [features, subgroup?.name, groupName, collapsedGroups],
  )

  const totalCount = useMemo(
    () => groups.reduce((acc, g) => acc + g.subgroups.reduce((a, s) => a + s.features.length, 0), 0),
    [groups],
  )

  const selectedFeature = selectedRow !== null ? features[selectedRow] : null
  const selectedStatus = String(selectedFeature?.attributes?.status ?? '')
  const canSendAreaToSurvey = isArea && selectedFeature && selectedStatus !== 'wip'
  const canManageAreaSurvey = isArea && selectedFeature && selectedStatus === 'wip'

  const loadHighlight = async (
    row: number,
    opts?: {
      subgroup?: typeof subgroup
      groupName?: string
      features?: typeof features
    },
  ) => {
    const activeSubgroup = opts?.subgroup ?? subgroup
    const activeFeatures = opts?.features ?? features
    const activeGroupName = opts?.groupName ?? groupName
    const feat = activeFeatures[row]
    if (!feat || !activeSubgroup) {
      onSelectHighlight(null)
      return
    }

    const primary = feat.geometry ?? null
    const popup = {
      groupName: activeGroupName,
      subgroupName: activeSubgroup.name,
      feature: feat,
      taskKey: feat.task_key ?? undefined,
    }
    onSelectHighlight({
      primary,
      linked: [],
      popup,
      taskKey: feat.task_key ?? undefined,
    })
    setLinkInfo(null)

    if (isArea) return

    setLinkLoading(true)
    try {
      let taskKey = feat.task_key
      if (!taskKey) {
        const record = await lookupTaskByFeature(
          activeSubgroup.name,
          feat.attributes,
          feat.layer_key,
        )
        taskKey = record.key
      }

      const loadReports = isFieldObserved(feat.attributes.field_observed)
      const [linkedResult, reportsResult] = await Promise.all([
        fetchLinkedFeatures(taskKey, activeGroupName),
        loadReports
          ? fetchFieldReports(taskKey).catch(() => ({ reports: [] }))
          : Promise.resolve({ reports: [] }),
      ])
      const { linked_features, missing_links } = linkedResult
      let linked = linked_features
      let notificationGroup: TaskHighlight['notificationGroup']

      const linkField = getSubgroupLinkField(activeSubgroup.name)
      if (activeGroupName === CRM_GROUP_ORDERS && linkField) {
        const linkValue = normalizeLinkValue(feat.attributes[linkField])
        if (linkValue) {
          const siblings = findSiblingFeatures(activeFeatures, feat, linkField, taskKey)
          linked = [...linked, ...siblingsToLinkedFeatures(siblings, linkField, linkValue)]
          const total = countNotificationGroup(activeFeatures, linkField, linkValue)
          if (total > 1) {
            notificationGroup = { value: linkValue, total }
          }
        }
      }

      const fieldReports = reportsResult.reports
      onSelectHighlight({
        primary,
        linked,
        fieldReports: fieldReports.length ? fieldReports : undefined,
        missingLinks: missing_links,
        popup,
        taskKey,
        notificationGroup,
      })

      const parts: string[] = []
      if (notificationGroup) {
        parts.push(`По номеру ${notificationGroup.value}: ${notificationGroup.total}`)
      } else if (linked.length) {
        parts.push(`Связано: ${linked.length}`)
      }
      if (fieldReports.length) {
        parts.push(`Отчёты: ${fieldReports.length}`)
      }
      if (missing_links.length) {
        parts.push(
          missing_links.map((m) => `${m.link_column}=${m.business_id} (не найден)`).join(', '),
        )
      }
      setLinkInfo(parts.length ? parts.join(' · ') : null)
    } catch {
      setLinkInfo(null)
    } finally {
      setLinkLoading(false)
    }
  }

  const handleRowClick = (row: number) => {
    setSelectedRow(row)
    setActionMessage(null)
    void loadHighlight(row)
  }

  useEffect(() => {
    if (!selectFromMap || !taskResult) return

    const request = selectFromMap
    const groupsList = taskResult.groups
    let gi = groupsList.findIndex((g) => g.name === request.groupName)
    if (gi < 0) gi = 0
    const group = groupsList[gi]
    if (!group) {
      onSelectFromMapConsumed?.()
      return
    }

    let si = group.subgroups.findIndex((s) => s.name === request.subgroupName)
    if (si < 0) si = 0
    const sub = group.subgroups[si]
    if (!sub) {
      onSelectFromMapConsumed?.()
      return
    }

    const target = request.feature
    const targetKey = target.task_key ?? String(target.attributes._task_key ?? '')
    const targetGeom = JSON.stringify(target.geometry ?? null)

    let featureIndex = sub.features.findIndex((f) => {
      const key = f.task_key ?? String(f.attributes._task_key ?? '')
      return Boolean(targetKey) && key === targetKey && JSON.stringify(f.geometry ?? null) === targetGeom
    })
    if (featureIndex < 0) {
      featureIndex = sub.features.findIndex(
        (f) =>
          f.layer_key === target.layer_key &&
          JSON.stringify(f.geometry ?? null) === targetGeom,
      )
    }
    if (featureIndex < 0 && targetKey) {
      featureIndex = sub.features.findIndex(
        (f) => (f.task_key ?? String(f.attributes._task_key ?? '')) === targetKey,
      )
    }

    setSelectedGroup(gi)
    setSelectedSub(si)
    setActionMessage(null)

    const consumeIfCurrent = () => {
      onSelectFromMapConsumed?.()
    }

    if (featureIndex < 0) {
      setSelectedRow(null)
      onSelectHighlight(null)
      consumeIfCurrent()
      return
    }

    const feat = sub.features[featureIndex]
    const linkField = getSubgroupLinkField(sub.name)
    if (group.name === CRM_GROUP_ORDERS && linkField) {
      const linkValue = normalizeLinkValue(feat.attributes[linkField])
      if (linkValue) {
        const groupKey = `${linkField}:${linkValue}`
        setCollapsedGroups((prev) =>
          prev[groupKey] ? { ...prev, [groupKey]: false } : prev,
        )
      }
    }

    setSelectedRow(featureIndex)
    void loadHighlight(featureIndex, {
      subgroup: sub,
      groupName: group.name,
      features: sub.features,
    }).finally(() => {
      if (selectFromMapRef.current === request) consumeIfCurrent()
    })
  }, [selectFromMap])

  useEffect(() => {
    if (selectedRow === null) return
    const el = document.querySelector<HTMLElement>(
      `.task-panel tr[data-feature-index="${selectedRow}"]`,
    )
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedRow, selectedGroup, selectedSub, collapsedGroups])
  const handleExecute = async () => {
    if (!subgroup || selectedRow === null || !taskResult) return
    const feature = features[selectedRow]
    if (!feature) return

    setBusy(true)
    try {
      await onExecute({
        groupName: groups[selectedGroup].name,
        subgroupName: subgroup.name,
        feature,
        taskKey: feature.task_key ?? undefined,
        taskSource,
      })
    } catch {
      /* ошибка уже показана в onExecute */
    } finally {
      setBusy(false)
    }
  }

  const handleSendAreaToSurvey = async () => {
    if (!selectedFeature?.task_key) return
    setBusy(true)
    setActionMessage(null)
    try {
      const result = await sendAreaToSurvey(selectedFeature.task_key)
      if (result.status === 'updated') {
        setActionMessage('Отправлено на полевое обследование (статус: wip)')
        await onRefresh()
      } else if (result.status === 'skipped') {
        setActionMessage('Уже на обследовании (wip)')
      } else {
        setActionMessage('Заказ не найден')
      }
    } catch (e) {
      setActionMessage(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleReleaseAreaFromSurvey = async () => {
    if (!selectedFeature?.task_key) return
    setBusy(true)
    setActionMessage(null)
    try {
      const result = await releaseAreaFromSurvey(selectedFeature.task_key)
      if (result.status === 'updated') {
        setActionMessage('Снято с обследования (статус: free)')
        await onRefresh()
      } else {
        setActionMessage('Заказ не найден или не на обследовании')
      }
    } catch (e) {
      setActionMessage(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleCompleteAreaSurvey = async () => {
    if (!selectedFeature?.task_key) return
    setBusy(true)
    setActionMessage(null)
    try {
      const result = await completeAreaSurvey(selectedFeature.task_key)
      if (result.status === 'updated') {
        setActionMessage('Обследование завершено (статус: done)')
        await onRefresh()
      } else {
        setActionMessage('Заказ не найден или не на обследовании')
      }
    } catch (e) {
      setActionMessage(String(e))
    } finally {
      setBusy(false)
    }
  }

  if (!taskResult) {
    return (
      <div className="task-panel empty">
        <p>Выберите район и нажмите «Получить задачу»</p>
      </div>
    )
  }

  if (tasksHidden) {
    return (
      <div className="task-panel empty">
        <p className="muted">Район: <strong>{taskResult.district_name}</strong></p>
        <p>Выберите тип задач в фильтре или включите «Заказы»</p>
      </div>
    )
  }

  return (
    <div className="task-panel">
      <div className="task-panel-header">
        <strong>{taskResult.district_name}</strong>
        <span className="muted">
          {TASK_SOURCE_LABELS[taskSource]}: {totalCount}
        </span>
        {taskSource === 'active' && taskResult.apply_date_filter ? (
          <div className="muted small">
            Период: {taskResult.filter_date_from} — {taskResult.filter_date_to}
          </div>
        ) : taskSource === 'active' ? (
          <div className="muted small">Без фильтра по дате</div>
        ) : null}
        {linkLoading && <div className="muted small">Загрузка привязок…</div>}
        {linkInfo && !linkLoading && <div className="muted small">{linkInfo}</div>}
        {actionMessage && <div className="muted small">{actionMessage}</div>}
      </div>

      {!isArea && (
        <div className="task-tree">
          {groups.map((group: TaskGroup, gi) => (
            <div key={group.name} className="task-tree-group">
              <div className="task-tree-group-name">
                {group.name} (
                {group.subgroups.reduce((a, s) => a + s.features.length, 0)})
              </div>
              {group.subgroups.map((sub, si) => (
                <button
                  key={sub.name}
                  type="button"
                  className={`task-tree-item ${gi === selectedGroup && si === selectedSub ? 'active' : ''}`}
                  onClick={() => {
                    setSelectedGroup(gi)
                    setSelectedSub(si)
                    setSelectedRow(null)
                    onSelectHighlight(null)
                    setLinkInfo(null)
                    setActionMessage(null)
                  }}
                >
                  {sub.name} ({sub.features.length})
                </button>
              ))}
            </div>
          ))}
        </div>
      )}

      <div className="task-table-wrap">
        <table className="task-table">
          <thead>
            <tr>
              <th>{isArea ? 'Заказ' : 'Слой'}</th>
              {showSentAt && <th>Отправлено</th>}
              {tableColumns.map((col) => (
                <th key={col.field}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row) => {
              if (row.kind === 'group') {
                return (
                  <tr
                    key={row.groupKey}
                    className="task-table-group-row"
                    onClick={() =>
                      setCollapsedGroups((prev) => ({
                        ...prev,
                        [row.groupKey]: !row.collapsed,
                      }))
                    }
                  >
                    <td colSpan={tableColumns.length + (showSentAt ? 2 : 1)}>
                      <span className="task-table-group-toggle">{row.collapsed ? '▸' : '▾'}</span>
                      {row.label} ({row.count})
                    </td>
                  </tr>
                )
              }

              const { featureIndex, feature: feat, indent } = row
              const areaStatus = isArea ? areaStatusFromAttributes(feat.attributes) : null
              const rowStyle =
                areaStatus != null
                  ? { borderLeftColor: AREA_STATUS_COLORS[areaStatus] }
                  : undefined
              return (
                <tr
                  key={`${feat.layer_key}-${featureIndex}`}
                  data-feature-index={featureIndex}
                  className={`${selectedRow === featureIndex ? 'selected' : ''}${areaStatus != null ? ' area-order-row' : ''}${indent ? ' task-table-nested-row' : ''}`}
                  style={rowStyle}
                  onClick={() => handleRowClick(featureIndex)}
                >
                  <td>{feat.layer_name}</td>
                  {showSentAt && (
                    <td>{feat.sent_at ? new Date(feat.sent_at).toLocaleString('ru-RU') : ''}</td>
                  )}
                  {tableColumns.map((col) => (
                    <td key={col.field}>
                      {formatTaskTableCell(feat.attributes[col.field], col.format)}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {isArea ? (
        <div className="area-actions">
          <button
            type="button"
            className="btn"
            disabled={selectedRow === null || busy}
            onClick={() => {
              if (selectedFeature && onViewArea) onViewArea(selectedFeature)
            }}
          >
            Просмотр заказа
          </button>
          {canManageAreaSurvey ? (
            <>
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={handleReleaseAreaFromSurvey}
              >
                Снять с обследования
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={handleCompleteAreaSurvey}
              >
                Завершить обследование
              </button>
            </>
          ) : (
            <button
              type="button"
              className="btn primary"
              disabled={!canSendAreaToSurvey || busy}
              onClick={handleSendAreaToSurvey}
            >
              Отправить на полевое обследование
            </button>
          )}
        </div>
      ) : (
        <div className="area-actions">
          <button
            type="button"
            className="btn primary"
            disabled={selectedRow === null || busy}
            onClick={handleExecute}
          >
            {taskExecuteButtonLabel(taskSource)}
          </button>
          {officeWorking && onTogglePlacePoint && (
            <button
              type="button"
              className={`btn${placePointMode ? ' primary' : ''}`}
              disabled={placePointDisabled || busy}
              onClick={onTogglePlacePoint}
            >
              {placePointMode ? 'Отменить добавление' : 'Добавить разрытие на карте'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
