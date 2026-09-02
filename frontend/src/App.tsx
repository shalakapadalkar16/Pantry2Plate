import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useAuthStore } from './store/authStore'
import { LoginPage, RegisterPage } from './pages/AuthPages'
import PantryPage from './pages/PantryPage'
import AuditLogPage from './pages/AuditLogPage'
import Layout from './components/layout/Layout'
import SearchPage from './pages/SearchPage'
import RecipeDetailPage from './pages/RecipeDetailPage'
import SavedRecipesPage from './pages/SavedRecipesPage'
// If the user is not authenticated, redirect to /login
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

// If the user IS authenticated, redirect away from login/register
function RedirectIfAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (isAuthenticated) return <Navigate to="/pantry" replace />
  return <>{children}</>
}

export default function App() {
  const { isAuthenticated, loadProfile } = useAuthStore()

  // On app load, if a token exists, fetch the user profile
  useEffect(() => {
    if (isAuthenticated) loadProfile()
  }, [isAuthenticated, loadProfile])

  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={
          <RedirectIfAuth><LoginPage /></RedirectIfAuth>
        } />
        <Route path="/register" element={
          <RedirectIfAuth><RegisterPage /></RedirectIfAuth>
        } />

        {/* Protected routes — Layout wraps all of them, RequireAuth guards the parent */}
        <Route element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }>
          <Route path="/pantry" element={<PantryPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/logs" element={<AuditLogPage />} />
          <Route path="/saved" element={<SavedRecipesPage />} />
          <Route path="/recipes/:id" element={<RecipeDetailPage/>} />
        </Route>

        {/* Default — redirect root to pantry */}
        <Route path="*" element={<Navigate to="/pantry" replace />} />
      </Routes>
    </BrowserRouter>
  )
}