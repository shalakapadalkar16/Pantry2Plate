// zustand store for pantry state
// holds the list of pantry items in memory and exposes actions (load, add, update, delete) that call pantryApi.ts under the hood. 
// Components just call store actions — they don't touch the API directly.

import { create } from "zustand";
import type { PantryItem, PantryItemCreatePayload, PantryItemUpdatePayload } from "../types";
import {
  getPantryItems,
  createPantryItem,
  updatePantryItem,
  deletePantryItem,
} from "../api/pantryApi";

interface PantryState {
  items: PantryItem[];
  loading: boolean;
  error: string | null;

  // Actions
  loadItems: () => Promise<void>;
  addItem: (payload: PantryItemCreatePayload) => Promise<void>;
  editItem: (id: string, payload: PantryItemUpdatePayload) => Promise<void>;
  removeItem: (id: string) => Promise<void>;
}

export const usePantryStore = create<PantryState>((set, get) => ({
  items: [],
  loading: false,
  error: null,

  // Fetches all pantry items from the backend and stores them
  loadItems: async () => {
    set({ loading: true, error: null });
    try {
      const res = await getPantryItems();
      set({ items: res.data });
    } catch {
      set({ error: "Failed to load pantry items." });
    } finally {
      set({ loading: false });
    }
  },

  // Sends new item to backend, then appends it to the local list
  addItem: async (payload) => {
    const res = await createPantryItem(payload);
    set((state) => ({ items: [...state.items, res.data] }));
  },

  // Sends edits to backend, then swaps the old item with the updated one
  editItem: async (id, payload) => {
    const res = await updatePantryItem(id, payload);
    set((state) => ({
      items: state.items.map((item) => (item.id === id ? res.data : item)),
    }));
  },

  // Optimistic delete — remove immediately, restore if API call fails
  removeItem: async (id) => {
    const previous = get().items;
    set((state) => ({ items: state.items.filter((item) => item.id !== id) }));
    try {
      await deletePantryItem(id);
    } catch {
      set({ items: previous, error: "Failed to delete item." });
    }
  },
}));