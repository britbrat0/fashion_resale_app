import { createContext, useContext, useState, useEffect } from 'react'
import api from '../services/api'

const AuthContext = createContext(null)

function decodeEmail(token) {
  try {
    return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))?.sub || null
  } catch { return null }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(localStorage.getItem('token'))
  const [signInOpen, setSignInOpen] = useState(false)
  const [signInMessage, setSignInMessage] = useState(null)
  const email = token ? decodeEmail(token) : null

  // When an authenticated user's token expires mid-session, clear it
  useEffect(() => {
    const handler = () => setToken(null)
    window.addEventListener('auth:token-expired', handler)
    return () => window.removeEventListener('auth:token-expired', handler)
  }, [])

  const login = async (emailVal, password) => {
    const res = await api.post('/auth/login', { email: emailVal, password })
    const t = res.data.access_token
    localStorage.setItem('token', t)
    setToken(t)
    return t
  }

  const register = async (emailVal, password) => {
    const res = await api.post('/auth/register', { email: emailVal, password })
    const t = res.data.access_token
    localStorage.setItem('token', t)
    setToken(t)
    return t
  }

  const logout = () => {
    localStorage.removeItem('token')
    setToken(null)
  }

  const openSignIn = (msg = null) => { setSignInMessage(typeof msg === 'string' ? msg : null); setSignInOpen(true) }
  const closeSignIn = () => { setSignInOpen(false); setSignInMessage(null) }

  const isAuthenticated = !!token

  return (
    <AuthContext.Provider value={{ token, email, login, register, logout, isAuthenticated, signInOpen, signInMessage, openSignIn, closeSignIn }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
