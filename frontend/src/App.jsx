import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import LoginForm from './components/LoginForm'
import Dashboard from './components/Dashboard'
import VintageExplorer from './components/VintageExplorer/VintageExplorer'
import GarmentClassifier from './components/GarmentClassifier/GarmentClassifier'

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? children : <Navigate to="/" replace />
}

function PublicRoute({ children }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <Navigate to="/dashboard" replace /> : children
}

function AppShell() {
  const [mode, setMode] = useState('dashboard')
  const [initialEraId, setInitialEraId] = useState(null)

  if (mode === 'vintage') {
    return (
      <VintageExplorer
        initialEraId={initialEraId}
        onSwitchToDashboard={() => setMode('dashboard')}
        onSwitchToClassify={() => setMode('classify')}
      />
    )
  }

  if (mode === 'classify') {
    return (
      <GarmentClassifier
        onSwitchToDashboard={() => setMode('dashboard')}
        onSwitchToVintage={() => { setInitialEraId(null); setMode('vintage') }}
        onExploreEra={(id) => { setInitialEraId(id); setMode('vintage') }}
      />
    )
  }

  return <Dashboard onSwitchToVintage={() => { setInitialEraId(null); setMode('classify') }} />
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route
          path="/"
          element={
            <PublicRoute>
              <LoginForm />
            </PublicRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        />
      </Routes>
    </AuthProvider>
  )
}
