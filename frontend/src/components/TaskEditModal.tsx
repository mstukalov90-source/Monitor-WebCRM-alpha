import { useEffect, useState } from 'react'
import {
  closeTaskIllegal,
  closeTaskLegal,
  fetchLinkedFeatures,
  fetchTask,
  fetchTaskFormFields,
  lookupFieldSnapshot,
  lookupTaskByFeature,
  markDisruptionAbsent,
  returnTaskToActive,
  sendTaskToField,
  updateTask,
} from '../api/client'
import { TaskExecutorAssign } from './TaskExecutorAssign'
import type { LinkLayerInfo, SelectedTaskContext, TaskHighlight, TaskRecord, TaskSource, UserRole } from '../types'
import { aiPhotoUuidFromAttributes, formatFieldObserved, isAiPhotoContext, TASK_SOURCE_LABELS } from '../types'

type StatusAction = 'field' | 'legal' | 'illegal' | 'clear' | 'active'

type LegalValidation = {
  isValid: boolean
  hasLink: boolean
  hasStation: boolean
  message: string | null
}

const LEGAL_STATION_FIELDS = ['sps', 'station_avr'] as const
const LEGAL_LINK_EXCLUDED_INDEX = 2
const CRM_GROUP_ORDERS = 'Новые ордера ОАТИ, АВР и земляные работы'
const ILLEGAL_CLOSE_REQUIRES_FIELD_SURVEY = 'Не проведено полевое обследование.'

const STATUS_CONFIRM_MESSAGES: Record<StatusAction, string> = {
  field: 'Отправить задачу в поле?',
  legal: 'Закрыть задачу как легальную?',
  illegal: 'Закрыть задачу как нелегальную?',
  clear: 'Отметить задачу: разрытие отсутствует?',
  active: 'Вернуть задачу в активные?',
}

function isFilled(value: string | undefined): boolean {
  return Boolean(value?.trim())
}

function fieldValue(
  form: Record<string, string>,
  record: TaskRecord | null,
  field: string,
): string {
  const fromForm = form[field]?.trim()
  if (fromForm) return fromForm
  if (!record) return ''
  return String((record as unknown as Record<string, unknown>)[field] ?? '').trim()
}

function getLegalLinkFields(linkFields: string[]): string[] {
  return linkFields.filter((_, index) => index !== LEGAL_LINK_EXCLUDED_INDEX)
}

function getLegalValidation(
  form: Record<string, string>,
  legalLinkFields: string[],
  record: TaskRecord | null,
): LegalValidation {
  const hasLink =
    legalLinkFields.length === 0 ||
    legalLinkFields.some((field) => isFilled(fieldValue(form, record, field)))
  const hasStation = LEGAL_STATION_FIELDS.some((field) => isFilled(fieldValue(form, record, field)))

  if (legalLinkFields.length > 0 && !hasLink) {
    return {
      isValid: false,
      hasLink: false,
      hasStation,
      message: 'Заполните хотя бы одно поле в группе «Сопоставление» (кроме третьего).',
    }
  }

  if (!hasStation) {
    return {
      isValid: false,
      hasLink: true,
      hasStation: false,
      message: 'Заполните СПС или АВР в группе «Данные из Станции».',
    }
  }

  return { isValid: true, hasLink: true, hasStation: true, message: null }
}

function isLegalRequiredField(field: string, legalLinkFields: string[]): boolean {
  return legalLinkFields.includes(field) || (LEGAL_STATION_FIELDS as readonly string[]).includes(field)
}

function fieldObservedBadgeClass(value: boolean | null | undefined): string {
  if (value === true) return 'field-observed field-observed-yes'
  if (value === false) return 'field-observed field-observed-no'
  return 'field-observed field-observed-unknown'
}

interface TaskEditModalProps {
  context: SelectedTaskContext | null
  canManagePersonnel: boolean
  userRole: UserRole
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
  canManagePersonnel,
  userRole,
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
  const [pendingStatusAction, setPendingStatusAction] = useState<StatusAction | null>(null)
  const [showLegalRequirements, setShowLegalRequirements] = useState(false)
  const [fieldSnapshotKey, setFieldSnapshotKey] = useState<string | null>(null)
  const [fieldExecutor, setFieldExecutor] = useState<string | null>(null)

