import { useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import SignInModal from './components/SignInModal'
import HomePage from './components/HomePage'
import Dashboard from './components/Dashboard'
import VintageExplorer from './components/VintageExplorer/VintageExplorer'
import GarmentClassifier from './components/GarmentClassifier/GarmentClassifier'

function AppShell() {
  const location = useLocation()
  const [mode, setMode] = useState(location.state?.mode || 'home')
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

function AppWithModal() {
  const { signInOpen, signInMessage, closeSignIn } = useAuth()
  return (
    <>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<AppShell />} />
      </Routes>
      {signInOpen && <SignInModal onClose={closeSignIn} message={signInMessage} />}
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppWithModal />
    </AuthProvider>
  )
}
