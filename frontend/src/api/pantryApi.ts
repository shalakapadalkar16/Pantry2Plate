// single place where all pantry-related HTTP calls live.
// Every function here talks to one specific backend endpoint. 
// Your store and components will call these functions — they never call client directly. 
// This keeps your API logic in one place, so if an endpoint URL changes, you fix it here and nowhere else.

import { apiClient as client } from "./client";

import type {
  PantryItem,
  PantryItemCreatePayload,
  PantryItemUpdatePayload,
  IngredientLog,
} from "../types";

// Fetches all pantry items belonging to the logged-in user
export const getPantryItems = () =>
  client.get<PantryItem[]>("/api/v1/pantry/");

// Sends a new ingredient to the backend; returns the created item
export const createPantryItem = (payload: PantryItemCreatePayload) =>
  client.post<PantryItem>("/api/v1/pantry/", payload);

// Updates quantity/unit/expiry for one item by id; returns the updated item
export const updatePantryItem = (id: string, payload: PantryItemUpdatePayload) =>
  client.patch<PantryItem>(`/api/v1/pantry/${id}/`, payload);

// Deletes one item by id; backend returns 204 so no response body
export const deletePantryItem = (id: string) =>
  client.delete(`/api/v1/pantry/${id}/`);

// Fetches paginated audit logs of all add/remove/update actions
export const getLogs = (page = 1) =>
  client.get<{ results: IngredientLog[]; count: number }>(
    `/api/v1/pantry/logs/?page=${page}`
  );