  const taskSource: TaskSource = context?.taskSource ?? 'active'
  const isReadonly = taskSource !== 'active'
  const canManageFieldTaskStatus =
    taskSource === 'field' && (userRole === 'admin' || userRole === 'manager')
  const canPerformStatusActions = !isReadonly || canManageFieldTaskStatus
  const canSendToField = taskSource === 'active'
  const canCloseLegal =
    taskSource === 'active' || (taskSource === 'field' && canManageFieldTaskStatus)
  const showIllegalClose =
    taskSource === 'active' || (taskSource === 'field' && canManageFieldTaskStatus)
  const canCloseIllegal = showIllegalClose && record != null && record.field_observed !== false
  const showIllegalFieldHint =
    showIllegalClose && canPerformStatusActions && record?.field_observed === false
  const canMarkDisruptionAbsent =
    taskSource === 'active' || (taskSource === 'field' && canManageFieldTaskStatus)
  const canReturnToActive = canManageFieldTaskStatus
  const hasStatusActions =
    canSendToField ||
    canCloseLegal ||
    showIllegalClose ||
    canMarkDisruptionAbsent ||
    canReturnToActive
  const isAiPhoto = context ? isAiPhotoContext(context.subgroupName, context.feature.layer_key) : false
  const requiresLegalLink = context?.groupName !== CRM_GROUP_ORDERS
  const legalLinkFields = requiresLegalLink ? getLegalLinkFields(linkFields) : []
  const legalValidation = getLegalValidation(form, legalLinkFields, record)
  const showLegalFieldHints = canCloseLegal && canPerformStatusActions

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
      setPendingStatusAction(null)
      setShowLegalRequirements(false)
      onPickModeChange(false, [])
      return
    }

    setPendingStatusAction(null)
    setShowLegalRequirements(false)
    let cancelled = false
    setLoading(true)
    lookupAndLoad(context)
      .then(async (data) => {
        if (cancelled) return
        setRecord(data.record)
        setReadonlyFields(data.readonly)
        setLinkFields(data.link)
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

  useEffect(() => {
    if (!context || taskSource !== 'field' || !record) {
      setFieldSnapshotKey(null)
      setFieldExecutor(null)
      return
    }

    const attrs = context.feature.attributes
    const snapKey = attrs._snapshot_key ? String(attrs._snapshot_key) : ''
    const exec =
      attrs.executor != null && String(attrs.executor).trim() !== ''
        ? String(attrs.executor)
        : null

    if (snapKey) {
      setFieldSnapshotKey(snapKey)
      setFieldExecutor(exec)
      return
    }

    let cancelled = false
    lookupFieldSnapshot(record.key)
      .then((row) => {
        if (cancelled) return
        setFieldSnapshotKey(row.snapshot_key)
        setFieldExecutor(row.executor?.trim() || null)
      })
      .catch(() => {
        if (!cancelled) {
          setFieldSnapshotKey(null)
          setFieldExecutor(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [context, taskSource, record?.key])

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
      setMessage(`Выбрано: ${labels[pickedValue.column] ?? 'значение'} — ${pickedValue.value}`)
      onPickedConsumed()
    }
  }, [pickedValue, onPickedConsumed, isReadonly, labels])

  useEffect(() => {
    if (legalValidation.isValid) {
      setShowLegalRequirements(false)
    }
  }, [legalValidation.isValid])

  const formRowClass = (field: string) => {
    if (!showLegalRequirements || !isLegalRequiredField(field, legalLinkFields)) return 'form-row'

    const filled = isFilled(fieldValue(form, record, field))
    const groupMissing =
      (legalLinkFields.includes(field) && !legalValidation.hasLink) ||
      ((LEGAL_STATION_FIELDS as readonly string[]).includes(field) && !legalValidation.hasStation)

    return ['form-row', groupMissing && !filled && 'form-row-missing'].filter(Boolean).join(' ')
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

  const handleAction = async (action: StatusAction) => {
    if (!record || !canPerformStatusActions) return
    if (action === 'legal') {
      const validation = getLegalValidation(form, legalLinkFields, record)
      if (!validation.isValid) {
        setShowLegalRequirements(true)
        setMessage(validation.message ?? '')
        return
      }
    }
    if (action === 'illegal' && record.field_observed === false) {
      setMessage(ILLEGAL_CLOSE_REQUIRES_FIELD_SURVEY)
      return
    }
    setPendingStatusAction(null)
    const shouldSaveBeforeAction = !isReadonly && action !== 'field' && action !== 'active'
    if (shouldSaveBeforeAction) await handleSave()
    else if (action === 'field' && canSendToField && !isReadonly) await handleSave()
    setLoading(true)
    try {
      let result
      if (action === 'field') result = await sendTaskToField(record.key)
      else if (action === 'legal') result = await closeTaskLegal(record.key)
      else if (action === 'illegal') result = await closeTaskIllegal(record.key)
      else if (action === 'clear') result = await markDisruptionAbsent(record.key)
      else result = await returnTaskToActive(record.key)

      if (action === 'clear') {
        setMessage(
          result.status === 'skipped'
            ? 'Задача уже была отмечена как «разрытие отсутствует».'
            : 'Задача отмечена: разрытие отсутствует.',
        )
      } else if (action === 'active') {
        setMessage(
          result.status === 'deleted'
            ? 'Задача возвращена в активные.'
            : `Статус: ${result.status}`,
        )
      } else {
        setMessage(`Статус: ${result.status}`)
      }
      onSaved()
      onClose()
    } catch (e) {
      setMessage(String(e))
    } finally {
      setLoading(false)
    }
  }

  const requestStatusAction = (action: StatusAction) => {
    if (!record) return
    if (action === 'legal') {
      const validation = getLegalValidation(form, legalLinkFields, record)
      if (!validation.isValid) {
        setShowLegalRequirements(true)
        setMessage(validation.message ?? '')
        return
      }
    }
    if (action === 'illegal' && record.field_observed === false) {
      setMessage(ILLEGAL_CLOSE_REQUIRES_FIELD_SURVEY)
      return
    }
    setShowLegalRequirements(false)
    setMessage('')
    setPendingStatusAction(action)
  }

  const legalLinkLabels = legalLinkFields.map((field) => labels[field] || field)
  const legalStationLabels = LEGAL_STATION_FIELDS.map((field) => labels[field] || field)

  if (!context) return null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{isReadonly ? 'Просмотр задачи' : 'Исполнить задачу'}</h2>
        <p className="muted small">Источник: {TASK_SOURCE_LABELS[taskSource]}</p>
        {loading && <p>Загрузка…</p>}
        {record && (
          <>
            {userRole === 'admin' && (
              <p className="muted small">Ключ: {record.key}</p>
            )}
            <p className={fieldObservedBadgeClass(record.field_observed)}>
              Обследовано в поле: {formatFieldObserved(record.field_observed)}
            </p>
            {context.feature.sent_at && (
              <p className="muted small">
                Отправлено: {new Date(context.feature.sent_at).toLocaleString('ru-RU')}
              </p>
            )}
            {message && <p className="message error-text">{message}</p>}

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
              <div
                className={[
                  'form-section',
                  showLegalRequirements && requiresLegalLink && !legalValidation.hasLink && 'form-section-missing',
                ]
                  .filter(Boolean)
                  .join(' ')}
              >
                <h4>Сопоставление</h4>
                {showLegalFieldHints && requiresLegalLink && (
                  <p className="field-group-hint">
                    Для «Закрыть легальное» — одно из: {legalLinkLabels.join(', ')}
                  </p>
                )}
                {linkFields.map((f) => (
                  <label key={f} className={formRowClass(f)}>
                    <span>
                      {labels[f] || f}
                      {showLegalFieldHints && requiresLegalLink && legalLinkFields.includes(f) && (
                        <span className="required-marker">*</span>
                      )}
                    </span>
                    <input
                      value={form[f] ?? ''}
                      onChange={(e) => setForm((prev) => ({ ...prev, [f]: e.target.value }))}
                    />
                  </label>
                ))}
              </div>
            )}

            <div
              className={[
                'form-section',
                showLegalRequirements && !legalValidation.hasStation && 'form-section-missing',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              <h4>Данные из Станции</h4>
              {showLegalFieldHints && (
                <p className="field-group-hint">
                  Для «Закрыть легальное» — одно из: {legalStationLabels.join(' или ')}
                </p>
              )}
              {(['sps', 'kgs', 'station_avr'] as const).map((f) => (
                <label key={f} className={formRowClass(f)}>
                  <span>
                    {labels[f] || f}
                    {showLegalFieldHints && (f === 'sps' || f === 'station_avr') && (
                      <span className="required-marker">*</span>
                    )}
                  </span>
                  <input
                    value={form[f] ?? ''}
                    readOnly={isReadonly}
                    onChange={(e) => setForm((prev) => ({ ...prev, [f]: e.target.value }))}
                  />
                </label>
              ))}
            </div>

            {taskSource === 'field' && fieldSnapshotKey && (
              <TaskExecutorAssign
                table="field"
                assignmentKey={fieldSnapshotKey}
                initialExecutor={fieldExecutor}
                canManage={canManagePersonnel}
                onAssigned={(executor) => {
                  setFieldExecutor(executor)
                  onSaved()
                }}
              />
            )}

            <div className="modal-actions">
              <div className="modal-action-group">
                <h4>Управление задачей</h4>
                <div className="modal-action-buttons">
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
                  <button type="button" className="btn" onClick={onClose}>
                    Закрыть
                  </button>
                </div>
              </div>

              {hasStatusActions && (
                <div className="modal-action-group">
                  <h4>Изменить статус задачи</h4>
                  {showLegalFieldHints && (
                    <p className="legal-requirements">
                      <span className="required-marker">*</span> Для «Закрыть легальное»:
                      {requiresLegalLink
                        ? ' одно поле «Сопоставление» (кроме третьего) и СПС или АВР в «Данные из Станции».'
                        : ' СПС или АВР в «Данные из Станции».'}
                    </p>
                  )}
                  {showIllegalFieldHint && (
                    <p className="illegal-requirements">{ILLEGAL_CLOSE_REQUIRES_FIELD_SURVEY}</p>
                  )}
                  {pendingStatusAction ? (
                    <div className="status-confirm">
                      <p>{STATUS_CONFIRM_MESSAGES[pendingStatusAction]}</p>
                      <div className="modal-action-buttons">
                        <button
                          type="button"
                          className="btn primary"
                          disabled={loading}
                          onClick={() => void handleAction(pendingStatusAction)}
                        >
                          Подтвердить
                        </button>
                        <button
                          type="button"
                          className="btn"
                          disabled={loading}
                          onClick={() => setPendingStatusAction(null)}
                        >
                          Отмена
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="modal-action-buttons">
                      {canSendToField && (
                        <button
                          type="button"
                          className="btn btn-status-field"
                          onClick={() => requestStatusAction('field')}
                          disabled={loading}
                        >
                          Отправить в поле
                        </button>
                      )}
                      {canCloseLegal && (
                        <button
                          type="button"
                          className="btn btn-status-legal"
                          onClick={() => requestStatusAction('legal')}
                          disabled={loading}
                        >
                          Закрыть легальное
                        </button>
                      )}
                      {showIllegalClose && (
                        <button
                          type="button"
                          className="btn btn-status-illegal"
                          onClick={() => requestStatusAction('illegal')}
                          disabled={!canCloseIllegal || loading}
                          title={showIllegalFieldHint ? ILLEGAL_CLOSE_REQUIRES_FIELD_SURVEY : undefined}
                        >
                          Закрыть нелегальное
                        </button>
                      )}
                      {canMarkDisruptionAbsent && (
                        <button
                          type="button"
                          className="btn btn-status-clear"
                          onClick={() => requestStatusAction('clear')}
                          disabled={loading}
                        >
                          Разрытие отсутствует
                        </button>
                      )}
                      {canReturnToActive && (
                        <button
                          type="button"
                          className="btn btn-status-active"
                          onClick={() => requestStatusAction('active')}
                          disabled={loading}
                        >
                          Вернуть в активные
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export type { TaskEditModalProps }
