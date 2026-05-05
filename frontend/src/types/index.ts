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

// the shape of one ingredient row that the backend sends back
export interface PantryItem {
  id: string;
  ingredient_name: string;
  quantity: number;
  unit: string;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

// what your frontend sends to the backend when adding a new item
export interface PantryItemCreatePayload {
  ingredient_name: string;
  quantity: number;
  unit?: string;
  expires_at?: string;
}

// what you send on edit. ingredient_name is not here because you can't rename an ingredient, only change its quantity/unit/expiry
export interface PantryItemUpdatePayload {
  quantity: number;
  unit?: string;
  expires_at?: string;
}

// shape of one audit log row
export interface IngredientLog {
  id: string;
  ingredient_name: string;
  action: "ADD" | "REMOVE" | "UPDATE";
  quantity_change: number;
  unit: string;
  created_at: string;
}