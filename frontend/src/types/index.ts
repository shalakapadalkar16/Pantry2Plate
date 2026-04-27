// ── Auth ──────────────────────────────────────────────────────────────────────

// shape of a logged-in user object that comes back from Django
export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  created_at: string
}

// what Django returns when you log in: two tokens - access (short-lived) and refresh (long-lived)
export interface AuthTokens {
  access: string
  refresh: string
}

// what we send to Django when someone registers
export interface RegisterPayload {
  email: string
  first_name: string
  last_name: string
  password: string
}

// what we send to Django when someone logs in
export interface LoginPayload {
  email: string
  password: string
}