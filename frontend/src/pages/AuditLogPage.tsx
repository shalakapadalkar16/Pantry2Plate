// Paginated view of every ADDED/REMOVED/UPDATED action on the pantry.
//
// No store: logs are read-only and fetched per page, with no shared state
// or optimistic updates to coordinate. Local useState is enough.

import { useEffect, useState } from 'react'

import { getLogs } from '../api/pantryApi'
import { ErrorBanner, PageHeader, Spinner } from '../components/ui'
import type { IngredientLog, LogAction } from '../types'

// Keys must match the backend's IngredientLog.Action values exactly. They
// were ADD/REMOVE/UPDATE here against ADDED/REMOVED/UPDATED on the server,
// so every lookup returned undefined and the badge rendered unstyled.
const ACTION_STYLES: Record<LogAction, string> = {
  ADDED: 'bg-green-100 text-green-700',
  REMOVED: 'bg-red-100 text-red-600',
  UPDATED: 'bg-yellow-100 text-yellow-700',
}

// Matches PAGE_SIZE in config/settings/base.py. It was 10 here, so the page
// count was double the real one and the last pages were empty.
const PAGE_SIZE = 20

export default function AuditLogPage() {
  const [logs, setLogs] = useState<IngredientLog[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await getLogs(page)
        // Guard against a slower earlier request landing after a newer one
        // and overwriting the current page.
        if (cancelled) return
        setLogs(res.data.results)
        setTotalCount(res.data.count)
      } catch {
        if (!cancelled) setError('Failed to load audit logs.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [page])

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE))

  return (
    <div>
      <PageHeader
        title="Audit Log"
        subtitle="A history of every change made to your pantry"
      />

      <ErrorBanner message={error} />

      {loading && <Spinner />}

      {!loading && logs.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-16">
          No activity yet.
        </p>
      )}

      {!loading && logs.length > 0 && (
        <>
          <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">
                    Action
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">
                    Ingredient
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">
                    Quantity
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">
                    Date
                  </th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr
                    key={log.id}
                    className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs font-semibold px-2 py-1 rounded-full ${ACTION_STYLES[log.action]}`}
                      >
                        {log.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-800">
                      {/* The log keeps the text as written at the time, which
                          may differ from the ingredient's current name. */}
                      {log.ingredient?.display_name ?? log.ingredient_name}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {log.action === 'REMOVED' ? '−' : ''}
                      {parseFloat(log.quantity)} {log.unit}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-400">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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