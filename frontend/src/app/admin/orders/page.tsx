"use client";

import { useEffect, useState } from "react";
import { apiFetch, formatPrice } from "@/lib/api";
import { AdminGuard } from "@/components/admin-guard";

type AdminOrder = {
  id: number;
  status: string;
  total_cents: number;
  created_at: string;
  user_email: string;
};

const STATUSES = ["pending", "paid", "shipped", "cancelled"] as const;

export default function AdminOrdersPage() {
  const [orders, setOrders] = useState<AdminOrder[] | null>(null);

  function load() {
    apiFetch<{ orders: AdminOrder[] }>("/api/admin/orders").then((data) => setOrders(data.orders));
  }

  useEffect(load, []);

  async function handleStatusChange(id: number, status: string) {
    await apiFetch(`/api/admin/orders/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    load();
  }

  return (
    <AdminGuard>
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-semibold">Orders</h1>
        {orders === null ? (
          <p>Loading...</p>
        ) : orders.length === 0 ? (
          <p>No orders yet.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 dark:border-white/10">
                <th className="py-2">Order</th>
                <th className="py-2">Customer</th>
                <th className="py-2">Total</th>
                <th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id} className="border-b border-black/5 dark:border-white/5">
                  <td className="py-2">#{order.id}</td>
                  <td className="py-2">{order.user_email}</td>
                  <td className="py-2">{formatPrice(order.total_cents)}</td>
                  <td className="py-2">
                    <select
                      value={order.status}
                      onChange={(e) => handleStatusChange(order.id, e.target.value)}
                      className="rounded border border-black/20 px-2 py-1 dark:border-white/20"
                    >
                      {STATUSES.map((status) => (
                        <option key={status} value={status}>
                          {status}
                        </option>
                      ))}
                    </select>
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
