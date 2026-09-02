// Recipe search.
//
// One ranked list sorted by how many ingredients are missing, with a
// threshold the user controls. "Only what I have" is the threshold at zero,
// not a separate mode.

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { titleCase } from '../utils/text'
import { PAGE_SIZE, useSearchStore } from '../store/searchStore'
import { EmptyState, ErrorBanner, PageHeader, Spinner } from '../components/ui'
import type { RecipeMatch } from '../types'

// Filter changes are debounced. Dragging the slider across four positions
// would otherwise fire four searches, three of them already stale by the
// time they return.
const DEBOUNCE_MS = 250

const TIME_OPTIONS = [
  { label: 'Any time', value: null },
  { label: 'Under 15 min', value: 15 },
  { label: 'Under 30 min', value: 30 },
  { label: 'Under 1 hour', value: 60 },
]

const ORDER_OPTIONS = [
  { label: 'Best match', value: 'best' as const },
  { label: 'Quickest', value: 'quickest' as const },
  { label: 'Fewest ingredients', value: 'simplest' as const },
]

const THRESHOLD_LABELS = [
  'Only what I have',
  'Buy up to 1 thing',
  'Buy up to 2 things',
  'Buy up to 3 things',
]

// ── Result card ───────────────────────────────────────────────────────────────

