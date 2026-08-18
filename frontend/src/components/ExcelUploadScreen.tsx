import { useState } from 'react'
import { uploadExcelFile } from '../api/client'

export function ExcelUploadScreen() {
  const [file, setFile] = useState<File | null>(null)
  const [inputKey, setInputKey] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedName, setSavedName] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) {
      setError('Выберите файл Excel')
      return
    }
    setLoading(true)
    setError(null)
    setSavedName(null)
    try {
      const result = await uploadExcelFile(file)
      setSavedName(result.filename)
      setFile(null)
      setInputKey((n) => n + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="district-screen">
      <div className="district-card login-card">
        <h1>Загрузка Excel</h1>
        <p className="district-hint">Файл сохранится на сервере для другого приложения. Допустимы .xlsx и .xls, до 10 МБ.</p>

        <form className="login-form" onSubmit={handleSubmit}>
          <label className="district-field">
            <span>Файл</span>
            <input
              key={inputKey}
              type="file"
              accept=".xlsx,.xls,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              disabled={loading}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null)
                setSavedName(null)
                setError(null)
              }}
            />
          </label>

          {file && <p className="login-file-name">{file.name}</p>}

          <button type="submit" className="btn primary district-submit" disabled={loading || !file}>
            {loading ? 'Загрузка…' : 'Загрузить'}
          </button>
        </form>

        {savedName && (
          <div className="success-banner">Файл сохранён: {savedName}</div>
        )}
        {error && <div className="error-banner">{error}</div>}

        <a href="/" className="login-extra-link">
          Ко входу
        </a>
      </div>
    </div>
  )
}
