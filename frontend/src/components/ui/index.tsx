// These are small, reusable UI building blocks that multiple pages will use. 
// Instead of rewriting a spinner or error banner in every page, you build it once here and import it anywhere. 
// Personal mini design system.

// Reusable UI primitives — import these instead of rewriting them per page

// Animated loading circle — show this while waiting for API responses
export function Spinner() {
  return (
    <div className="flex justify-center items-center py-8">
      <div className="w-8 h-8 border-4 border-green-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

// Overlay modal — pass any form or content as children, control with isOpen/onClose
export function Modal({
  isOpen,
  onClose,
  title,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  if (!isOpen) return null;
  return (
    // Dark backdrop — clicking it closes the modal
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      {/* Stop clicks inside the modal from closing it */}
      <div
        className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold mb-4">{title}</h2>
        {children}
      </div>
    </div>
  );
}

// Shown when a list is empty — pass an icon emoji and a message
export function EmptyState({ icon, message }: { icon: string; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-gray-400">
      <span className="text-5xl mb-3">{icon}</span>
      <p className="text-sm">{message}</p>
    </div>
  );
}

// Red error banner — pass the error string, returns null if no error
export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm mb-4">
      {message}
    </div>
  );
}

// Consistent page title block — used at the top of PantryPage, AuditLogPage, etc.
export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-bold text-gray-800">{title}</h1>
      {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
    </div>
  );
}