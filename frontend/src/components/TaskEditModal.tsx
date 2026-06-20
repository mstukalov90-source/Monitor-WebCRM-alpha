import { useEffect, useState } from 'react'
import {
  closeTaskIllegal,
  closeTaskLegal,
  fetchLinkLayers,
  fetchLinkedFeatures,
  fetchTask,
  fetchTaskFormFields,
  lookupTaskByFeature,
  sendTaskToField,
  updateTask,
} from '../api/client'
import type { LinkLayerInfo, SelectedTaskContext, TaskHighlight, TaskRecord, TaskSource } from '../types'
import { aiPhotoUuidFromAttributes, isAiPhotoContext, TASK_SOURCE_LABELS } from '../types'

interface TaskEditModalProps {
  context: SelectedTaskContext | null
  onClose: () => void
  onSaved: () => void
  onHighlightChange: (highlight: TaskHighlight | null) => void
  onPickModeChange: (active: boolean, layers: LinkLayerInfo[]) => void
  pickedValue: { column: string; value: string } | null
  onPickedConsumed: () => void
  onViewPhoto: (uuid: string) => void
}

export function TaskEditModal({
  context,
  onClose,
  onSaved,
  onHighlightChange,
  onPickModeChange,
  pickedValue,
  onPickedConsumed,
  onViewPhoto,
}: TaskEditModalProps) {
  const [record, setRecord] = useState<TaskRecord | null>(null)
  const [readonlyFields, setReadonlyFields] = useState<string[]>([])
  const [linkFields, setLinkFields] = useState<string[]>([])
  const [labels, setLabels] = useState<Record<string, string>>({})
  const [form, setForm] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  const taskSource: TaskSource = context?.taskSource ?? 'active'
  const isReadonly = taskSource !== 'active'
  const canSendToField = taskSource === 'active'
  const canCloseLegal = taskSource === 'active' || taskSource === 'field'
  const canCloseIllegal = taskSource === 'active' || taskSource === 'field'
  const isAiPhoto = context ? isAiPhotoContext(context.subgroupName, context.feature.layer_key) : false

  const handleViewPhoto = () => {
    if (!context) return
    const uuid =
      record?.photo_uuid?.trim() ||
      aiPhotoUuidFromAttributes(context.feature.attributes) ||
      null
    if (!uuid) {
      setMessage('UUID фотографии не найден')
      return
    }
    onViewPhoto(uuid)
  }

  async function refreshHighlight(ctx: SelectedTaskContext, recordKey: string) {
    try {
      const { linked_features, missing_links } = await fetchLinkedFeatures(recordKey, ctx.groupName)
      onHighlightChange({
        primary: ctx.feature.geometry ?? null,
        linked: linked_features,
        missingLinks: missing_links,
      })
    } catch {
      onHighlightChange({
        primary: ctx.feature.geometry ?? null,
        linked: [],
      })
    }
  }

  useEffect(() => {
    if (!context) {
      setRecord(null)
      onPickModeChange(false, [])
      return
    }

    let cancelled = false
    setLoading(true)
    lookupAndLoad(context)
      .then(async (data) => {
        if (cancelled) return
        setRecord(data.record)
        setReadonlyFields(data.readonly)
        setLinkFields(isReadonly ? [] : data.link)
        setLabels(data.labels)
        const initial: Record<string, string> = {}
        const fields = isReadonly
          ? [...data.readonly, 'sps', 'kgs', 'station_avr']
          : [...data.readonly, ...data.link, 'sps', 'kgs', 'station_avr']
        fields.forEach((f) => {
          initial[f] = String((data.record as unknown as Record<string, unknown>)[f] ?? '')
        })
        setForm(initial)
        await refreshHighlight(context, data.record.key)
      })
      .catch((e) => setMessage(String(e)))
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      onPickModeChange(false, [])
    }
  }, [context, isReadonly])

  async function lookupAndLoad(ctx: SelectedTaskContext) {
    const rec = ctx.taskKey
      ? await fetchTask(ctx.taskKey)
      : await lookupTaskByFeature(ctx.subgroupName, ctx.feature.attributes)
    const fields = await fetchTaskFormFields(rec.key, ctx.groupName, ctx.subgroupName)
    return { record: rec, readonly: fields.readonly_fields, link: fields.link_fields, labels: fields.labels }
  }

  useEffect(() => {
    if (pickedValue && !isReadonly) {
      setForm((prev) => ({ ...prev, [pickedValue.column]: pickedValue.value }))
      setMessage(`Выбрано: ${pickedValue.column} = ${pickedValue.value}`)
      onPickedConsumed()
    }
  }, [pickedValue, onPickedConsumed, isReadonly])

  const startPick = async (column: string) => {
    if (isReadonly) return
    setMessage(`Кликните объект на карте для поля «${labels[column] || column}»`)
    const layers = await fetchLinkLayers(linkFields)
    onPickModeChange(true, layers.layers)
  }

  const handleSave = async () => {
    if (!record || isReadonly) return
    setLoading(true)
    try {
      const updated = await updateTask(record.key, {
        type: form.type,
        photo_uuid: form.photo_uuid || null,
        photo_lens: form.photo_lens || null,
        ogh_id: form.ogh_id || null,
        oati_id: form.oati_id || null,
        earthwork_id: form.earthwork_id || null,
        localwork_id: form.localwork_id || null,
        avr_mos_id: form.avr_mos_id || null,
        sps: form.sps || null,
        kgs: form.kgs || null,
        station_avr: form.station_avr || null,
      })
      setRecord(updated)
      setMessage('Сохранено')
      if (context) await refreshHighlight(context, updated.key)
      onSaved()
    } catch (e) {
      setMessage(String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleAction = async (action: 'field' | 'legal' | 'illegal') => {
    if (!record || isReadonly) return
    if (action !== 'field') await handleSave()
    else if (canSendToField) await handleSave()
    setLoading(true)
    try {
      let result
      if (action === 'field') result = await sendTaskToField(record.key)
      else if (action === 'legal') result = await closeTaskLegal(record.key)
      else result = await closeTaskIllegal(record.key)
      setMessage(`Статус: ${result.status}`)
      onSaved()
      onClose()
    } catch (e) {
      setMessage(String(e))
    } finally {
      setLoading(false)
    }
  }

  if (!context) return null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{isReadonly ? 'Просмотр задачи' : 'Исполнить задачу'}</h2>
        <p className="muted small">Источник: {TASK_SOURCE_LABELS[taskSource]}</p>
        {loading && <p>Загрузка…</p>}
        {record && (
          <>
            <p className="muted small">Ключ: {record.key}</p>
            {context.feature.sent_at && (
              <p className="muted small">
                Отправлено: {new Date(context.feature.sent_at).toLocaleString('ru-RU')}
              </p>
            )}
            {message && <p className="message">{message}</p>}

            <div className="form-section">
              <h4>Источник</h4>
              {readonlyFields.map((f) => (
                <label key={f} className="form-row">
                  <span>{labels[f] || f}</span>
                  <input value={form[f] ?? ''} readOnly />
                </label>
              ))}
            </div>

            {!isReadonly && linkFields.length > 0 && (
              <div className="form-section">
                <h4>Сопоставление</h4>
                {linkFields.map((f) => (
                  <label key={f} className="form-row">
                    <span>{labels[f] || f}</span>
                    <div className="form-row-input">
                      <input
                        value={form[f] ?? ''}
                        onChange={(e) => setForm((prev) => ({ ...prev, [f]: e.target.value }))}
                      />
                      <button type="button" className="btn small" onClick={() => startPick(f)}>
                        На карте
                      </button>
                    </div>
                  </label>
                ))}
              </div>
            )}

            <div className="form-section">
              <h4>Данные из Станции</h4>
              {(['sps', 'kgs', 'station_avr'] as const).map((f) => (
                <label key={f} className="form-row">
                  <span>{labels[f] || f}</span>
                  <input
                    value={form[f] ?? ''}
                    readOnly={isReadonly}
                    onChange={(e) => setForm((prev) => ({ ...prev, [f]: e.target.value }))}
                  />
                </label>
              ))}
            </div>

            <div className="modal-actions">
              {isAiPhoto && record && (
                <button type="button" className="btn" onClick={handleViewPhoto} disabled={loading}>
                  Просмотр фотографии
                </button>
              )}
              {!isReadonly && (
                <button type="button" className="btn" onClick={handleSave} disabled={loading}>
                  Сохранить
                </button>
              )}
              {canSendToField && (
                <button type="button" className="btn" onClick={() => handleAction('field')} disabled={loading}>
                  Отправить в поле
                </button>
              )}
              {canCloseLegal && (
                <button type="button" className="btn" onClick={() => handleAction('legal')} disabled={loading}>
                  Закрыть легальное
                </button>
              )}
              {canCloseIllegal && (
                <button type="button" className="btn" onClick={() => handleAction('illegal')} disabled={loading}>
                  Закрыть нелегальное
                </button>
              )}
              <button type="button" className="btn ghost" onClick={onClose}>
                Закрыть
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export type { TaskEditModalProps }
