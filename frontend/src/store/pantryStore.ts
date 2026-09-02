// Pantry state. Holds the item list in memory and exposes actions that call
// pantryApi under the hood. Components call store actions, never the API.

import axios from 'axios'
import { create } from 'zustand'

import {
  createPantryItem,
  deletePantryItem,
  getPantryItems,
  updatePantryItem,
} from '../api/pantryApi'
import type {
  ApiError,
  PantryItem,
  PantryItemCreatePayload,
  PantryItemUpdatePayload,
} from '../types'

// Pulls the server's message out of the standard error envelope. Without
// this every failure surfaced as "Something went wrong", which hid real
// causes - a rejected unit or a duplicate ingredient both looked identical.
function messageFrom(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiError | undefined
    if (body?.error?.message) return body.error.message
  }
  return fallback
}

interface PantryState {
  items: PantryItem[]
  loading: boolean
  error: string | null

  loadItems: () => Promise<void>
  addItem: (payload: PantryItemCreatePayload) => Promise<void>
  editItem: (id: number, payload: PantryItemUpdatePayload) => Promise<void>
  removeItem: (id: number) => Promise<void>
  clearError: () => void
}

export const usePantryStore = create<PantryState>((set, get) => ({
  items: [],
  loading: false,
  error: null,

  loadItems: async () => {
    set({ loading: true, error: null })
    try {
      const res = await getPantryItems()
      // res.data is a pagination envelope, not an array.
      set({ items: res.data.results })
    } catch (error) {
      set({ error: messageFrom(error, 'Failed to load pantry items.') })
    } finally {
      set({ loading: false })
    }
  },

  addItem: async (payload) => {
    const res = await createPantryItem(payload)
    set((state) => ({ items: [...state.items, res.data], error: null }))
  },

  editItem: async (id, payload) => {
    const res = await updatePantryItem(id, payload)
    set((state) => ({
      items: state.items.map((item) => (item.id === id ? res.data : item)),
      error: null,
    }))
  },

  // Optimistic: remove immediately, restore if the call fails.
  removeItem: async (id) => {
    const previous = get().items
    set((state) => ({ items: state.items.filter((item) => item.id !== id) }))
    try {
      await deletePantryItem(id)
    } catch (error) {
      set({ items: previous, error: messageFrom(error, 'Failed to delete item.') })
    }
  },

  clearError: () => set({ error: null }),
}))