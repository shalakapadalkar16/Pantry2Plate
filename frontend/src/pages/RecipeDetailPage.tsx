// Full recipe, with every ingredient marked against the user's pantry.
//
// No store: this is read-only and fetched per recipe id, with nothing shared
// to coordinate. The one exception is the saved-state star, which reads and
// writes the search store's id set so both pages stay consistent.

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getRecipeDetail } from '../api/recipeApi'
import { useSearchStore } from '../store/searchStore'
import { ErrorBanner, Spinner } from '../components/ui'
import { titleCase } from '../utils/text'
import type { IngredientState, RecipeDetail } from '../types'

// Four states, four meanings. 'staple' is reported but never counted as
// missing, so the user can see why a recipe listing salt still shows as
// fully covered.
const STATE_STYLES: Record<IngredientState, string> = {
  have: 'bg-green-50 border-green-200 text-green-800',
  missing: 'bg-amber-50 border-amber-200 text-amber-800',
  unknown: 'bg-gray-50 border-gray-200 text-gray-500 italic',
  staple: 'bg-blue-50 border-blue-200 text-blue-700',
}

const STATE_LABELS: Record<IngredientState, string> = {
  have: 'in your pantry',
  missing: 'need to buy',
  unknown: 'not recognised',
  staple: 'assumed in every kitchen',
}

const STATE_ORDER: IngredientState[] = ['missing', 'unknown', 'have', 'staple']

export default function RecipeDetailPage() {
  const { id } = useParams<{ id: string }>()
  const recipeId = Number(id)

  const { savedIds, toggleSaved } = useSearchStore()
  const saved = savedIds.has(recipeId)

  const [recipe, setRecipe] = useState<RecipeDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getRecipeDetail(recipeId)
        if (!cancelled) setRecipe(res.data)
      } catch {
        if (!cancelled) setError('Could not load that recipe.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    if (Number.isFinite(recipeId)) load()
    else {
      setError('Invalid recipe.')
      setLoading(false)
    }

    return () => {
      cancelled = true
    }
  }, [recipeId])

  if (loading) return <Spinner />

  if (error || !recipe) {
    return (
      <div>
        <ErrorBanner message={error ?? 'Recipe not found.'} />
        <Link to="/search" className="text-sm text-green-700 hover:underline">
          ← Back to search
        </Link>
      </div>
    )
  }

  const { summary } = recipe
  const cookable = summary.missing === 0 && summary.unknown === 0

  return (
    <div className="max-w-3xl">
      <Link
        to="/search"
        className="text-sm text-gray-400 hover:text-gray-600 mb-4 inline-block"
      >
        ← Back to search
      </Link>

      <div className="flex items-start justify-between gap-4 mb-2">
        <h1 className="text-2xl font-bold text-gray-800 leading-tight">
          {titleCase(recipe.name)}
        </h1>
        <button
          onClick={() => toggleSaved(recipeId)}
          title={saved ? 'Remove from your book' : 'Save to your book'}
          className={`shrink-0 text-2xl leading-none transition-transform hover:scale-110 ${
            saved ? '' : 'opacity-30 hover:opacity-70'
          }`}
        >
          {saved ? '★' : '☆'}
        </button>
      </div>

      <div className="flex items-center gap-3 flex-wrap text-sm text-gray-500 mb-6">
        {recipe.minutes ? <span>{recipe.minutes} min</span> : null}
        <span>·</span>
        <span>{summary.n_required} ingredients needed</span>
        {recipe.calories ? (
          <>
            <span>·</span>
            <span>{Math.round(recipe.calories)} cal</span>
          </>
        ) : null}
      </div>

      {/* Verdict first. It is the question the user came to answer. */}
      <div
        className={`rounded-2xl px-5 py-4 mb-6 ${
          cookable
            ? 'bg-green-50 border border-green-200'
            : 'bg-amber-50 border border-amber-200'
        }`}
      >
        <p
          className={`font-semibold ${
            cookable ? 'text-green-800' : 'text-amber-800'
          }`}
        >
          {cookable
            ? 'You can cook this right now'
            : `You need ${summary.missing + summary.unknown} more ${
                summary.missing + summary.unknown === 1 ? 'thing' : 'things'
              }`}
        </p>
        <p className="text-sm text-gray-600 mt-1">
          {summary.have} of {summary.n_required} required ingredients are in
          your pantry
          {summary.unknown > 0 &&
            `, and ${summary.unknown} could not be identified`}
          .
        </p>
      </div>

      {recipe.description && (
        <p className="text-sm text-gray-600 mb-6 leading-relaxed">
          {recipe.description}
        </p>
      )}

      {/* Ingredients, grouped by state with missing first — that is the
          shopping list, and it is what the user needs to act on. */}
      <section className="mb-8">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
          Ingredients
        </h2>
        <div className="flex flex-col gap-4">
          {STATE_ORDER.map((state) => {
            const rows = recipe.ingredients.filter((i) => i.state === state)
            if (!rows.length) return null

            return (
              <div key={state}>
                <p className="text-xs text-gray-400 mb-2">
                  {STATE_LABELS[state]}
                </p>
                <div className="flex flex-wrap gap-2">
                  {rows.map((row, index) => (
                    <span
                      key={`${row.raw_text}-${index}`}
                      title={row.raw_text}
                      className={`text-sm border px-3 py-1.5 rounded-lg ${STATE_STYLES[state]}`}
                    >
                      {row.display_name}
                    </span>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
          Method
        </h2>
        <ol className="flex flex-col gap-3">
          {recipe.steps.map((step, index) => (
            <li key={index} className="flex gap-3 text-sm text-gray-700">
              <span className="shrink-0 w-6 h-6 rounded-full bg-gray-100 text-gray-500 text-xs flex items-center justify-center">
                {index + 1}
              </span>
              <span className="leading-relaxed first-letter:uppercase">
                {step}
              </span>
            </li>
          ))}
        </ol>
      </section>

      {recipe.tags.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
            Tags
          </h2>
          <div className="flex flex-wrap gap-1.5">
            {/* These are the source corpus tags the mood filters map onto. */}
            {recipe.tags.slice(0, 20).map((tag) => (
              <span
                key={tag}
                className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded"
              >
                {tag}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}