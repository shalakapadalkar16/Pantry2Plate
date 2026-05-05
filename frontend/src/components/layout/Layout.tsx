// shell that wraps every protected page
// It renders a sidebar on the left with navigation links and a sign-out button, and an <Outlet /> on the right where the current page's content appears. 
// Every route inside RequireAuth will be wrapped in this — so you define the sidebar once and it shows up everywhere automatically.

import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";

// Each nav item — path is the route, label is display text, icon is an emoji
const NAV_ITEMS = [
  { path: "/pantry", label: "My Pantry", icon: "🥦" },
  { path: "/logs", label: "Audit Log", icon: "📋" },
];

export default function Layout() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  // Signs out and sends user back to login
  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* ── Sidebar ── */}
      <aside className="w-56 bg-white border-r border-gray-200 flex flex-col py-6 px-4">
        {/* App name at the top */}
        <div className="text-xl font-bold text-green-600 mb-8 px-2">
          🍽 Pantry2Plate
        </div>

        {/* Nav links */}
        <nav className="flex flex-col gap-1 flex-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-green-50 text-green-700"
                    : "text-gray-600 hover:bg-gray-100"
                }`
              }
            >
              <span>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* User info + sign out at the bottom */}
        <div className="border-t border-gray-100 pt-4">
          <p className="text-xs text-gray-400 px-2 mb-2 truncate">
            {user?.first_name} {user?.last_name}
          </p>
          <button
            onClick={handleLogout}
            className="w-full text-left px-3 py-2 text-sm text-red-500 hover:bg-red-50 rounded-lg transition-colors"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* ── Main content area — active page renders here ── */}
      <main className="flex-1 overflow-y-auto p-8">
        <Outlet />
      </main>
    </div>
  );
}