import { useMemo, useState } from 'react'
import { fetchLinkedFeatures, lookupTaskByFeature, sendAreaToSurvey, releaseAreaFromSurvey, completeAreaSurvey } from '../api/client'
import type { SelectedTaskContext, TaskFeature, TaskGroup, TaskHighlight, TaskResult, TaskSource, TaskTableColumn } from '../types'
import { formatTaskTableCell, isAreaSource, resolveTaskTableColumns, TASK_SOURCE_LABELS, taskExecuteButtonLabel } from '../types'

interface TaskPanelProps {
  taskResult: TaskResult | null
  taskSource: TaskSource
  onExecute: (ctx: SelectedTaskContext) => void | Promise<void>
  onViewArea?: (feature: TaskFeature) => void
  onSelectHighlight: (highlight: TaskHighlight | null) => void
  onRefresh: () => void | Promise<void>
}

export function TaskPanel({
  taskResult,
  taskSource,
  onExecute,
  onViewArea,
  onSelectHighlight,
  onRefresh,
}: TaskPanelProps) {
  const [selectedGroup, setSelectedGroup] = useState(0)
  const [selectedSub, setSelectedSub] = useState(0)
  const [selectedRow, setSelectedRow] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [linkLoading, setLinkLoading] = useState(false)
  const [linkInfo, setLinkInfo] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  const isArea = isAreaSource(taskSource)
  const groups = taskResult?.groups ?? []
  const subgroup = groups[selectedGroup]?.subgroups[selectedSub]
  const features = subgroup?.features ?? []
  const groupName = groups[selectedGroup]?.name ?? ''

  const showSentAt = !isArea && taskSource !== 'active'

  const tableColumns = useMemo((): TaskTableColumn[] => {
    return resolveTaskTableColumns(subgroup?.name, isArea, features.map((f) => f.attributes), showSentAt)
  }, [subgroup?.name, isArea, features, showSentAt])

  const totalCount = useMemo(
    () => groups.reduce((acc, g) => acc + g.subgroups.reduce((a, s) => a + s.features.length, 0), 0),
    [groups],
  )

  const selectedFeature = selectedRow !== null ? features[selectedRow] : null
  const selectedStatus = String(selectedFeature?.attributes?.status ?? '')
  const canSendAreaToSurvey = isArea && selectedFeature && selectedStatus !== 'wip'
  const canManageAreaSurvey = isArea && selectedFeature && selectedStatus === 'wip'

  const loadHighlight = async (row: number) => {
    const feat = features[row]
    if (!feat || !subgroup) {
      onSelectHighlight(null)
      return
    }

    const primary = feat.geometry ?? null
    onSelectHighlight({ primary, linked: [] })
    setLinkInfo(null)

    if (isArea) return

    setLinkLoading(true)
    try {
      let taskKey = feat.task_key
      if (!taskKey) {
        const record = await lookupTaskByFeature(subgroup.name, feat.attributes)
        taskKey = record.key
      }

      const { linked_features, missing_links } = await fetchLinkedFeatures(taskKey, groupName)
      onSelectHighlight({
        primary,
        linked: linked_features,
        missingLinks: missing_links,
      })

      const parts: string[] = []
      if (linked_features.length) {
        parts.push(`Привязано: ${linked_features.length}`)
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
        {taskResult.persist_stats && taskSource === 'active' && (
          <div className="muted small">
            БД: +{taskResult.persist_stats.inserted}, пропущено {taskResult.persist_stats.skipped}
          </div>
        )}
        {linkLoading && <div className="muted small">Загрузка привязок…</div>}
        {linkInfo && !linkLoading && <div className="muted small">{linkInfo}</div>}
        {actionMessage && <div className="muted small">{actionMessage}</div>}
      </div>

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
            {features.map((feat, row) => (
              <tr
                key={row}
                className={selectedRow === row ? 'selected' : ''}
                onClick={() => handleRowClick(row)}
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
            ))}
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
        </div>
      )}
    </div>
  )
}
