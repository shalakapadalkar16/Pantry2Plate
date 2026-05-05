// Shows a paginated, color-coded table of every ADD/REMOVE/UPDATE action that has happened in the pantry.
// It calls getLogs from pantryApi.ts directly — we don't need a store for this because logs are read-only, no optimistic updates or shared state needed.
// Local useState is enough.
// Why no store here: The pantry store exists because multiple components need to share and mutate the same ingredient list. 
// Logs are just a display — fetched once per page load, never mutated by the frontend. 
// Using a store for this would be overkill.

import { useEffect, useState } from "react";
import { getLogs } from "../api/pantryApi";
import { Spinner, ErrorBanner, PageHeader } from "../components/ui";
import type { IngredientLog } from "../types";

// Color coding per action type — makes the log easy to scan at a glance
const ACTION_STYLES: Record<IngredientLog["action"], string> = {
  ADD: "bg-green-100 text-green-700",
  REMOVE: "bg-red-100 text-red-600",
  UPDATE: "bg-yellow-100 text-yellow-700",
};

export default function AuditLogPage() {
  const [logs, setLogs] = useState<IngredientLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const PAGE_SIZE = 10; // matches backend's StandardResultsPagination

  // Fetch logs whenever the page number changes
  useEffect(() => {
    const fetch = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getLogs(page);
        setLogs(res.data.results);
        setTotalCount(res.data.count);
      } catch {
        setError("Failed to load audit logs.");
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, [page]);

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

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
                    Change
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
                    {/* Color-coded action badge */}
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs font-semibold px-2 py-1 rounded-full ${ACTION_STYLES[log.action]}`}
                      >
                        {log.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-800">
                      {log.ingredient_name}
                    </td>
                    {/* Shows + for additions, - for removals */}
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {log.action === "REMOVE" ? "-" : "+"}
                      {log.quantity_change} {log.unit}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-400">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination controls — only shown if more than one page */}
          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-4 mt-6 text-sm">
              <button
                onClick={() => setPage((p) => p - 1)}
                disabled={page === 1}
                className="px-3 py-1 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40"
              >
                ← Prev
              </button>
              <span className="text-gray-500">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page === totalPages}
                className="px-3 py-1 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}