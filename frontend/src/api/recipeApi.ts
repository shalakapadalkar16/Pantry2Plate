// Recipe search and recipe book calls.
//
// Paths are relative to the client's baseURL of '/api/v1'.

import { apiClient as client } from './client'

import type {
  Mood,
  Paginated,
  RecipeDetail,
  RecommendationResponse,
  SavedRecipe,
  SearchParams,
} from '../types'

// Builds the query string, dropping anything unset.
//
// Sending `max_minutes=` or `mood=` as empty strings would fail the
// backend's serializer validation rather than being ignored, so absent has
// to mean absent.
function toQuery(params: SearchParams): string {
  const search = new URLSearchParams()

  search.set('max_missing', String(params.max_missing))
  search.set('limit', String(params.limit))
  search.set('offset', String(params.offset))
  search.set('order', params.order)

  if (params.min_required != null) {
    search.set('min_required', String(params.min_required))
  }
  if (params.max_minutes) {
    search.set('max_minutes', String(params.max_minutes))
  }
  // Moods are AND-ed server-side: a recipe must match every mood, while
  // tags within one mood are OR-ed.
  if (params.moods.length) {
    search.set('mood', params.moods.join(','))
  }

  return search.toString()
}

export const getRecommendations = (params: SearchParams) =>
  client.get<RecommendationResponse>(`/recommendations/?${toQuery(params)}`)

// Public endpoint — no auth needed, so the client can render filter options
// before login.
export const getMoods = () =>
  client.get<{ moods: Mood[] }>('/recommendations/moods/')

export const getRecipeDetail = (id: number) =>
  client.get<RecipeDetail>(`/recommendations/recipes/${id}/`)

// ── Recipe book ───────────────────────────────────────────────────────────────

export const getSavedRecipes = (page = 1) =>
  client.get<Paginated<SavedRecipe>>(`/recipes/saved/?page=${page}`)

// Returns ids only. This exists so search results can be marked as saved
// without an is_saved flag going into the recommendation response, which is
// cached on a key that accounts for the pantry and query but not for
// per-user state.
export const getSavedRecipeIds = () =>
  client.get<{ count: number; recipe_ids: number[] }>('/recipes/saved/ids/')

export const saveRecipe = (recipeId: number, notes = '') =>
  client.post<SavedRecipe>('/recipes/saved/', { recipe_id: recipeId, notes })

// Addressed by recipe id, not SavedRecipe id — the client already has the
// recipe id from the card it rendered.
export const updateSavedNotes = (recipeId: number, notes: string) =>
  client.patch<SavedRecipe>(`/recipes/saved/${recipeId}/`, { notes })

export const unsaveRecipe = (recipeId: number) =>
  client.delete(`/recipes/saved/${recipeId}/`)