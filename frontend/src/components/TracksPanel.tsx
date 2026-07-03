import type { TrackFeature } from '../types'
import { formatTrackTableCell, TRACK_TABLE_COLUMNS } from '../types'

interface TracksPanelProps {
  districtName: string
  tracks: TrackFeature[]
  selectedTrackId: string | null
  loading?: boolean
  onSelect: (trackId: string) => void
}

export function TracksPanel({
  districtName,
  tracks,
  selectedTrackId,
  loading,
  onSelect,
}: TracksPanelProps) {
  return (
    <div className="task-panel">
      <div className="task-panel-header">
        <strong>{districtName}</strong>
        <span className="muted">Треки заказов: {tracks.length}</span>
        {loading && <div className="muted small">Загрузка…</div>}
      </div>

      <div className="task-table-wrap">
        <table className="task-table">
          <thead>
            <tr>
              <th>#</th>
              {TRACK_TABLE_COLUMNS.map((col) => (
                <th key={col.field}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tracks.length === 0 && !loading ? (
              <tr>
                <td colSpan={TRACK_TABLE_COLUMNS.length + 1} className="muted">
                  Нет треков в выбранном районе
                </td>
              </tr>
            ) : (
              tracks.map((track) => (
                <tr
                  key={track.id}
                  className={selectedTrackId === track.id ? 'selected' : ''}
                  onClick={() => onSelect(track.id)}
                >
                  <td>{track.id}</td>
                  {TRACK_TABLE_COLUMNS.map((col) => (
                    <td key={col.field}>
                      {formatTrackTableCell(track.attributes[col.field], col.format)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
