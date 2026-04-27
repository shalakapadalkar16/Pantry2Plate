// global state for authentication. Using Zustand
// Any component in the app can read from this store — whether the user is logged in, who they are, loading state, errors.

import { create } from 'zustand'
import type { User, LoginPayload, RegisterPayload } from '../types'
import { authApi } from '../api/authApi'

// This describes the shape of our auth state + the actions to change it
interface AuthState {
  user: User | null           // null means not logged in
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  login: (payload: LoginPayload) => Promise<void>
  register: (payload: RegisterPayload) => Promise<void>
  logout: () => void
  loadProfile: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  // ── Initial state ───────────────────────────────────────────────────────────
  user: null,
  // If a token already exists in localStorage, user is considered authenticated
  isAuthenticated: !!localStorage.getItem('access_token'),
  isLoading: false,
  error: null,

  // ── Actions ─────────────────────────────────────────────────────────────────

  login: async (payload) => {
    set({ isLoading: true, error: null })
    try {
      // Step 1: get tokens from Django
      const tokens = await authApi.login(payload)
      localStorage.setItem('access_token', tokens.access)
      localStorage.setItem('refresh_token', tokens.refresh)
      // Step 2: use the token to fetch the user profile
      const user = await authApi.getProfile()
      set({ user, isAuthenticated: true, isLoading: false })
    } catch {
      set({ error: 'Invalid email or password.', isLoading: false })
    }
  },

  register: async (payload) => {
    set({ isLoading: true, error: null })
    try {
      // Step 1: create the account
      await authApi.register(payload)
      // Step 2: immediately log in with the same credentials
      const tokens = await authApi.login({
        email: payload.email,
        password: payload.password,
      })
      localStorage.setItem('access_token', tokens.access)
      localStorage.setItem('refresh_token', tokens.refresh)
      // Step 3: fetch the user profile
      const user = await authApi.getProfile()
      set({ user, isAuthenticated: true, isLoading: false })
    } catch {
      set({ error: 'Registration failed. Email may already be in use.', isLoading: false })
    }
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    set({ user: null, isAuthenticated: false })
  },

  loadProfile: async () => {
    try {
      const user = await authApi.getProfile()
      set({ user })
    } catch {
      // Token invalid or expired — clear everything
      localStorage.clear()
      set({ user: null, isAuthenticated: false })
    }
  },

  clearError: () => set({ error: null }),
}))