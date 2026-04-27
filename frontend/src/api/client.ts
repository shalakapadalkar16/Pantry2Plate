// Every single API call in the app goes through this.

import axios from 'axios'

// One shared axios instance — all API files import from here, never from 'axios' directly
export const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor ───────────────────────────────────────────────────────
// Runs before every request is sent.
// Grabs the access token from localStorage and attaches it to the header.
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor ──────────────────────────────────────────────────────
// Runs after every response comes back.
// If the server says 401 (token expired), we silently get a new token
// using the refresh token, then retry the original request.
apiClient.interceptors.response.use(
  (response) => response, // success — just pass it through
  async (error) => {
    const original = error.config

    // If it's a 401 and we haven't already retried this request
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true

      const refresh = localStorage.getItem('refresh_token')
      if (!refresh) {
        // No refresh token — user must log in again
        localStorage.clear()
        window.location.href = '/login'
        return Promise.reject(error)
      }

      try {
        // Ask Django for a new access token
        const { data } = await axios.post('/api/v1/auth/token/refresh/', {
          refresh,
        })
        // Save the new access token
        localStorage.setItem('access_token', data.access)
        // Retry the original request with the new token
        original.headers.Authorization = `Bearer ${data.access}`
        return apiClient(original)
      } catch {
        // Refresh token also expired — force logout
        localStorage.clear()
        window.location.href = '/login'
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  }
)