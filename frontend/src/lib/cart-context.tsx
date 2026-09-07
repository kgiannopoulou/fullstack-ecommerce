"use client";

// The cart is intentionally client-side only (localStorage), not stored on
// the backend or tied to a user account: browsing and adding to cart never
// requires being logged in — only checkout does (see cart/page.tsx).
import { createContext, useContext, useEffect, useState } from "react";
import { Product } from "./api";

export type CartItem = {
  productId: number;
  name: string;
  slug: string;
  priceCents: number;
  quantity: number;
};

type CartContextValue = {
  items: CartItem[];
  addItem: (product: Product, quantity?: number) => void;
  updateQuantity: (productId: number, quantity: number) => void;
  removeItem: (productId: number) => void;
  clear: () => void;
  totalCents: number;
  totalQuantity: number;
};

const CartContext = createContext<CartContextValue | null>(null);
const STORAGE_KEY = "ecommerce-cart";

export function CartProvider({ children }: { children: React.ReactNode }) {
  // Cart always starts empty on first render (including during server-side
  // rendering, which has no localStorage) and is filled in from
  // localStorage after mount, below.
  const [items, setItems] = useState<CartItem[]>([]);
  // Guards against the effect below overwriting a real saved cart with an
  // empty one before the read-from-localStorage effect has had a chance
  // to run.
  const [hydrated, setHydrated] = useState(false);

  // Runs once on mount (client only) to restore a cart saved in a previous
  // visit/tab.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrating from localStorage on mount
      if (raw) setItems(JSON.parse(raw));
    } catch {
      // ignore corrupt cart data
    }
    setHydrated(true);
  }, []);

  // Persists on every change so a page refresh or new tab sees the same cart.
  useEffect(() => {
    if (!hydrated) return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  }, [items, hydrated]);

  function addItem(product: Product, quantity = 1) {
    setItems((prev) => {
      const existing = prev.find((item) => item.productId === product.id);
      if (existing) {
        return prev.map((item) =>
          item.productId === product.id
            ? { ...item, quantity: item.quantity + quantity }
            : item
        );
      }
      return [
        ...prev,
        {
          productId: product.id,
          name: product.name,
          slug: product.slug,
          priceCents: product.price_cents,
          quantity,
        },
      ];
    });
  }

  function updateQuantity(productId: number, quantity: number) {
    if (quantity <= 0) {
      removeItem(productId);
      return;
    }
    setItems((prev) =>
      prev.map((item) => (item.productId === productId ? { ...item, quantity } : item))
    );
  }

  function removeItem(productId: number) {
    setItems((prev) => prev.filter((item) => item.productId !== productId));
  }

  function clear() {
    setItems([]);
  }

  const totalCents = items.reduce((sum, item) => sum + item.priceCents * item.quantity, 0);
  const totalQuantity = items.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <CartContext.Provider
      value={{ items, addItem, updateQuantity, removeItem, clear, totalCents, totalQuantity }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used within CartProvider");
  return ctx;
}
