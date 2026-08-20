import { useEffect, useMemo, useState } from 'react'
import {
  createReportTemplate,
  deleteReportTemplate,
  exportStatisticsReport,
  fetchReportCatalog,
  fetchReportTemplates,
  updateReportTemplate,
} from '../api/client'
import type {
  ReportCatalog,
  ReportDatasetDef,
  ReportNestMode,
  ReportSheetSpec,
  ReportSpec,
  ReportTemplate,
} from '../types'

interface ReportConstructorModalProps {
  dateFrom: string
  dateTo: string
  userRole?: 'field' | 'office'
  userLogin?: string
  objectType?: 'task' | 'order'
  onClose: () => void
}

function newSheetId(prefix: string, existing: ReportSheetSpec[]): string {
  const used = new Set(existing.map((sheet) => sheet.id))
  if (!used.has(prefix)) return prefix
  let n = 2
  while (used.has(`${prefix}_${n}`)) n += 1
  return `${prefix}_${n}`
}

function emptySheet(dataset: ReportDatasetDef, existing: ReportSheetSpec[]): ReportSheetSpec {
  return {
    id: newSheetId(dataset.id, existing),
    dataset: dataset.id,
    title: dataset.label,
    columns: dataset.columns.map((col) => col.id),
    filters: {},
  }
}

function childSheet(
  parent: ReportSheetSpec,
  dataset: ReportDatasetDef,
  existing: ReportSheetSpec[],
): ReportSheetSpec {
  const sourcesFilter = dataset.filters.find((flt) => flt.id === 'sources')
  return {
    id: newSheetId(dataset.id, existing),
    dataset: dataset.id,
    title: dataset.label,
    columns: dataset.columns.map((col) => col.id),
    filters: sourcesFilter
      ? { sources: sourcesFilter.options.map((opt) => opt.value) }
      : {},
    parent_sheet: parent.id,
    nest: 'related_sheet',
  }
}

