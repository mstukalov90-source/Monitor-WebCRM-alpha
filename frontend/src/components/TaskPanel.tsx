import { useMemo, useState } from 'react'
import { fetchLinkedFeatures, fetchTask, lookupTaskByFeature, sendAreaToSurvey, releaseAreaFromSurvey, completeAreaSurvey } from '../api/client'
import type { SelectedTaskContext, TaskGroup, TaskHighlight, TaskResult, TaskSource } from '../types'
import { aiPhotoUuidFromAttributes, isAiPhotoContext, isAreaSource, TASK_SOURCE_LABELS } from '../types'

interface TaskPanelProps {
  taskResult: TaskResult | null
  taskSource: TaskSource
  onExecute: (ctx: SelectedTaskContext) => void
  onSelectHighlight: (highlight: TaskHighlight | null) => void
  onRefresh: () => void | Promise<void>
  onViewPhoto: (uuid: string) => void
}

export function TaskPanel({
  taskResult,
  taskSource,
  onExecute,
  onSelectHighlight,
  onRefresh,
  onViewPhoto,
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

  const fieldNames = useMemo(() => {
    const names = new Set<string>()
    features.forEach((f) => Object.keys(f.attributes).forEach((k) => {
      if (!k.startsWith('_')) names.add(k)
    }))
    return Array.from(names).sort()
  }, [features])

  const totalCount = useMemo(
    () => groups.reduce((acc, g) => acc + g.subgroups.reduce((a, s) => a + s.features.length, 0), 0),
    [groups],
  )

  const showSentAt = !isArea && taskSource !== 'active'

  const selectedFeature = selectedRow !== null ? features[selectedRow] : null
  const selectedStatus = String(selectedFeature?.attributes?.status ?? '')
  const canSendAreaToSurvey = isArea && selectedFeature && selectedStatus !== 'wip'
  const canManageAreaSurvey = isArea && selectedFeature && selectedStatus === 'wip'
  const isAiPhoto =
    !isArea &&
    subgroup != null &&
    isAiPhotoContext(subgroup.name, selectedFeature?.layer_key)
  const canViewAiPhoto = isAiPhoto && selectedFeature != null

  const handleViewPhoto = async () => {
    if (!selectedFeature || !subgroup) return
    let uuid = aiPhotoUuidFromAttributes(selectedFeature.attributes)
    if (!uuid && selectedFeature.task_key) {
      setBusy(true)
      try {
        const record = await fetchTask(selectedFeature.task_key)
        uuid = record.photo_uuid?.trim() || null
      } catch {
        setActionMessage('Не удалось определить UUID фотографии')
        return
      } finally {
        setBusy(false)
      }
    }
    if (!uuid) {
      setActionMessage('UUID фотографии не найден')
      return
    }
    onViewPhoto(uuid)
  }

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
      const taskKey = feature.task_key
      if (taskKey) {
        await fetchTask(taskKey)
      } else {
        await lookupTaskByFeature(subgroup.name, feature.attributes)
      }
      onExecute({
        groupName: groups[selectedGroup].name,
        subgroupName: subgroup.name,
        feature,
        taskKey: taskKey ?? undefined,
        taskSource,
      })
    } catch {
      alert('Задача не найдена в crm.tasks.')
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
              {fieldNames.slice(0, showSentAt ? 5 : 6).map((f) => (
                <th key={f}>{f}</th>
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
                {fieldNames.slice(0, showSentAt ? 5 : 6).map((f) => (
                  <td key={f}>{String(feat.attributes[f] ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {isArea ? (
        <div className="area-actions">
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
          {canViewAiPhoto && (
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={handleViewPhoto}
            >
              Просмотр фотографии
            </button>
          )}
          <button
            type="button"
            className="btn primary"
            disabled={selectedRow === null || busy}
            onClick={handleExecute}
          >
            {taskSource === 'active' ? 'Исполнить задачу' : 'Просмотр задачи'}
          </button>
        </div>
      )}
    </div>
  )
}
