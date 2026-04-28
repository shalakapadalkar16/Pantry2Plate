// the main pantry management page
// It shows the user's ingredient list, lets them search/filter it, add new items via a modal, edit quantities, and delete items. 
// It pulls everything from pantryStore and uses the shared UI components

import { useEffect, useState } from "react";
import { usePantryStore } from "../store/pantryStore";
import {
  Spinner,
  Modal,
  EmptyState,
  ErrorBanner,
  PageHeader,
} from "../components/ui";
import type { PantryItem, PantryItemCreatePayload, PantryItemUpdatePayload } from "../types";

// ── Item Form ─────────────────────────────────────────────────────────────────
// Rendered inside the Modal for both Add and Edit actions.
// editItem is null when adding, populated when editing.
function ItemForm({
  editItem,
  onClose,
}: {
  editItem: PantryItem | null;
  onClose: () => void;
}) {
  const { addItem, editItem: updateItem } = usePantryStore();

  // Pre-fill fields if editing, blank if adding
  const [name, setName] = useState(editItem?.ingredient_name ?? "");
  const [quantity, setQuantity] = useState(editItem?.quantity?.toString() ?? "");
  const [unit, setUnit] = useState(editItem?.unit ?? "");
  const [expiresAt, setExpiresAt] = useState(editItem?.expires_at ?? "");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    // Basic validation before hitting the API
    if (!name.trim() || !quantity) {
      setError("Ingredient name and quantity are required.");
      return;
    }
    try {
      if (editItem) {
        // Editing — only send quantity/unit/expiry, not name
        const payload: PantryItemUpdatePayload = {
          quantity: parseFloat(quantity),
          unit: unit || undefined,
          expires_at: expiresAt || undefined,
        };
        await updateItem(editItem.id, payload);
      } else {
        // Adding — send all fields
        const payload: PantryItemCreatePayload = {
          ingredient_name: name.trim(),
          quantity: parseFloat(quantity),
          unit: unit || undefined,
          expires_at: expiresAt || undefined,
        };
        await addItem(payload);
      }
      onClose();
    } catch {
      setError("Something went wrong. Please try again.");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <ErrorBanner message={error} />

      {/* Name field — disabled when editing since you can't rename an ingredient */}
      <div>
        <label className="text-sm text-gray-600 mb-1 block">Ingredient name</label>
        <input
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={!!editItem}
          placeholder="e.g. Eggs"
        />
      </div>

      <div className="flex gap-3">
        <div className="flex-1">
          <label className="text-sm text-gray-600 mb-1 block">Quantity</label>
          <input
            type="number"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="e.g. 6"
          />
        </div>
        <div className="flex-1">
          <label className="text-sm text-gray-600 mb-1 block">Unit</label>
          <input
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            placeholder="e.g. pcs, ml, g"
          />
        </div>
      </div>

      <div>
        <label className="text-sm text-gray-600 mb-1 block">Expires at (optional)</label>
        <input
          type="date"
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
          value={expiresAt}
          onChange={(e) => setExpiresAt(e.target.value)}
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
          className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700"
        >
          {editItem ? "Save changes" : "Add item"}
        </button>
      </div>
    </div>
  );
}

// ── Expiry helpers ────────────────────────────────────────────────────────────

// Returns true if the item expires within the next 3 days
function isExpiringSoon(expiresAt: string | null): boolean {
  if (!expiresAt) return false;
  const diff = new Date(expiresAt).getTime() - Date.now();
  const threeDays = 3 * 24 * 60 * 60 * 1000;
  return diff > 0 && diff <= threeDays;
}

// Returns true if the item has already expired
function isExpired(expiresAt: string | null): boolean {
  if (!expiresAt) return false;
  return new Date(expiresAt).getTime() < Date.now();
}

// ── Ingredient Row ────────────────────────────────────────────────────────────
// One row in the pantry table.
// onEdit and onDelete are passed down from PantryPage.
function IngredientRow({
  item,
  onEdit,
  onDelete,
}: {
  item: PantryItem;
  onEdit: (item: PantryItem) => void;
  onDelete: (id: string) => void;
}) {
  const expiring = isExpiringSoon(item.expires_at);
  const expired = isExpired(item.expires_at);

  // Row gets a yellow tint if expiring soon, red tint if already expired
  const rowClass = expired
    ? "bg-red-50"
    : expiring
    ? "bg-yellow-50"
    : "bg-white";

  return (
    <tr className={`${rowClass} border-b border-gray-100 hover:brightness-95 transition-all`}>
      <td className="px-4 py-3 text-sm font-medium text-gray-800">
        {item.ingredient_name}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">
        {item.quantity} {item.unit}
      </td>
      <td className="px-4 py-3 text-sm">
        {item.expires_at ? (
          <span
            className={
              expired
                ? "text-red-600 font-medium"
                : expiring
                ? "text-yellow-600 font-medium"
                : "text-gray-500"
            }
          >
            {expired && "⚠️ "}
            {expiring && !expired && "⏰ "}
            {new Date(item.expires_at).toLocaleDateString()}
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
  );
}

// ── PantryPage ────────────────────────────────────────────────────────────────
// Main page — wires the store, search filter, and modal together
export default function PantryPage() {
  const { items, loading, error, loadItems, removeItem } = usePantryStore();

  // Controls the add/edit modal
  const [modalOpen, setModalOpen] = useState(false);
  // null = adding new item, populated = editing existing item
  const [editTarget, setEditTarget] = useState<PantryItem | null>(null);
  // Search filter — filters client-side, no extra API call needed
  const [search, setSearch] = useState("");

  // Load pantry items once when the page mounts
  useEffect(() => {
    loadItems();
  }, [loadItems]);

  // Filter items by ingredient name as the user types
  const filtered = items.filter((item) =>
    item.ingredient_name.toLowerCase().includes(search.toLowerCase())
  );

  // Opens modal in "add" mode
  const handleAdd = () => {
    setEditTarget(null);
    setModalOpen(true);
  };

  // Opens modal in "edit" mode with the selected item pre-filled
  const handleEdit = (item: PantryItem) => {
    setEditTarget(item);
    setModalOpen(true);
  };

  // Closes modal and clears edit target
  const handleClose = () => {
    setModalOpen(false);
    setEditTarget(null);
  };

  return (
    <div>
      <PageHeader
        title="My Pantry"
        subtitle="Track your ingredients and expiry dates"
      />

      <ErrorBanner message={error} />

      {/* Search bar + Add button row */}
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

      {/* Loading state */}
      {loading && <Spinner />}

      {/* Empty state — shown when no items match the search */}
      {!loading && filtered.length === 0 && (
        <EmptyState
          icon="🥦"
          message={
            search
              ? "No ingredients match your search."
              : "Your pantry is empty. Add your first ingredient!"
          }
        />
      )}

      {/* Ingredient table */}
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

      {/* Add / Edit modal */}
      <Modal
        isOpen={modalOpen}
        onClose={handleClose}
        title={editTarget ? "Edit ingredient" : "Add ingredient"}
      >
        <ItemForm editItem={editTarget} onClose={handleClose} />
      </Modal>
    </div>
  );
}