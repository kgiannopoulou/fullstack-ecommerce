import { AdminGuard } from "@/components/admin-guard";
import { ProductForm } from "@/components/product-form";

export default function NewProductPage() {
  return (
    <AdminGuard>
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-semibold">New product</h1>
        <ProductForm />
      </div>
    </AdminGuard>
  );
}
