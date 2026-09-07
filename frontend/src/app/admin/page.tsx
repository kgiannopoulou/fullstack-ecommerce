import Link from "next/link";
import { AdminGuard } from "@/components/admin-guard";

export default function AdminHomePage() {
  return (
    <AdminGuard>
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold">Admin</h1>
        <div className="flex gap-4 underline">
          <Link href="/admin/products">Manage products</Link>
          <Link href="/admin/orders">Manage orders</Link>
        </div>
      </div>
    </AdminGuard>
  );
}
