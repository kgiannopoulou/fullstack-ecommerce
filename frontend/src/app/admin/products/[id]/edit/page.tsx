"use client";

import { use, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { AdminGuard } from "@/components/admin-guard";
import { AdminProduct, ProductForm } from "@/components/product-form";

export default function EditProductPage(props: PageProps<"/admin/products/[id]/edit">) {
  const { id } = use(props.params);
  const [product, setProduct] = useState<AdminProduct | null>(null);

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