export function ReportConstructorModal({
  dateFrom,
  dateTo,
  userRole,
  userLogin,
  objectType,
  onClose,
}: ReportConstructorModalProps) {
  const [catalog, setCatalog] = useState<ReportCatalog | null>(null)
  const [templates, setTemplates] = useState<ReportTemplate[]>([])
  const [spec, setSpec] = useState<ReportSpec>({ name: 'Отчёт', sheets: [] })
  const [selectedSheetId, setSelectedSheetId] = useState('')
  const [templateId, setTemplateId] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([fetchReportCatalog(), fetchReportTemplates()])
      .then(([nextCatalog, nextTemplates]) => {
        if (cancelled) return
        setCatalog(nextCatalog)
        setTemplates(nextTemplates)
        const preset = nextCatalog.presets[0]?.spec
        if (preset) {
          setSpec(preset)
          setSelectedSheetId(preset.sheets[0]?.id ?? '')
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const datasetsById = useMemo(() => {
    const map = new Map<string, ReportDatasetDef>()
    for (const item of catalog?.datasets ?? []) map.set(item.id, item)
    return map
  }, [catalog])

  const rootDatasets = useMemo(
    () => (catalog?.datasets ?? []).filter((item) => item.parent_datasets.length === 0),
    [catalog],
  )

  const selectedSheet = spec.sheets.find((sheet) => sheet.id === selectedSheetId) ?? null
  const selectedDataset = selectedSheet ? datasetsById.get(selectedSheet.dataset) : undefined

  const updateSheet = (sheetId: string, patch: Partial<ReportSheetSpec>) => {
    setSpec((prev) => ({
      ...prev,
      sheets: prev.sheets.map((sheet) => (sheet.id === sheetId ? { ...sheet, ...patch } : sheet)),
    }))
  }

  const handleAddRoot = (datasetId: string) => {
    const dataset = datasetsById.get(datasetId)
    if (!dataset) return
    const sheet = emptySheet(dataset, spec.sheets)
    setSpec((prev) => ({ ...prev, sheets: [...prev.sheets, sheet] }))
    setSelectedSheetId(sheet.id)
  }

  const handleAddChild = (datasetId: string) => {
    if (!selectedSheet) return
    const dataset = datasetsById.get(datasetId)
    if (!dataset) return
    const already = spec.sheets.some(
      (sheet) => sheet.parent_sheet === selectedSheet.id && sheet.dataset === datasetId,
    )
    if (already) {
      const existing = spec.sheets.find(
        (sheet) => sheet.parent_sheet === selectedSheet.id && sheet.dataset === datasetId,
      )
      if (existing) setSelectedSheetId(existing.id)
      return
    }
    const sheet = childSheet(selectedSheet, dataset, spec.sheets)
    setSpec((prev) => ({ ...prev, sheets: [...prev.sheets, sheet] }))
    setSelectedSheetId(sheet.id)
  }

  const handleRemoveSheet = (sheetId: string) => {
    const remaining = spec.sheets.filter(
      (sheet) => sheet.id !== sheetId && sheet.parent_sheet !== sheetId,
    )
    setSpec((prev) => ({ ...prev, sheets: remaining }))
    setSelectedSheetId((prev) => {
      if (prev !== sheetId && remaining.some((sheet) => sheet.id === prev)) return prev
      return remaining[0]?.id ?? ''
    })
  }

  const toggleColumn = (columnId: string) => {
    if (!selectedSheet) return
    const has = (selectedSheet.columns ?? []).includes(columnId)
    const next = has
      ? (selectedSheet.columns ?? []).filter((id) => id !== columnId)
      : [...(selectedSheet.columns ?? []), columnId]
    updateSheet(selectedSheet.id, { columns: next })
  }

  const toggleFilterValue = (filterId: string, value: string) => {
    if (!selectedSheet) return
    const current = (selectedSheet.filters ?? {})[filterId] ?? []
    const next = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value]
    updateSheet(selectedSheet.id, {
      filters: { ...(selectedSheet.filters ?? {}), [filterId]: next },
    })
  }

  const applyPreset = (presetId: string) => {
    const preset = catalog?.presets.find((item) => item.id === presetId)
    if (!preset) return
    setSpec(preset.spec)
    setSelectedSheetId(preset.spec.sheets[0]?.id ?? '')
    setTemplateId('')
  }

  const applyTemplate = (id: string) => {
    setTemplateId(id)
    if (!id) return
    const template = templates.find((item) => item.id === id)
    if (!template) return
    setSpec(template.spec)
    setSelectedSheetId(template.spec.sheets[0]?.id ?? '')
  }

  const handleSaveTemplate = async () => {
    const name = spec.name.trim()
    if (!name) {
      setError('Укажите название отчёта — оно станет именем шаблона')
      return
    }
    setBusy(true)
    setError(null)
    try {
      if (templateId) {
        const updated = await updateReportTemplate(templateId, { name, spec })
        setTemplates((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
      } else {
        const created = await createReportTemplate(name, spec)
        setTemplates((prev) => [created, ...prev])
        setTemplateId(created.id)
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleDeleteTemplate = async () => {
    if (!templateId) return
    setBusy(true)
    setError(null)
    try {
      await deleteReportTemplate(templateId)
      setTemplates((prev) => prev.filter((item) => item.id !== templateId))
      setTemplateId('')
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleExport = async () => {
    setBusy(true)
    setError(null)
    try {
      await exportStatisticsReport({
        spec,
        dateFrom,
        dateTo,
        userRole,
        userLogin,
        objectType,
      })
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const unusedChildren =
    selectedDataset?.child_datasets.filter(
      (child) =>
        !spec.sheets.some(
          (sheet) => sheet.parent_sheet === selectedSheet?.id && sheet.dataset === child.id,
        ),
    ) ?? []

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal report-constructor-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Конструктор Excel-отчёта</h2>
        <p className="muted small">
          Период {dateFrom} — {dateTo}. Выберите наборы данных, колонки и связанные таблицы.
        </p>

        {loading ? (
          <p className="muted">Загрузка каталога…</p>
        ) : (
          <>
            <div className="report-constructor-toolbar">
              <label className="district-field">
                <span>Название</span>
                <input
                  value={spec.name}
                  onChange={(e) => setSpec((prev) => ({ ...prev, name: e.target.value }))}
                />
              </label>
              <label className="district-field">
                <span>Шаблон</span>
                <select value={templateId} onChange={(e) => applyTemplate(e.target.value)}>
                  <option value="">— новый —</option>
                  {templates.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              {(catalog?.presets ?? []).map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() => applyPreset(preset.id)}
                >
                  Пресет: {preset.name}
                </button>
              ))}
            </div>

            <div className="report-constructor-sheets">
              {spec.sheets.map((sheet) => {
                const dataset = datasetsById.get(sheet.dataset)
                const nested = Boolean(sheet.parent_sheet)
                return (
                  <button
                    key={sheet.id}
                    type="button"
                    className={`btn report-sheet-chip${selectedSheetId === sheet.id ? ' primary' : ''}`}
                    onClick={() => setSelectedSheetId(sheet.id)}
                  >
                    {nested ? '↳ ' : ''}
                    {sheet.title || dataset?.label || sheet.dataset}
                  </button>
                )
              })}
              <label className="district-field report-add-dataset">
                <span>Добавить лист</span>
                <select
                  value=""
                  onChange={(e) => {
                    if (e.target.value) handleAddRoot(e.target.value)
                  }}
                >
                  <option value="">— набор данных —</option>
                  {rootDatasets.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {selectedSheet && selectedDataset ? (
              <section className="report-constructor-editor">
                <div className="report-constructor-editor-head">
                  <label className="district-field">
                    <span>Лист</span>
                    <input
                      value={selectedSheet.title}
                      onChange={(e) => updateSheet(selectedSheet.id, { title: e.target.value })}
                    />
                  </label>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => handleRemoveSheet(selectedSheet.id)}
                  >
                    Удалить лист
                  </button>
                </div>
                <p className="muted small">{selectedDataset.description}</p>

                {selectedSheet.parent_sheet && (
                  <label className="district-field">
                    <span>Как выгрузить связанные строки</span>
                    <select
                      value={selectedSheet.nest ?? 'related_sheet'}
                      onChange={(e) =>
                        updateSheet(selectedSheet.id, {
                          nest: e.target.value as ReportNestMode,
                        })
                      }
                    >
                      {(catalog?.nest_modes ?? []).map((mode) => (
                        <option key={mode.id} value={mode.id}>
                          {mode.label}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                <div className="report-columns">
                  <span className="report-columns-label">Колонки</span>
                  <div className="report-columns-list">
                    {selectedDataset.columns.map((col) => (
                      <label key={col.id} className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={(selectedSheet.columns ?? []).includes(col.id)}
                          onChange={() => toggleColumn(col.id)}
                        />
                        {col.label}
                      </label>
                    ))}
                  </div>
                </div>

                {selectedDataset.filters.map((flt) => (
                  <div key={flt.id} className="report-columns">
                    <span className="report-columns-label">{flt.label}</span>
                    <div className="report-columns-list">
                      {flt.options.map((opt) => (
                        <label key={opt.value} className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={((selectedSheet.filters ?? {})[flt.id] ?? []).includes(opt.value)}
                            onChange={() => toggleFilterValue(flt.id, opt.value)}
                          />
                          {opt.label}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}

                {unusedChildren.length > 0 && (
                  <div className="report-related">
                    <span className="report-columns-label">Связанные данные</span>
                    <div className="report-related-actions">
                      {unusedChildren.map((child) => (
                        <button
                          key={child.id}
                          type="button"
                          className="btn"
                          onClick={() => handleAddChild(child.id)}
                        >
                          + {child.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </section>
            ) : (
              <p className="muted">Добавьте лист из каталога или откройте пресет.</p>
            )}
          </>
        )}

        {error && <p className="error-banner small">{error}</p>}

        <div className="modal-actions">
          <button type="button" className="btn" disabled={busy || loading} onClick={() => void handleSaveTemplate()}>
            {templateId ? 'Сохранить шаблон' : 'Сохранить как шаблон'}
          </button>
          {templateId && (
            <button
              type="button"
              className="btn"
              disabled={busy || loading}
              onClick={() => void handleDeleteTemplate()}
            >
              Удалить шаблон
            </button>
          )}
          <button
            type="button"
            className="btn primary"
            disabled={busy || loading || spec.sheets.length === 0}
            onClick={() => void handleExport()}
          >
            {busy ? 'Выгрузка…' : 'Выгрузить Excel'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  )
}
