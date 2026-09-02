// ── Shared ────────────────────────────────────────────────────────────────────

// Every list endpoint in the API is paginated and returns this envelope.
// Getting this wrong was a real bug: getPantryItems was typed as
// PantryItem[], so `items` became an object and .filter() threw.
export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// Standard error shape from core/exceptions.py. `fields` carries per-field
// validation detail so a form can attach messages to the right input.
export interface ApiError {
  error: {
    message: string
    code: string
    status_code: number
    fields: Record<string, string[]> | null
  }
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface User {
  id: number
  email: string
  first_name: string
  last_name: string
  created_at: string
}

export interface AuthTokens {
  access: string
  refresh: string
}

export interface RegisterPayload {
  email: string
  first_name: string
  last_name: string
  password: string
}

export interface LoginPayload {
  email: string
  password: string
}

// ── Ingredients ───────────────────────────────────────────────────────────────

// Canonical ingredient the backend resolved a free-text string to. Null on a
// pantry item means the matcher could not identify what the user typed.
export interface IngredientBrief {
  id: number
  canonical_name: string
  display_name: string
  category: string
  // Staples (salt, oil, pepper) are assumed present in every kitchen and
  // never counted as missing from a recipe.
  is_staple: boolean
}

// ── Pantry ────────────────────────────────────────────────────────────────────

export interface PantryItem {
  id: number
  // Null when unresolved. The item is still stored and shown, it just never
  // matches a recipe.
  ingredient: IngredientBrief | null
  // Exactly what the user typed.
  raw_input: string
  // ingredient.display_name when resolved, raw_input otherwise.
  display_name: string
  is_resolved: boolean
  // A string, not a number: DRF serializes DecimalField as a string unless
  // COERCE_DECIMAL_TO_STRING is disabled. Parse before doing arithmetic.
  quantity: string
  unit: string
  expiry_date: string | null
  created_at: string
  updated_at: string
}

export interface PantryItemCreatePayload {
  // Free text. The backend resolves it to an Ingredient; the client does
  // not need to know the vocabulary.
  raw_input: string
  quantity: number
  unit?: string
  expiry_date?: string | null
}

// All fields optional — the endpoint is a real PATCH.
export interface PantryItemUpdatePayload {
  quantity?: number
  unit?: string
  expiry_date?: string | null
}

export type LogAction = 'ADDED' | 'REMOVED' | 'UPDATED'

export interface IngredientLog {
  id: number
  ingredient: IngredientBrief | null
  // Kept verbatim from the time of writing — the log is a historical
  // record, so it does not follow later vocabulary changes.
  ingredient_name: string
  action: LogAction
  quantity: string
  unit: string
  created_at: string
}

// ── Recipes ───────────────────────────────────────────────────────────────────

export interface RecipeSummary {
  id: number
  external_id: string
  name: string
  minutes: number | null
  n_ingredients: number
  // Non-staple ingredient count. This is the coverage denominator.
  n_required: number
  // Ingredients the matcher could not identify. These can never be
  // satisfied by a pantry.
  n_unresolved: number
  tags: string[]
  calories: number | null
}

export interface RecipeMatch {
  recipe: RecipeSummary
  have: number
  missing: number
  coverage: number
  // Known ingredients the pantry lacks — these can go on a shopping list.
  missing_ingredients: string[]
  // Ingredients the backend could not identify. Reported separately
  // because "you need butter" and "we could not read this" are different
  // messages, even though both count against coverage.
  unknown_ingredients: string[]
}

export interface RecommendationResponse {
  count: number
  next: string | null
  previous: string | null
  pantry_size: number
  moods_applied: string[]
  backend?: 'sql' | 'es'
  cached?: boolean
  results: RecipeMatch[]
  // Present only when the pantry is empty, so the UI can prompt for
  // ingredients rather than suggesting looser filters.
  detail?: string
}

export interface Mood {
  key: string
  label: string
  description: string
  tags: string[]
}

export type IngredientState = 'have' | 'missing' | 'unknown' | 'staple'

export interface RecipeDetailIngredient {
  raw_text: string
  display_name: string
  state: IngredientState
}

export interface RecipeDetail {
  id: number
  name: string
  description: string
  minutes: number | null
  tags: string[]
  calories: number | null
  // Positional list from the source dataset:
  // [calories, fat_pdv, sugar_pdv, sodium_pdv, protein_pdv, sat_fat_pdv, carbs_pdv]
  nutrition: number[]
  steps: string[]
  ingredients: RecipeDetailIngredient[]
  summary: {
    n_required: number
    have: number
    missing: number
    unknown: number
  }
}

// ── Recipe book ───────────────────────────────────────────────────────────────

export interface SavedRecipeCard {
  id: number
  name: string
  minutes: number | null
  n_ingredients: number
  n_required: number
  tags: string[]
}

export interface SavedRecipe {
  id: number
  recipe: SavedRecipeCard
  notes: string
  created_at: string
  updated_at: string
}

// ── Search parameters ─────────────────────────────────────────────────────────

export interface SearchParams {
  // How many ingredients the user is willing to buy. 0 means "only what I
  // can cook right now".
  max_missing: number
  // Floor on recipe size. A two-ingredient recipe scores perfectly and
  // recommends nothing, which is why the backend default is 3.
  min_required?: number
  max_minutes?: number | null
  moods: string[]
  order: 'best' | 'quickest' | 'simplest'
  limit: number
  offset: number
}