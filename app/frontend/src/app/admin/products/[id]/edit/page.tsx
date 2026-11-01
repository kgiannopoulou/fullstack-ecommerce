"use client";

import { use, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { AdminGuard } from "@/components/admin-guard";
import { AdminProduct, ProductForm } from "@/components/product-form";

export default function EditProductPage(props: PageProps<"/admin/products/[id]/edit">) {
  // props.params is a Promise in the App Router; `use()` unwraps it in a
  // Client Component (the async/await equivalent used in Server Components
  // elsewhere, e.g. products/[slug]/page.tsx, isn't available here).
  const { id } = use(props.params);
  const [product, setProduct] = useState<AdminProduct | null>(null);

  // Fetch the existing product first, then hand it to ProductForm — the
  // form can't render its fields until it knows what to pre-fill.
  useEffect(() => {
    apiFetch<{ product: AdminProduct }>(`/api/admin/products/${id}`).then((data) =>
      setProduct(data.product)
    );
  }, [id]);

  return (
    <AdminGuard>
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-semibold">Edit product</h1>
        {product ? <ProductForm product={product} /> : <p>Loading...</p>}
      </div>
    </AdminGuard>
  );
}
