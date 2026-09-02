// The recipe book.
//
// Local state for the list, but removal goes through the search store's
// toggleSaved so the id set stays consistent — unsaving here must also
// unfill the star on the search page.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getSavedRecipes, updateSavedNotes } from '../api/recipeApi'
import { useSearchStore } from '../store/searchStore'
import {
  EmptyState,
  ErrorBanner,
  PageHeader,
  Spinner,
} from '../components/ui'
import { titleCase } from '../utils/text'
import type { SavedRecipe } from '../types'

const PAGE_SIZE = 20

function NoteEditor({
  saved,
  onSaved,
}: {
  saved: SavedRecipe
  onSaved: (notes: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(saved.notes)
  const [busy, setBusy] = useState(false)

  const commit = async () => {
    setBusy(true)
    try {
      const res = await updateSavedNotes(saved.recipe.id, value)
      onSaved(res.data.notes)
      setEditing(false)
    } catch {
      // Revert to the last known good value rather than leaving the input
      // showing something the server rejected.
      setValue(saved.notes)
    } finally {
      setBusy(false)
    }
  }

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="text-left text-sm text-gray-500 hover:text-gray-700 italic w-full"
      >
        {saved.notes || 'Add a note…'}
      </button>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={2}
        autoFocus
        placeholder="Made it with less chilli. Worked well."
        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
      />
      <div className="flex gap-2">
        <button
          onClick={commit}
          disabled={busy}
          className="px-3 py-1 text-xs bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
        >
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={() => {
            setValue(saved.notes)
            setEditing(false)
          }}
          className="px-3 py-1 text-xs text-gray-500 hover:bg-gray-100 rounded-lg"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

export default function SavedRecipesPage() {
  const { toggleSaved, loadSavedIds } = useSearchStore()

  const [saved, setSaved] = useState<SavedRecipe[]>([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getSavedRecipes(page)
        if (cancelled) return
        setSaved(res.data.results)
        setCount(res.data.count)
      } catch {
        if (!cancelled) setError('Could not load your recipe book.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [page])

  const handleRemove = async (recipeId: number) => {
    // Optimistic locally, and toggleSaved keeps the shared id set in step.
    setSaved((rows) => rows.filter((row) => row.recipe.id !== recipeId))
    setCount((c) => Math.max(0, c - 1))
    await toggleSaved(recipeId)
    // Re-read the authoritative set in case the delete failed and the store
    // reverted it.
    await loadSavedIds()
  }

  const handleNoteSaved = (recipeId: number, notes: string) => {
    setSaved((rows) =>
      rows.map((row) =>
        row.recipe.id === recipeId ? { ...row, notes } : row
      )
    )
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))

  return (
    <div>
      <PageHeader
        title="My Recipes"
        subtitle={
          count
            ? `${count} saved ${count === 1 ? 'recipe' : 'recipes'}`
            : 'Recipes you have saved for later'
        }
      />

      <ErrorBanner message={error} />

      {loading && <Spinner />}

      {!loading && saved.length === 0 && (
        <>
          <EmptyState
            icon="📖"
            message="Nothing saved yet. Star a recipe to keep it here."
          />
          <div className="flex justify-center">
            <Link
              to="/search"
              className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700"
            >
              Find recipes
            </Link>
          </div>
        </>
      )}

      {!loading && saved.length > 0 && (
        <>
          <div className="flex flex-col gap-3">
            {saved.map((row) => (
              <div
                key={row.id}
                className="bg-white rounded-2xl shadow-sm p-5 flex flex-col gap-3"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <Link
                      to={`/recipes/${row.recipe.id}`}
                      className="font-semibold text-gray-800 hover:text-green-700"
                    >
                      {titleCase(row.recipe.name)}
                    </Link>
                    <p className="text-xs text-gray-400 mt-1">
                      {row.recipe.n_required} ingredients
                      {row.recipe.minutes
                        ? ` · ${row.recipe.minutes} min`
                        : ''}
                      {' · saved '}
                      {new Date(row.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <button
                    onClick={() => handleRemove(row.recipe.id)}
                    className="shrink-0 px-3 py-1 text-xs bg-red-50 hover:bg-red-100 rounded-lg text-red-500"
                  >
                    Remove
                  </button>
                </div>

                <NoteEditor
                  saved={row}
                  onSaved={(notes) => handleNoteSaved(row.recipe.id, notes)}
                />
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-4 mt-6 text-sm">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40"
              >
                ← Prev
              </button>
              <span className="text-gray-500">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}