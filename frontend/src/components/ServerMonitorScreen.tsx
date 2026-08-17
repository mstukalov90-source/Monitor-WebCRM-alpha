import { useCallback, useEffect, useState } from 'react'
import { fetchMonitorStatus } from '../api/client'
import type {
  MonitorApp,
  MonitorDatabase,
  MonitorHost,
  MonitorLevel,
  MonitorStatus,
  MonitorUnit,
} from '../types'

const POLL_MS = 10_000

interface ServerMonitorScreenProps {
  userLogin: string
  onBack: () => void
  onLogout: () => Promise<void>
}

export function ServerMonitorScreen({ userLogin, onBack, onLogout }: ServerMonitorScreenProps) {
  const [data, setData] = useState<MonitorStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const next = await fetchMonitorStatus()
      setData(next)
      setError(null)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const id = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(id)
  }, [load])

  const overall = data?.overall ?? 'ok'
  const dockerUnits = data?.units.filter((u) => u.kind === 'docker') ?? []
  const dockerUp = dockerUnits.filter((u) => u.state === 'running').length

  return (
    <div className="district-screen statistics-screen monitor-screen">
      <div className="statistics-layout">
        <div className="district-card statistics-card">
          <div className="workspace-meta district-user-meta">
            <span className="muted">{userLogin} (мониторинг сервера)</span>
            <button type="button" className="btn" onClick={onBack}>
              К карте
            </button>
            <button type="button" className="btn" onClick={() => void onLogout()}>
              Выйти
            </button>
          </div>

          <div className="monitor-title-row">
            <h1>Мониторинг</h1>
            <div className="monitor-refresh">
              <span className="muted">
                {data ? `обновлено ${formatClock(data.collected_at)}` : loading ? 'загрузка…' : ''}
                {' · авто 10с'}
              </span>
              <button type="button" className="btn" disabled={loading} onClick={() => void load()}>
                Обновить
              </button>
            </div>
          </div>

          {error && <div className="personnel-message monitor-error">{error}</div>}

          {data && (
            <>
              <div className={`monitor-banner monitor-banner-${overall}`}>
                <span className={`monitor-dot monitor-dot-${overall}`} />
                <strong>Система {levelLabel(overall)}</strong>
                <span>
                  контейнеры {dockerUp}/{dockerUnits.length} up
                </span>
                {data.database && (
                  <span>
                    БД {data.database.connections}
                    {data.database.max_connections != null
                      ? `/${data.database.max_connections}`
                      : ''}
                  </span>
                )}
                {data.host && <span>CPU {fmtPct(data.host.cpu_percent)}</span>}
                {data.host && <span>RAM {fmtPct(data.host.memory_percent)}</span>}
              </div>

              {data.warnings.length > 0 && (
                <ul className="monitor-warnings">
                  {data.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              )}

              <div className="monitor-cards">
                <HostCard host={data.host} />
                <DatabaseCard database={data.database} />
                <AppCard app={data.app} />
              </div>

              <section className="statistics-section">
                <h2>Контейнеры и сервисы</h2>
                {data.units.length === 0 ? (
                  <p className="muted">Нет данных о контейнерах и сервисах</p>
                ) : (
                  <div className="monitor-table-wrap">
                    <table className="monitor-table">
                      <thead>
                        <tr>
                          <th>имя</th>
                          <th>тип</th>
                          <th>CPU</th>
                          <th>RAM</th>
                          <th>uptime</th>
                          <th>health</th>
                          <th>статус</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.units.map((unit) => (
                          <UnitRow key={`${unit.kind}-${unit.name}`} unit={unit} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="statistics-section">
                <h2>Последние операции</h2>
                {data.operations.length === 0 ? (
                  <p className="muted">Пока нет записей (лента в памяти процесса, сбрасывается при рестарте)</p>
                ) : (
                  <div className="monitor-table-wrap">
                    <table className="monitor-table">
                      <thead>
                        <tr>
                          <th>время</th>
                          <th>операция</th>
                          <th>статус</th>
                          <th>детали</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.operations.map((op, index) => (
                          <tr key={`${op.ts}-${op.name}-${index}`}>
                            <td>{formatClock(op.ts)}</td>
                            <td>{op.name}</td>
                            <td>
                              <span className={`monitor-pill monitor-pill-${op.status}`}>
                                {levelLabel(op.status)}
                              </span>
                            </td>
                            <td className="monitor-detail">{op.detail}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function HostCard({ host }: { host: MonitorHost | null }) {
  return (
    <article className="monitor-card">
      <h2>Железо</h2>
      {!host ? (
        <p className="muted">Нет данных</p>
      ) : (
        <>
          <Meter label={`CPU ${fmtPct(host.cpu_percent)}`} percent={host.cpu_percent} />
          {host.loadavg && (
            <p className="muted monitor-sub">
              load {host.loadavg.map((v) => v.toFixed(2)).join('  ')}
            </p>
          )}
          <Meter
            label={`RAM ${formatBytes(host.memory_used_bytes)} / ${formatBytes(host.memory_total_bytes)}`}
            percent={host.memory_percent}
          />
          {host.disks.map((disk) => (
            <Meter
              key={disk.path}
              label={`Диск ${disk.label} ${fmtPct(disk.percent)}`}
              percent={disk.percent}
            />
          ))}
        </>
      )}
    </article>
  )
}

function DatabaseCard({ database }: { database: MonitorDatabase | null }) {
  const connPct =
    database && database.max_connections
      ? (100 * database.connections) / database.max_connections
      : 0
  return (
    <article className="monitor-card">
      <h2>База данных</h2>
      {!database ? (
        <p className="muted">Нет данных</p>
      ) : (
        <>
          <Meter
            label={`Соединения ${database.connections}${
              database.max_connections != null ? ` / ${database.max_connections}` : ''
            }`}
            percent={connPct}
          />
          <p>Active queries: {database.active_queries}</p>
          <p>Cache hit: {database.cache_hit_percent != null ? fmtPct(database.cache_hit_percent) : '—'}</p>
          <p>Размер БД: {formatBytes(database.size_bytes)}</p>
          <p>Долгие &gt;5с: {database.slow_queries.length}</p>
        </>
      )}
    </article>
  )
}

function AppCard({ app }: { app: MonitorApp | null }) {
  const poolPct = app && app.pool_max ? (100 * app.pool_in_use) / app.pool_max : 0
  return (
    <article className="monitor-card">
      <h2>WebCRM</h2>
      {!app ? (
        <p className="muted">Нет данных</p>
      ) : (
        <>
          <p>
            uvicorn <span className="monitor-pill monitor-pill-ok">{app.status}</span>
          </p>
          <p>
            RSS {app.rss_bytes != null ? formatBytes(app.rss_bytes) : '—'}
            {app.cpu_percent != null ? `  CPU ${fmtPct(app.cpu_percent)}` : ''}
          </p>
          <Meter label={`Pool ${app.pool_in_use} / ${app.pool_max}`} percent={poolPct} />
          <p>req/мин: {app.requests_per_minute}</p>
          <p>p95: {app.p95_ms != null ? `${Math.round(app.p95_ms)}ms` : '—'}</p>
        </>
      )}
    </article>
  )
}

function UnitRow({ unit }: { unit: MonitorUnit }) {
  return (
    <tr className={`monitor-row-${unit.level}`}>
      <td>{unit.name}</td>
      <td>{unit.kind}</td>
      <td>{unit.cpu_percent != null ? fmtPct(unit.cpu_percent) : '—'}</td>
      <td>{unit.memory_bytes != null ? formatBytes(unit.memory_bytes) : '—'}</td>
      <td>{formatUptime(unit.uptime_seconds)}</td>
      <td>{unit.health ?? '—'}</td>
      <td>
        <span className={`monitor-pill monitor-pill-${unit.level}`}>{unit.state}</span>
      </td>
    </tr>
  )
}

function Meter({ label, percent }: { label: string; percent: number }) {
  const clamped = Math.max(0, Math.min(100, percent))
  const tone = clamped >= 95 ? 'error' : clamped >= 85 ? 'warn' : 'ok'
  return (
    <div className="monitor-meter">
      <div className="monitor-meter-label">{label}</div>
      <div className="monitor-meter-track" aria-hidden>
        <div
          className={`monitor-meter-fill monitor-meter-fill-${tone}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  )
}

function levelLabel(level: MonitorLevel): string {
  if (level === 'ok') return 'OK'
  if (level === 'warn') return 'WARN'
  return 'ERROR'
}

function fmtPct(value: number): string {
  return `${value.toFixed(value >= 10 ? 0 : 1)}%`
}

function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  const digits = value >= 10 || index === 0 ? 0 : 1
  return `${value.toFixed(digits)} ${units[index]}`
}

function formatUptime(seconds: number | null): string {
  if (seconds == null) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}д ${hours}ч`
  if (hours > 0) return `${hours}ч ${minutes}м`
  return `${minutes}м`
}

function formatClock(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
