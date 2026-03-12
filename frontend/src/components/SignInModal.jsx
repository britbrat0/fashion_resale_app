import { useState, useEffect } from 'react'
import { useAuth } from '../hooks/useAuth'
import './SignInModal.css'

export default function SignInModal({ onClose, message }) {
  const { login, register } = useAuth()
  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (isRegister) {
        await register(email, password)
      } else {
        await login(email, password)
      }
      onClose()
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="sim-overlay" onClick={onClose}>
      <div className="sim-card" onClick={e => e.stopPropagation()}>
        <button className="sim-close" onClick={onClose} type="button" aria-label="Close">✕</button>

        {message && <p className="sim-message">{message}</p>}

        <div className="sim-tabs">
          <button
            className={`sim-tab${!isRegister ? ' active' : ''}`}
            onClick={() => { setIsRegister(false); setError('') }}
            type="button"
          >Sign In</button>
          <button
            className={`sim-tab${isRegister ? ' active' : ''}`}
            onClick={() => { setIsRegister(true); setError('') }}
            type="button"
          >Create Account</button>
        </div>

        <form onSubmit={handleSubmit} className="sim-form">
          <div className="sim-field">
            <label htmlFor="sim-email">Email</label>
            <input
              id="sim-email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoFocus
            />
          </div>
          <div className="sim-field">
            <label htmlFor="sim-password">Password</label>
            <input
              id="sim-password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Enter password"
              required
              minLength={6}
            />
          </div>
          {error && <div className="sim-error">{error}</div>}
          <button type="submit" className="sim-submit" disabled={loading}>
            {loading ? 'Please wait…' : isRegister ? 'Create Account' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