function RecipeCard({
  match,
  saved,
  onToggleSave,
}: {
  match: RecipeMatch
  saved: boolean
  onToggleSave: (id: number) => void
}) {
  const { recipe, have, missing, missing_ingredients, unknown_ingredients } =
    match

  return (
    <div className="bg-white rounded-2xl shadow-sm p-5 flex flex-col gap-3 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-3">
        <Link
          to={`/recipes/${recipe.id}`}
          className="font-semibold text-gray-800 hover:text-green-700 leading-snug capitalize"
        >
          {recipe.name}
        </Link>
        <button
          onClick={() => onToggleSave(recipe.id)}
          title={saved ? 'Remove from your book' : 'Save to your book'}
          className={`shrink-0 text-lg leading-none transition-transform hover:scale-110 ${
            saved ? '' : 'opacity-30 hover:opacity-70'
          }`}
        >
          {saved ? '★' : '☆'}
        </button>
      </div>

      <div className="flex items-center gap-2 flex-wrap text-xs">
        {missing === 0 ? (
          <span className="bg-green-100 text-green-700 px-2 py-1 rounded-full font-medium">
            Ready to cook
          </span>
        ) : (
          <span className="bg-amber-100 text-amber-700 px-2 py-1 rounded-full font-medium">
            Need {missing} more
          </span>
        )}
        {/* have out of n_required, not out of n_ingredients: staples are
            assumed present and never counted. */}
        <span className="text-gray-500">
          uses {have} of your {have === 1 ? 'ingredient' : 'ingredients'}
        </span>
        {recipe.minutes ? (
          <span className="text-gray-400">· {recipe.minutes} min</span>
        ) : null}
      </div>

      {missing_ingredients.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {missing_ingredients.slice(0, 5).map((name) => (
            <span
              key={name}
              className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded"
            >
              {name}
            </span>
          ))}
          {missing_ingredients.length > 5 && (
            <span className="text-xs text-gray-400 px-1">
              +{missing_ingredients.length - 5} more
            </span>
          )}
        </div>
      )}

      {/* Kept visually distinct from missing ingredients. "You need butter"
          and "we could not identify this line" are different messages, even
          though both count against coverage. */}
      {unknown_ingredients.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {unknown_ingredients.slice(0, 3).map((text) => (
            <span
              key={text}
              title="We could not identify this ingredient, so it counts as missing"
              className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded italic"
            >
              {text}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SearchPage() {
  const {
    results,
    count,
    pantrySize,
    backend,
    cached,
    detail,
    moods,
    savedIds,
    params,
    loading,
    error,
    search,
    loadMoods,
    loadSavedIds,
    toggleSaved,
    setParam,
    toggleMood,
    setOffset,
  } = useSearchStore()

  const [showAllMoods, setShowAllMoods] = useState(false)

  useEffect(() => {
    loadMoods()
    loadSavedIds()
  }, [loadMoods, loadSavedIds])

  // Debounced on the whole params object, so any filter change is covered
  // by one rule rather than each control managing its own timing.
  useEffect(() => {
    const timer = setTimeout(() => search(), DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [params, search])

  const page = Math.floor(params.offset / PAGE_SIZE) + 1
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))

  // Cuisine and dietary moods are pushed behind a toggle. Twenty-three
  // chips is a wall; the first eight cover most intent.
  const visibleMoods = useMemo(
    () => (showAllMoods ? moods : moods.slice(0, 8)),
    [moods, showAllMoods]
  )

  if (pantrySize === 0 && detail) {
    return (
      <div>
        <PageHeader title="Find Recipes" />
        <EmptyState icon="🧺" message={detail} />
        <div className="flex justify-center">
          <Link
            to="/pantry"
            className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700"
          >
            Go to my pantry
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Find Recipes"
        subtitle={
          pantrySize
            ? `Ranked against the ${pantrySize} ingredients in your pantry`
            : undefined
        }
      />

      <ErrorBanner message={error} />

      {/* ── Filters ── */}
      <div className="bg-white rounded-2xl shadow-sm p-5 mb-6 flex flex-col gap-5">
        <div>
          <div className="flex items-baseline justify-between mb-2">
            <label className="text-sm font-medium text-gray-700">
              {THRESHOLD_LABELS[params.max_missing] ??
                `Buy up to ${params.max_missing} things`}
            </label>
            <span className="text-xs text-gray-400">
              {count.toLocaleString()} {count === 1 ? 'recipe' : 'recipes'}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={3}
            step={1}
            value={params.max_missing}
            onChange={(e) => setParam('max_missing', Number(e.target.value))}
            className="w-full accent-green-600"
          />
        </div>

        <div className="flex flex-wrap gap-3">
          <select
            value={params.max_minutes ?? ''}
            onChange={(e) =>
              setParam(
                'max_minutes',
                e.target.value ? Number(e.target.value) : null
              )
            }
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
          >
            {TIME_OPTIONS.map((opt) => (
              <option key={opt.label} value={opt.value ?? ''}>
                {opt.label}
              </option>
            ))}
          </select>

          <select
            value={params.order}
            onChange={(e) =>
              setParam('order', e.target.value as typeof params.order)
            }
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
          >
            {ORDER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {moods.length > 0 && (
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Mood</p>
            <div className="flex flex-wrap gap-2">
              {visibleMoods.map((mood) => {
                const active = params.moods.includes(mood.key)
                return (
                  <button
                    key={mood.key}
                    onClick={() => toggleMood(mood.key)}
                    title={mood.description}
                    className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                      active
                        ? 'bg-green-600 text-white border-green-600'
                        : 'bg-white text-gray-600 border-gray-200 hover:border-green-400'
                    }`}
                  >
                    {mood.label}
                  </button>
                )
              })}
              <button
                onClick={() => setShowAllMoods((v) => !v)}
                className="text-xs px-3 py-1.5 text-gray-400 hover:text-gray-600"
              >
                {showAllMoods ? 'Fewer' : `+${moods.length - 8} more`}
              </button>
            </div>
            {/* Stated because it is not obvious: two moods narrow the
                results rather than widening them. */}
            {params.moods.length > 1 && (
              <p className="text-xs text-gray-400 mt-2">
                Recipes must match all {params.moods.length} selected moods.
              </p>
            )}
          </div>
        )}
      </div>

      {/* ── Results ── */}
      {loading && results.length === 0 && <Spinner />}

      {!loading && results.length === 0 && (
        <EmptyState
          icon="🍳"
          message={
            params.max_missing < 3
              ? 'Nothing matches yet. Try allowing a few missing ingredients, or clearing a mood filter.'
              : 'Nothing matches these filters. Try clearing a mood or the time limit.'
          }
        />
      )}

      {results.length > 0 && (
        <>
          <div
            className={`grid gap-4 sm:grid-cols-2 xl:grid-cols-3 transition-opacity ${
              loading ? 'opacity-50' : ''
            }`}
          >
            {results.map((match) => (
              <RecipeCard
                key={match.recipe.id}
                match={match}
                saved={savedIds.has(match.recipe.id)}
                onToggleSave={toggleSaved}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-4 mt-8 text-sm">
              <button
                onClick={() => setOffset(Math.max(0, params.offset - PAGE_SIZE))}
                disabled={page === 1}
                className="px-3 py-1 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40"
              >
                ← Prev
              </button>
              <span className="text-gray-500">
                Page {page} of {totalPages.toLocaleString()}
              </span>
              <button
                onClick={() => setOffset(params.offset + PAGE_SIZE)}
                disabled={page >= totalPages}
                className="px-3 py-1 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          )}

          {/* Small, but it makes the backend selection and cache observable
              rather than something the README asserts. */}
          {backend && (
            <p className="text-center text-xs text-gray-300 mt-4">
              {backend === 'es' ? 'Elasticsearch' : 'PostgreSQL'}
              {cached ? ' · cached' : ''}
            </p>
          )}
        </>
      )}
    </div>
  )
}