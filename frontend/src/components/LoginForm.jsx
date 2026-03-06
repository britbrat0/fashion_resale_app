import { useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import './LoginForm.css'

export default function LoginForm() {
  const { login, register } = useAuth()
  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

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
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="nav-logo-wrap" style={{margin: '0 auto 0.75rem'}}>
          <img src="/resale-rat-logo.png" alt="Resale Rat" className="nav-logo" style={{height: '40px'}} />
        </div>
        <p className="login-subtitle">
          Detect and predict fashion resale trend cycles
        </p>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              required
              minLength={6}
            />
          </div>

          {error && <div className="error-message">{error}</div>}

          <button type="submit" className="submit-btn" disabled={loading}>
            {loading ? 'Please wait...' : isRegister ? 'Create Account' : 'Sign In'}
          </button>
        </form>

        <button
          className="toggle-btn"
          onClick={() => {
            setIsRegister(!isRegister)
            setError('')
          }}
        >
          {isRegister
            ? 'Already have an account? Sign in'
            : "Don't have an account? Create one"}
        </button>
      </div>
    </div>
  )
}
