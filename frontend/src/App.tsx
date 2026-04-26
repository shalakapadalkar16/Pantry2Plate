import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useAuthStore } from './store/authStore'
import { LoginPage, RegisterPage } from './pages/AuthPages'

// ── Protected route guard ─────────────────────────────────────────────────────
// If the user is not authenticated, redirect to /login
// Otherwise render whatever is inside it
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

// ── Placeholder for pages we build in later sprints ───────────────────────────
function PantryPage() {
  return <div className="p-8 text-stone-700">🥦 Pantry page — coming in Sprint 2</div>
}

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const { isAuthenticated, loadProfile } = useAuthStore()

  // On app load, if a token exists, fetch the user profile
  useEffect(() => {
    if (isAuthenticated) loadProfile()
  }, [isAuthenticated, loadProfile])

  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes — anyone can access */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Protected routes — must be logged in */}
        <Route
          path="/pantry"
          element={
            <RequireAuth>
              <PantryPage />
            </RequireAuth>
          }
        />

        {/* Default — redirect root to pantry */}
        <Route path="*" element={<Navigate to="/pantry" replace />} />
      </Routes>
    </BrowserRouter>
  )
}