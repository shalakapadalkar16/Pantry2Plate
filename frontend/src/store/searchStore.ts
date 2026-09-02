// Recipe search state.
//
// The filters here fire a request on every change, and a threshold slider
// produces several in a fraction of a second. Two things guard against that:
// the page debounces filter changes, and this store discards responses that
// arrive out of order.

import axios from 'axios'
import { create } from 'zustand'

import {
  getMoods,
  getRecommendations,
  getSavedRecipeIds,
  saveRecipe,
  unsaveRecipe,
} from '../api/recipeApi'
import type {
  ApiError,
  Mood,
  RecipeMatch,
  SearchParams,
} from '../types'

export const PAGE_SIZE = 12

const DEFAULT_PARAMS: SearchParams = {
  // Zero means "only what I can cook right now". Raising it is the user
  // saying they will buy something.
  max_missing: 0,
  // A two-ingredient recipe scores perfectly and recommends nothing.
  min_required: 3,
  max_minutes: null,
  moods: [],
  order: 'best',
  limit: PAGE_SIZE,
  offset: 0,
}

function messageFrom(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiError | undefined
    if (body?.error?.message) return body.error.message
  }
  return fallback
}

// Monotonic request counter, module-level rather than in state so updating
// it never triggers a re-render.
//
// Without this, dragging the slider from 0 to 3 fires four requests and
// whichever the server happens to finish last wins - which is not
// necessarily the one matching the current filters. The symptom is results
// that do not match the controls, intermittently, and only under fast
// input.
let requestSeq = 0

interface SearchState {
  results: RecipeMatch[]
  count: number
  pantrySize: number
  // Echoed by the API. Surfaced in the UI because it makes the caching and
  // backend selection observable instead of a claim.
  backend?: 'sql' | 'es'
  cached?: boolean
  detail?: string

  moods: Mood[]
  savedIds: Set<number>

  params: SearchParams
  loading: boolean
  error: string | null

  search: () => Promise<void>
  loadMoods: () => Promise<void>
  loadSavedIds: () => Promise<void>
  toggleSaved: (recipeId: number) => Promise<void>

  setParam: <K extends keyof SearchParams>(
    key: K,
    value: SearchParams[K]
  ) => void
  toggleMood: (key: string) => void
  setOffset: (offset: number) => void
  reset: () => void
}

export const useSearchStore = create<SearchState>((set, get) => ({
  results: [],
  count: 0,
  pantrySize: 0,
  moods: [],
  savedIds: new Set(),
  params: DEFAULT_PARAMS,
  loading: false,
  error: null,

  search: async () => {
    const seq = ++requestSeq
    set({ loading: true, error: null })

    try {
      const res = await getRecommendations(get().params)
      // A newer request has been issued since this one left; its answer is
      // the correct one, so drop this response entirely.
      if (seq !== requestSeq) return

      set({
        results: res.data.results,
        count: res.data.count,
        pantrySize: res.data.pantry_size,
        backend: res.data.backend,
        cached: res.data.cached,
        detail: res.data.detail,
      })
    } catch (error) {
      if (seq !== requestSeq) return
      set({ error: messageFrom(error, 'Search failed. Please try again.') })
    } finally {
      // Only the latest request may clear the spinner, or an early response
      // would hide loading while a newer request is still in flight.
      if (seq === requestSeq) set({ loading: false })
    }
  },

  loadMoods: async () => {
    if (get().moods.length) return
    try {
      const res = await getMoods()
      set({ moods: res.data.moods })
    } catch {
      // A missing mood list degrades the page rather than breaking it, so
      // this failure is not surfaced.
    }
  },

  loadSavedIds: async () => {
    try {
      const res = await getSavedRecipeIds()
      set({ savedIds: new Set(res.data.recipe_ids) })
    } catch {
      // Same reasoning: without this the save buttons just show unsaved.
    }
  },

  toggleSaved: async (recipeId) => {
    const saved = get().savedIds.has(recipeId)

    // Optimistic. Sets are copied rather than mutated so Zustand sees a new
    // reference and re-renders.
    const next = new Set(get().savedIds)
    if (saved) next.delete(recipeId)
    else next.add(recipeId)
    set({ savedIds: next })

    try {
      if (saved) await unsaveRecipe(recipeId)
      else await saveRecipe(recipeId)
    } catch (error) {
      const reverted = new Set(get().savedIds)
      if (saved) reverted.add(recipeId)
      else reverted.delete(recipeId)
      set({
        savedIds: reverted,
        error: messageFrom(error, 'Could not update your recipe book.'),
      })
    }
  },

  // Any filter change returns to the first page. Staying on page 5 of a
  // result set that just shrank to two pages shows an empty screen.
  setParam: (key, value) =>
    set((state) => ({
      params: { ...state.params, [key]: value, offset: 0 },
    })),

  toggleMood: (key) =>
    set((state) => {
      const active = state.params.moods.includes(key)
      return {
        params: {
          ...state.params,
          moods: active
            ? state.params.moods.filter((m) => m !== key)
            : // The backend rejects more than four moods at once.
              [...state.params.moods, key].slice(0, 4),
          offset: 0,
        },
      }
    }),

  setOffset: (offset) =>
    set((state) => ({ params: { ...state.params, offset } })),

  reset: () => set({ params: DEFAULT_PARAMS }),
}))