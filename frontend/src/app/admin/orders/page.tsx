"use client";

import { useEffect, useState } from "react";
import { ApiError, apiFetch, formatPrice } from "@/lib/api";
import { AdminGuard } from "@/components/admin-guard";

type AdminOrder = {
  id: number;
  status: string;
  total_cents: number;
  created_at: string;
  user_email: string;
  // Statuses the backend will accept as the next manual change for this
  // order (see ADMIN_TRANSITIONS in backend checkout/orderLifecycle.ts).
  next_statuses: string[];
};

export default function AdminOrdersPage() {
  const [orders, setOrders] = useState<AdminOrder[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    apiFetch<{ orders: AdminOrder[] }>("/api/admin/orders").then((data) => setOrders(data.orders));
  }

  useEffect(load, []);

  // Manual change, e.g. marking an order "shipped". 'paid' is only ever set
  // by the Stripe webhook (see backend checkout/orderLifecycle.ts), so the
  // dropdown only offers the moves the backend allows for each order.
  async function handleStatusChange(id: number, status: string) {
    if (status === "cancelled" && !window.confirm(`Cancel order #${id}? Its stock will be returned.`)) {
      return;
    }
    setError(null);
    try {
      await apiFetch(`/api/admin/orders/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update the order.");
    }
    load();
  }

  return (
    <AdminGuard>
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-semibold">Orders</h1>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <p className="text-sm text-black/60 dark:text-white/60">
          Cancelling a paid order returns its stock; issue the refund from the Stripe dashboard.
        </p>
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
                      disabled={order.next_statuses.length === 0}
                      onChange={(e) => handleStatusChange(order.id, e.target.value)}
                      className="rounded border border-black/20 px-2 py-1 disabled:opacity-60 dark:border-white/20"
                    >
                      {[order.status, ...order.next_statuses].map((status) => (
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
