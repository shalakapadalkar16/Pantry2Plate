import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

// ── Shared wrapper ────────────────────────────────────────────────────────────
function AuthShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-stone-50 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-amber-600">🍽 Pantry to Plate</h1>
          <p className="text-stone-500 mt-2 text-sm">{title}</p>
        </div>
        <div className="bg-white rounded-xl border border-stone-200 p-6 shadow-sm">
          {children}
        </div>
      </div>
    </div>
  )
}

// ── Login Page ────────────────────────────────────────────────────────────────
export function LoginPage() {
  const { login, isLoading, error, clearError } = useAuthStore()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await login(form)
    // Only navigate if login succeeded (no error in store)
    if (!useAuthStore.getState().error) {
      navigate('/pantry')
    }
  }

  return (
    <AuthShell title="Sign in to your account">
      <form onSubmit={handleSubmit} className="space-y-4">

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg flex justify-between">
            <span>{error}</span>
            <button onClick={clearError} className="text-red-400 hover:text-red-600">✕</button>
          </div>
        )}

        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Email</label>
          <input
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            type="email"
            placeholder="you@example.com"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            required
            autoFocus
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Password</label>
          <input
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            type="password"
            placeholder="••••••••"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            required
          />
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium py-2 rounded-lg disabled:opacity-50 transition-colors"
        >
          {isLoading ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="text-center text-sm text-stone-500">
          No account?{' '}
          <Link to="/register" className="text-amber-600 hover:underline">Register</Link>
        </p>

      </form>
    </AuthShell>
  )
}

// ── Register Page ─────────────────────────────────────────────────────────────
export function RegisterPage() {
  const { register, isLoading, error, clearError } = useAuthStore()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', username: '', password: '' })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await register(form)
    if (!useAuthStore.getState().error) {
      navigate('/pantry')
    }
  }

  return (
    <AuthShell title="Create your account">
      <form onSubmit={handleSubmit} className="space-y-4">

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg flex justify-between">
            <span>{error}</span>
            <button onClick={clearError} className="text-red-400 hover:text-red-600">✕</button>
          </div>
        )}

        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Email</label>
          <input
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            type="email"
            placeholder="you@example.com"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            required
            autoFocus
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Username</label>
          <input
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            placeholder="chef_shalaka"
            value={form.username}
            onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
            required
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1">Password</label>
          <input
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            type="password"
            placeholder="8+ characters"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            minLength={8}
            required
          />
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium py-2 rounded-lg disabled:opacity-50 transition-colors"
        >
          {isLoading ? 'Creating account…' : 'Create account'}
        </button>

        <p className="text-center text-sm text-stone-500">
          Already have an account?{' '}
          <Link to="/login" className="text-amber-600 hover:underline">Sign in</Link>
        </p>

      </form>
    </AuthShell>
  )
}