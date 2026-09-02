// Pantry management. Lists the user's ingredients, filters them, and handles
// add/edit/delete through pantryStore.

import { useEffect, useState } from 'react'
import axios from 'axios'

import { usePantryStore } from '../store/pantryStore'
import {
  EmptyState,
  ErrorBanner,
  Modal,
  PageHeader,
  Spinner,
} from '../components/ui'
import type {
  ApiError,
  PantryItem,
  PantryItemCreatePayload,
  PantryItemUpdatePayload,
} from '../types'

// Server messages beat generic ones. A rejected unit and a duplicate
// ingredient are different problems and the user can act on the difference.
function messageFrom(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiError | undefined
    if (body?.error?.fields) {
      const first = Object.values(body.error.fields)[0]
      if (Array.isArray(first) && first[0]) return first[0]
    }
    if (body?.error?.message) return body.error.message
  }
  return fallback
}

// ── Item form ─────────────────────────────────────────────────────────────────

function ItemForm({
  editItem,
  onClose,
}: {
  editItem: PantryItem | null
  onClose: () => void
}) {
  const { addItem, editItem: updateItem } = usePantryStore()

  // raw_input, not a canonical name — the backend does the resolution.
  const [name, setName] = useState(editItem?.raw_input ?? '')
  const [quantity, setQuantity] = useState(editItem?.quantity ?? '')
  const [unit, setUnit] = useState(editItem?.unit ?? '')
  const [expiryDate, setExpiryDate] = useState(editItem?.expiry_date ?? '')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async () => {
    if (!name.trim() || !quantity) {
      setError('Ingredient name and quantity are required.')
      return
    }

    setSaving(true)
    setError(null)
    try {
      if (editItem) {
        const payload: PantryItemUpdatePayload = {
          quantity: parseFloat(quantity),
          unit: unit || undefined,
          // Explicit null clears the date; undefined leaves it alone.
          expiry_date: expiryDate || null,
        }
        await updateItem(editItem.id, payload)
      } else {
        const payload: PantryItemCreatePayload = {
          raw_input: name.trim(),
          quantity: parseFloat(quantity),
          unit: unit || undefined,
          expiry_date: expiryDate || null,
        }
        await addItem(payload)
      }
      onClose()
    } catch (err) {
      setError(messageFrom(err, 'Something went wrong. Please try again.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <ErrorBanner message={error} />

      <div>
        <label className="text-sm text-gray-600 mb-1 block">Ingredient</label>
        <input
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={!!editItem}
          placeholder="e.g. extra virgin olive oil"
        />
        {!editItem && (
          <p className="text-xs text-gray-400 mt-1">
            Type it however you like — "EVOO", "2 large onions" and "chicken
            breasts" all work.
          </p>
        )}
      </div>

      <div className="flex gap-3">
        <div className="flex-1">
          <label className="text-sm text-gray-600 mb-1 block">Quantity</label>
          <input
            type="number"
            min="0"
            step="any"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="6"
          />
        </div>
        <div className="flex-1">
          <label className="text-sm text-gray-600 mb-1 block">Unit</label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            placeholder="g, cups, tbsp, pieces"
          />
        </div>
      </div>

      <div>
        <label className="text-sm text-gray-600 mb-1 block">
          Expiry date (optional)
        </label>
        <input
          type="date"
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
          value={expiryDate ?? ''}
          onChange={(e) => setExpiryDate(e.target.value)}
        />
      </div>

      <div className="flex justify-end gap-2 mt-2">
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 rounded-lg"
        >
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={saving}
          className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : editItem ? 'Save changes' : 'Add item'}
        </button>
      </div>
    </div>
  )
}

// ── Expiry helpers ────────────────────────────────────────────────────────────

function isExpiringSoon(date: string | null): boolean {
  if (!date) return false
  const diff = new Date(date).getTime() - Date.now()
  return diff > 0 && diff <= 3 * 24 * 60 * 60 * 1000
}

function isExpired(date: string | null): boolean {
  if (!date) return false
  return new Date(date).getTime() < Date.now()
}

// ── Row ───────────────────────────────────────────────────────────────────────

function IngredientRow({
  item,
  onEdit,
  onDelete,
}: {
  item: PantryItem
  onEdit: (item: PantryItem) => void
  onDelete: (id: number) => void
}) {
  const expiring = isExpiringSoon(item.expiry_date)
  const expired = isExpired(item.expiry_date)

  const rowClass = expired ? 'bg-red-50' : expiring ? 'bg-yellow-50' : 'bg-white'

  return (
    <tr
      className={`${rowClass} border-b border-gray-100 hover:brightness-95 transition-all`}
    >
      <td className="px-4 py-3 text-sm font-medium text-gray-800">
        {item.display_name}
        {/* Surfaced deliberately. An unresolved item will never appear in a
            recipe match, and the user should be able to see why rather than
            wonder where their ingredient went. */}
        {!item.is_resolved && (
          <span
            className="ml-2 text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full"
            title="We could not identify this ingredient, so it will not be matched to recipes"
          >
            unrecognised
          </span>
        )}
        {item.ingredient?.is_staple && (
          <span
            className="ml-2 text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full"
            title="Assumed present in every kitchen — never counted as missing"
          >
            staple
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">
        {/* quantity arrives as a string like "6.00" */}
        {parseFloat(item.quantity)} {item.unit}
      </td>
      <td className="px-4 py-3 text-sm">
        {item.expiry_date ? (
          <span
            className={
              expired
                ? 'text-red-600 font-medium'
                : expiring
                  ? 'text-yellow-600 font-medium'
                  : 'text-gray-500'
            }
          >
            {expired && '⚠️ '}
            {expiring && !expired && '⏰ '}
            {new Date(item.expiry_date).toLocaleDateString()}
          </span>
        ) : (
          <span className="text-gray-300">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-sm flex gap-2 justify-end">
        <button
          onClick={() => onEdit(item)}
          className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-lg text-gray-600"
        >
          Edit
        </button>
        <button
          onClick={() => onDelete(item.id)}
          className="px-3 py-1 text-xs bg-red-50 hover:bg-red-100 rounded-lg text-red-500"
        >
          Delete
        </button>
      </td>
    </tr>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PantryPage() {
  const { items, loading, error, loadItems, removeItem } = usePantryStore()

  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<PantryItem | null>(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    loadItems()
  }, [loadItems])

  // Filters on both the canonical name and what the user typed, so someone
  // searching "evoo" finds the item they entered that way.
  const filtered = items.filter((item) => {
    const needle = search.toLowerCase()
    return (
      item.display_name.toLowerCase().includes(needle) ||
      item.raw_input.toLowerCase().includes(needle)
    )
  })

  const unresolvedCount = items.filter((item) => !item.is_resolved).length

  const handleAdd = () => {
    setEditTarget(null)
    setModalOpen(true)
  }

  const handleEdit = (item: PantryItem) => {
    setEditTarget(item)
    setModalOpen(true)
  }

  const handleClose = () => {
    setModalOpen(false)
    setEditTarget(null)
  }

  return (
    <div>
      <PageHeader
        title="My Pantry"
        subtitle={
          items.length
            ? `${items.length} ingredients tracked`
            : 'Track your ingredients and expiry dates'
        }
      />

      <ErrorBanner message={error} />

      {unresolvedCount > 0 && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-4 py-3 text-sm mb-4">
          {unresolvedCount} {unresolvedCount === 1 ? 'item' : 'items'} could not
          be identified and will not be matched to recipes. Try a simpler name.
        </div>
      )}

      <div className="flex items-center gap-3 mb-6">
        <input
          className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
          placeholder="Search ingredients..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button
          onClick={handleAdd}
          className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700"
        >
          + Add item
        </button>
      </div>

      {loading && <Spinner />}

      {!loading && filtered.length === 0 && (
        <EmptyState
          icon="🥦"
          message={
            search
              ? 'No ingredients match your search.'
              : 'Your pantry is empty. Add your first ingredient!'
          }
        />
      )}

      {!loading && filtered.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">
                  Ingredient
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">
                  Quantity
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">
                  Expires
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <IngredientRow
                  key={item.id}
                  item={item}
                  onEdit={handleEdit}
                  onDelete={removeItem}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        isOpen={modalOpen}
        onClose={handleClose}
        title={editTarget ? 'Edit ingredient' : 'Add ingredient'}
      >
        <ItemForm editItem={editTarget} onClose={handleClose} />
      </Modal>
    </div>
  )
}