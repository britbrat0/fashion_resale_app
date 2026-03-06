import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import LandingPage from './components/LandingPage'
import HomePage from './components/HomePage'
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
  const [mode, setMode] = useState('home')
  const [initialEraId, setInitialEraId] = useState(null)

  const goHome = () => setMode('home')

  if (mode === 'home') {
    return (
      <HomePage
        onGoToDashboard={() => setMode('dashboard')}
        onGoToVintage={() => { setInitialEraId(null); setMode('classify') }}
      />
    )
  }

  if (mode === 'vintage') {
    return (
      <VintageExplorer
        initialEraId={initialEraId}
        onGoHome={goHome}
        onSwitchToDashboard={() => setMode('dashboard')}
        onSwitchToClassify={() => setMode('classify')}
      />
    )
  }

  if (mode === 'classify') {
    return (
      <GarmentClassifier
        onGoHome={goHome}
        onSwitchToDashboard={() => setMode('dashboard')}
        onSwitchToVintage={() => { setInitialEraId(null); setMode('vintage') }}
        onExploreEra={(id) => { setInitialEraId(id); setMode('vintage') }}
      />
    )
  }

  return <Dashboard onGoHome={goHome} onSwitchToVintage={() => { setInitialEraId(null); setMode('classify') }} />
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route
          path="/"
          element={
            <PublicRoute>
              <LandingPage />
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
