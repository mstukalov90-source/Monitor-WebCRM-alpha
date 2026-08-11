import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchFieldScoreContext, saveFieldScore } from '../api/client'
import { useWorkspaceLayout } from '../hooks/useWorkspaceLayout'
import { formatAreaHectares } from '../types'
import type { FieldScoreContext, FieldScoreValue } from '../types'
import { FIELD_SCORE_LABELS } from '../types'
import { FieldMaterialsModal } from './FieldMaterialsModal'
import { FieldScoreMapView } from './FieldScoreMapView'
import { ResizeHandle } from './ResizeHandle'

interface FieldScoreScreenProps {
  orderKey: string
  userLogin: string
  canGenerateLetters?: boolean
  onBack: () => void
  onLogout: () => Promise<void>
}

const SCORE_OPTIONS: FieldScoreValue[] = ['unsatisfactory', 'satisfactory', 'good']

function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`
}

export function FieldScoreScreen({
  orderKey,
  userLogin,
  onBack,
  onLogout,
}: FieldScoreScreenProps) {
  const workspace = useWorkspaceLayout()
  const [data, setData] = useState<FieldScoreContext | null>(null)
  const [taskScores, setTaskScores] = useState<Record<string, FieldScoreValue>>({})
  const [orderScore, setOrderScore] = useState<FieldScoreValue | ''>('')
  const [selectedTaskKey, setSelectedTaskKey] = useState<string | null>(null)
  const [materialsTaskKey, setMaterialsTaskKey] = useState<string | null>(null)
  const [materialsReportId, setMaterialsReportId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedMessage, setSavedMessage] = useState<string | null>(null)
  const selectedTaskRowRef = useRef<HTMLLIElement | null>(null)
  const selectFromMapRef = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setSavedMessage(null)
    try {
      const result = await fetchFieldScoreContext(orderKey)
      setData(result)
      setTaskScores(result.saved?.task_scores ?? {})
      setOrderScore(result.saved?.order_score ?? '')
      setSelectedTaskKey(result.tasks[0]?.task_key ?? null)
      if (result.errors.length) {
        setError(result.errors.join('; '))
      }
    } catch (e) {
      setError(String(e))
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [orderKey])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!selectFromMapRef.current) return
    selectFromMapRef.current = false
    selectedTaskRowRef.current?.scrollIntoView({ block: 'nearest' })
  }, [selectedTaskKey])

  const allTasksScored = useMemo(() => {
    if (!data) return false
    if (!data.tasks.length) return true
    return data.tasks.every((task) => Boolean(taskScores[task.task_key]))
  }, [data, taskScores])

  const coverageHintLabel = data?.coverage_hint
    ? FIELD_SCORE_LABELS[data.coverage_hint]
    : null

  const materialsTaskIndex = useMemo(() => {
    if (!data || !materialsTaskKey) return -1
    return data.tasks.findIndex((task) => task.task_key === materialsTaskKey)
  }, [data, materialsTaskKey])

  const hasNextMaterialsTask =
    materialsTaskIndex >= 0 && data != null && materialsTaskIndex < data.tasks.length - 1

  const handleSave = async () => {
    if (!data) return
    if (orderScore && !allTasksScored) {
      setError('Сначала оцените все задачи, затем оценку заказа')
      return
    }
    setSaving(true)
    setError(null)
    setSavedMessage(null)
    try {
      const saved = await saveFieldScore(orderKey, {
        task_scores: taskScores,
        order_score: orderScore || null,
      })
      setData((prev) =>
        prev
          ? {
              ...prev,
              saved,
              track_coverage_pct: saved.track_coverage_pct ?? prev.track_coverage_pct,
              coverage_hint: saved.coverage_hint ?? prev.coverage_hint,
            }
          : prev,
      )
      setTaskScores(saved.task_scores)
      setOrderScore(saved.order_score ?? '')
      setSavedMessage('Оценка сохранена')
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const setTaskScore = (taskKey: string, value: FieldScoreValue | '') => {
    setTaskScores((prev) => {
      const next = { ...prev }
      if (!value) delete next[taskKey]
      else next[taskKey] = value
      return next
    })
  }

  const openMaterials = (taskKey: string, reportId?: number | null) => {
    setSelectedTaskKey(taskKey)
    setMaterialsTaskKey(taskKey)
    setMaterialsReportId(reportId ?? null)
  }

  const handleSelectTaskFromMap = useCallback((taskKey: string) => {
    selectFromMapRef.current = true
    setSelectedTaskKey(taskKey)
  }, [])

  const handleNextMaterialsTask = () => {
    if (!data || materialsTaskIndex < 0) return
    const next = data.tasks[materialsTaskIndex + 1]
    if (!next) return
    openMaterials(next.task_key, next.report_id)
  }

  const orderTitle =
    data?.order.task_number?.trim() ||
    data?.order.order_key.slice(0, 8) ||
    orderKey.slice(0, 8)

  return (
    <div className="app">
      <header className="app-header">
        <div className="workspace-header">
          <h1>Оценка качества</h1>
          <div className="workspace-meta">
            <span className="muted">{userLogin}</span>
            <span className="muted">
              {orderTitle}
              {data?.order.rayon ? ` · ${data.order.rayon}` : ''}
            </span>
            <button type="button" className="btn" onClick={onBack}>
              Назад
            </button>
            <button type="button" className="btn" onClick={() => void onLogout()}>
              Выйти
            </button>
            <button
              type="button"
              className="btn"
              disabled={loading || saving}
              onClick={() => void load()}
            >
              {loading ? 'Загрузка…' : 'Обновить'}
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={loading || saving || !data}
              onClick={() => void handleSave()}
            >
              {saving ? 'Сохранение…' : 'Сохранить'}
            </button>
          </div>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {savedMessage && <div className="success-banner">{savedMessage}</div>}
      </header>

      <div
        ref={workspace.appBodyRef}
        className={`app-body${workspace.resizing ? ' app-body--resizing' : ''}`}
        style={workspace.layoutStyle}
      >
        <aside className="sidebar">
          <div className="task-panel field-score-panel">
            {loading && !data ? (
              <p className="muted">Загрузка…</p>
            ) : !data ? (
              <p className="muted">Нет данных по заказу</p>
            ) : (
              <>
                <section className="field-score-section">
                  <h2>Заказ</h2>
                  <p className="muted small">Номер: {data.order.task_number || '—'}</p>
                  <p className="muted small">Район: {data.order.rayon || '—'}</p>
                  <p className="muted small">
                    Площадь: {formatAreaHectares(data.order.area) || '—'}
                  </p>
                  <p className="muted small">
                    Дата обследования: {data.order.date_survey || '—'}
                  </p>
                </section>

                <section className="field-score-section">
                  <h2>
                    Задачи <span className="muted">({data.tasks.length})</span>
                  </h2>
                  {data.tasks.length === 0 ? (
                    <p className="muted small">Нет закрытых задач внутри заказа</p>
                  ) : (
                    <ul className="field-score-task-list">
                      {data.tasks.map((task) => (
                        <li
                          key={task.task_key}
                          className="field-score-task-row"
                          ref={
                            selectedTaskKey === task.task_key ? selectedTaskRowRef : undefined
                          }
                        >
                          <div className="field-score-task-row-main">
                            <button
                              type="button"
                              className={`field-score-task-item${
                                selectedTaskKey === task.task_key ? ' selected' : ''
                              }`}
                              onClick={() => setSelectedTaskKey(task.task_key)}
                              onDoubleClick={() => openMaterials(task.task_key, task.report_id)}
                              title="Двойной клик — открыть полевые материалы"
                            >
                              <span className="field-score-task-label">{task.label}</span>
                              <span className="muted small">
                                {task.subgroup_name || task.group_name || task.source}
                              </span>
                            </button>
                            <button
                              type="button"
                              className="btn small field-score-materials-btn"
                              onClick={() => openMaterials(task.task_key, task.report_id)}
                            >
                              Материалы
                            </button>
                          </div>
                          <label className="district-field field-score-select">
                            <span>Оценка</span>
                            <select
                              value={taskScores[task.task_key] ?? ''}
                              onChange={(e) => {
                                setTaskScore(task.task_key, e.target.value as FieldScoreValue | '')
                              }}
                            >
                              <option value="">— не выставлена —</option>
                              {SCORE_OPTIONS.map((value) => (
                                <option key={value} value={value}>
                                  {FIELD_SCORE_LABELS[value]}
                                </option>
                              ))}
                            </select>
                          </label>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <section className="field-score-section">
                  <h2>Трек</h2>
                  <p className="muted small">
                    Покрытие буфером {data.buffer_meters} м:{' '}
                    <strong>{formatPct(data.track_coverage_pct)}</strong>
                  </p>
                  <p className="muted small">
                    Подсказка по покрытию:{' '}
                    {coverageHintLabel ? (
                      <strong>{coverageHintLabel}</strong>
                    ) : (
                      '—'
                    )}
                  </p>
                  <p className="muted small">
                    Треков: {data.tracks.length}
                    {!data.tracks.length ? ' (трек не найден)' : ''}
                  </p>
                  <p className="muted small">
                    Пороги: &lt;50% неудовл., 50–80% удовлетв., ≥80% хорошо. Подсказка не
                    заменяет ручную оценку заказа.
                  </p>
                </section>

                <section className="field-score-section">
                  <h2>Оценка заказа</h2>
                  <label className="district-field">
                    <span>Итоговая оценка</span>
                    <select
                      value={orderScore}
                      disabled={!allTasksScored}
                      onChange={(e) =>
                        setOrderScore((e.target.value as FieldScoreValue | '') || '')
                      }
                    >
                      <option value="">— не выставлена —</option>
                      {SCORE_OPTIONS.map((value) => (
                        <option key={value} value={value}>
                          {FIELD_SCORE_LABELS[value]}
                        </option>
                      ))}
                    </select>
                  </label>
                  {!allTasksScored && (
                    <p className="muted small">
                      Сначала оцените все задачи, затем выставьте оценку заказа.
                    </p>
                  )}
                  {data.saved && (
                    <p className="muted small">
                      Сохранено: {data.saved.scored_by}
                      {data.saved.updated_at
                        ? ` · ${new Date(data.saved.updated_at).toLocaleString('ru-RU')}`
                        : ''}
                    </p>
                  )}
                </section>
              </>
            )}
          </div>
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
              {data ? (
                <FieldScoreMapView
                  orderGeometry={data.order.geometry}
                  tasks={data.tasks}
                  tracks={data.tracks}
                  selectedTaskKey={selectedTaskKey}
                  onSelectTask={handleSelectTaskFromMap}
                />
              ) : (
                <div className="task-panel empty map-placeholder">
                  <p className="muted">Карта появится после загрузки заказа</p>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
      {materialsTaskKey && (
        <FieldMaterialsModal
          taskKey={materialsTaskKey}
          reportId={materialsReportId}
          canGenerateLetter={false}
          onClose={() => {
            setMaterialsTaskKey(null)
            setMaterialsReportId(null)
          }}
          scoring={{
            value: taskScores[materialsTaskKey] ?? '',
            onChange: (value) => setTaskScore(materialsTaskKey, value),
            onNextTask: handleNextMaterialsTask,
            hasNextTask: hasNextMaterialsTask,
          }}
        />
      )}
    </div>
  )
}
