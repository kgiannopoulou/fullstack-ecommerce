"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, formatPrice } from "@/lib/api";
import { AdminGuard } from "@/components/admin-guard";
import { AdminProduct } from "@/components/product-form";

export default function AdminProductsPage() {
  const [products, setProducts] = useState<AdminProduct[] | null>(null);

  function load() {
    apiFetch<{ products: AdminProduct[] }>("/api/admin/products").then((data) =>
      setProducts(data.products)
    );
  }

  useEffect(load, []);

  async function handleDelete(id: number) {
    if (!confirm("Delete this product?")) return;
    await apiFetch(`/api/admin/products/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <AdminGuard>
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Products</h1>
          <Link
            href="/admin/products/new"
            className="rounded bg-black px-4 py-2 text-white dark:bg-white dark:text-black"
          >
            New product
          </Link>
        </div>
        {products === null ? (
          <p>Loading...</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 dark:border-white/10">
                <th className="py-2">Name</th>
                <th className="py-2">Price</th>
                <th className="py-2">Stock</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {products.map((product) => (
                <tr key={product.id} className="border-b border-black/5 dark:border-white/5">
                  <td className="py-2">{product.name}</td>
                  <td className="py-2">{formatPrice(product.price_cents)}</td>
                  <td className="py-2">{product.stock}</td>
                  <td className="flex gap-3 py-2">
                    <Link href={`/admin/products/${product.id}/edit`} className="underline">
                      Edit
                    </Link>
                    <button onClick={() => handleDelete(product.id)} className="underline">
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </AdminGuard>
  );
}
