"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useCart } from "@/lib/cart-context";

// Top nav shown on every page (mounted once in layout.tsx). Reads both
// contexts so the cart count and logged-in state stay in sync everywhere
// without prop drilling.
export function NavBar() {
  const { user, loading, logout } = useAuth();
  const { totalQuantity } = useCart();
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push("/");
  }

  return (
    <header className="border-b border-black/10 dark:border-white/10">
      <nav className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-4">
        <Link href="/" className="text-lg font-semibold">
          Shop
        </Link>
        <div className="flex items-center gap-4 text-sm">
          <Link href="/cart">Cart ({totalQuantity})</Link>
          {!loading && user?.role === "admin" && <Link href="/admin">Admin</Link>}
          {!loading && user && <Link href="/account/orders">Orders</Link>}
          {!loading && user ? (
            <button onClick={handleLogout} className="cursor-pointer">
              Log out ({user.email})
            </button>
          ) : (
            !loading && (
              <>
                <Link href="/login">Log in</Link>
                <Link href="/signup">Sign up</Link>
              </>
            )
          )}
        </div>
      </nav>
    </header>
  );
}
