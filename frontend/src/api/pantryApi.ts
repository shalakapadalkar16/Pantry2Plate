// Every pantry-related HTTP call lives here. Stores and components call
// these functions, never apiClient directly, so an endpoint change is a
// one-file edit.
//
// Paths are relative to the client's baseURL of '/api/v1'. They previously
// repeated that prefix, which resolved to /api/v1/api/v1/pantry/ and 404'd
// on every call.

import { apiClient as client } from './client'

import type {
  IngredientLog,
  Paginated,
  PantryItem,
  PantryItemCreatePayload,
  PantryItemUpdatePayload,
} from '../types'

// The list endpoint is paginated. page_size is raised because the pantry is
// filtered client-side and a partial list would filter incorrectly - the
// user would type "onion" and see nothing because their onion is on page 2.
export const getPantryItems = (pageSize = 100) =>
  client.get<Paginated<PantryItem>>(`/pantry/?page_size=${pageSize}`)

export const createPantryItem = (payload: PantryItemCreatePayload) =>
  client.post<PantryItem>('/pantry/', payload)

export const updatePantryItem = (
  id: number,
  payload: PantryItemUpdatePayload
) => client.patch<PantryItem>(`/pantry/${id}/`, payload)

// Returns 204 with no body.
export const deletePantryItem = (id: number) => client.delete(`/pantry/${id}/`)

export const getLogs = (page = 1) =>
  client.get<Paginated<IngredientLog>>(`/pantry/logs/?page=${page}`)

// Items approaching expiry. Not wired into the UI yet, but the endpoint
// exists and this is where it belongs.
export const getExpiringItems = (days = 7) =>
  client.get<Paginated<PantryItem>>(`/pantry/expiring/?days=${days}`)