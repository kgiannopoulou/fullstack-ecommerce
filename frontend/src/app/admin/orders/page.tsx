"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch, formatPrice, Pagination } from "@/lib/api";
import { AdminGuard } from "@/components/admin-guard";
import { OrderEvent, OrderTimeline } from "@/components/order-timeline";

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

const STATUS_FILTERS = ["", "pending", "paid", "shipped", "cancelled"];

function withoutKey<T>(record: Record<number, T>, key: number) {
  const copy = { ...record };
  delete copy[key];
  return copy;
}

export default function AdminOrdersPage() {
  const [orders, setOrders] = useState<AdminOrder[] | null>(null);
  const [pagination, setPagination] = useState<Pagination | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Order id -> its audit trail, for the rows whose history is open.
  const [history, setHistory] = useState<Record<number, OrderEvent[]>>({});

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page) });
    if (status) params.set("status", status);
    apiFetch<{ orders: AdminOrder[]; pagination: Pagination }>(`/api/admin/orders?${params}`).then((data) => {
      setOrders(data.orders);
      setPagination(data.pagination);
    });
  }, [page, status]);

  useEffect(load, [load]);

  async function toggleHistory(id: number) {
    if (history[id]) {
      setHistory((h) => withoutKey(h, id));
      return;
    }
    const data = await apiFetch<{ history: OrderEvent[] }>(`/api/admin/orders/${id}/history`);
    setHistory((h) => ({ ...h, [id]: data.history }));
  }

  // Manual change, e.g. marking an order "shipped". 'paid' is only ever set
  // by the Stripe webhook (see backend checkout/orderLifecycle.ts), so the
  // dropdown only offers the moves the backend allows for each order.
  async function handleStatusChange(id: number, next: string) {
    if (next === "cancelled" && !window.confirm(`Cancel order #${id}? Its stock will be returned.`)) {
      return;
    }
    setError(null);
    try {
      await apiFetch(`/api/admin/orders/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: next }),
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update the order.");
    }
    setHistory((h) => withoutKey(h, id));
    load();
  }

  return (
    <AdminGuard>
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-2xl font-semibold">Orders</h1>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            aria-label="Filter by status"
            className="rounded border border-black/20 px-2 py-1 text-sm dark:border-white/20"
          >
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>
                {s || "All statuses"}
              </option>
            ))}
          </select>
        </div>
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
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <Fragment key={order.id}>
                  <tr className="border-b border-black/5 dark:border-white/5">
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
                        {[order.status, ...order.next_statuses].map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2 text-right">
                      <button onClick={() => toggleHistory(order.id)} className="cursor-pointer underline">
                        {history[order.id] ? "Hide history" : "History"}
                      </button>
                    </td>
                  </tr>
                  {history[order.id] && (
                    <tr>
                      <td colSpan={5} className="py-3">
                        <OrderTimeline events={history[order.id]} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
        {pagination && pagination.totalPages > 1 && (
          <div className="flex items-center justify-center gap-4 text-sm">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="underline disabled:opacity-40">
              Previous
            </button>
            <span>
              Page {pagination.page} of {pagination.totalPages}
            </span>
            <button
              disabled={page >= pagination.totalPages}
              onClick={() => setPage(page + 1)}
              className="underline disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </AdminGuard>
  );
}
