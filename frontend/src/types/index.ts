// ── Auth ──────────────────────────────────────────────────────────────────────

// shape of a logged-in user object that comes back from Django
export interface User {
  id: string
  email: string
  username: string
  timezone: string
  date_joined: string
}

// what Django returns when you log in: two tokens - access (short-lived) and refresh (long-lived)
export interface AuthTokens {
  access: string
  refresh: string
}

// what we send to Django when someone registers
export interface RegisterPayload {
  email: string
  username: string
  password: string
}

// what we send to Django when someone logs in
export interface LoginPayload {
  email: string
  password: string
}