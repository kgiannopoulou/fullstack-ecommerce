"use client";

import { useState } from "react";
import { Product } from "@/lib/api";
import { useCart } from "@/lib/cart-context";

export function AddToCartButton({ product }: { product: Product }) {
  const { addItem } = useCart();
  const [added, setAdded] = useState(false);

  function handleClick() {
    addItem(product);
    setAdded(true);
    setTimeout(() => setAdded(false), 1500);
  }

  return (
    <button
      onClick={handleClick}
      disabled={product.stock === 0}
      className="rounded bg-black px-4 py-2 text-white disabled:opacity-40 dark:bg-white dark:text-black"
    >
      {product.stock === 0 ? "Out of stock" : added ? "Added!" : "Add to cart"}
    </button>
  );
}
