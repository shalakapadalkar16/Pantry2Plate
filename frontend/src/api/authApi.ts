// contains all the functions that talk to Django's auth endpoints. It uses apiClient from client.ts

import { apiClient } from './client' // apiClient is the Axios instance created 
import type { User, AuthTokens, RegisterPayload, LoginPayload } from '../types'

export const authApi = {

    // sends { email, username, password } to Django, gets back the created User
  register: (payload: RegisterPayload) =>
    apiClient.post<User>('/auth/register/', payload).then((r) => r.data),

  // sends { email, password } to Django, gets back { access, refresh } tokens
  login: (payload: LoginPayload) =>
    apiClient.post<AuthTokens>('/auth/login/', payload).then((r) => r.data),

  // sends a GET request (with the token automatically attached by client.ts), gets back the logged-in User
  getProfile: () =>
    apiClient.get<User>('/auth/profile/').then((r) => r.data),

}