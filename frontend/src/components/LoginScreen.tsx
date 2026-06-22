import { useState } from 'react'
import { useAuth } from '../context/AuthContext'

export function LoginScreen() {
  const { login } = useAuth()
  const [loginName, setLoginName] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!loginName.trim() || !password) return
    setLoading(true)
    setError(null)
    try {
      await login(loginName.trim(), password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка входа')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="district-screen">
      <div className="district-card login-card">
        <h1>Monitor Web CRM</h1>
        <p className="district-hint">Войдите с учётной записью из crm.users</p>

        <form className="login-form" onSubmit={handleSubmit}>
          <label className="district-field">
            <span>Логин</span>
            <input
              type="text"
              value={loginName}
              onChange={(e) => setLoginName(e.target.value)}
              autoComplete="username"
              disabled={loading}
              required
            />
          </label>

          <label className="district-field">
            <span>Пароль</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              disabled={loading}
              required
            />
          </label>

          <button type="submit" className="btn primary district-submit" disabled={loading}>
            {loading ? 'Вход…' : 'Войти'}
          </button>
        </form>

        {error && <div className="error-banner">{error}</div>}
      </div>
    </div>
  )
}
