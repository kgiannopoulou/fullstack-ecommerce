"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, formatPrice } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useCart } from "@/lib/cart-context";

export default function CartPage() {
  const { items, updateQuantity, removeItem, totalCents } = useCart();
  const { user, loading } = useAuth();
  const router = useRouter();
  const [checkingOut, setCheckingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCheckout() {
    if (!user) {
      router.push("/login?next=/cart");
      return;
    }

    setError(null);
    setCheckingOut(true);
    try {
      const data = await apiFetch<{ url: string }>("/api/checkout/create-session", {
        method: "POST",
        body: JSON.stringify({
          items: items.map((item) => ({ productId: item.productId, quantity: item.quantity })),
        }),
      });
      window.location.href = data.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
      setCheckingOut(false);
    }
  }

  if (items.length === 0) {
    return (
      <p>
        Your cart is empty. <Link href="/" className="underline">Browse products</Link>.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Your cart</h1>
      <div className="flex flex-col divide-y divide-black/10 dark:divide-white/10">
        {items.map((item) => (
          <div key={item.productId} className="flex items-center justify-between gap-4 py-3">
            <div>
              <Link href={`/products/${item.slug}`} className="font-medium hover:underline">
                {item.name}
              </Link>
              <p className="text-sm opacity-60">{formatPrice(item.priceCents)} each</p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={1}
                value={item.quantity}
                onChange={(e) => updateQuantity(item.productId, Number(e.target.value))}
                className="w-16 rounded border border-black/20 px-2 py-1 dark:border-white/20"
              />
              <button onClick={() => removeItem(item.productId)} className="text-sm underline">
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between border-t border-black/10 pt-4 dark:border-white/10">
        <span className="text-lg font-semibold">Total: {formatPrice(totalCents)}</span>
        <button
          onClick={handleCheckout}
          disabled={checkingOut || loading}
          className="rounded bg-black px-4 py-2 text-white disabled:opacity-40 dark:bg-white dark:text-black"
        >
          {checkingOut ? "Redirecting to Stripe..." : "Checkout"}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
