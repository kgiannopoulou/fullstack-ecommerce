"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, formatPrice } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

type OrderItem = { name: string; slug: string; quantity: number; price_cents: number };
type Order = {
  id: number;
  status: string;
  total_cents: number;
  created_at: string;
  items: OrderItem[];
};

export default function OrdersPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [orders, setOrders] = useState<Order[] | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.push("/login?next=/account/orders");
      return;
    }
    apiFetch<{ orders: Order[] }>("/api/orders").then((data) => setOrders(data.orders));
  }, [loading, user, router]);

  if (loading || orders === null) return <p>Loading...</p>;
  if (orders.length === 0) return <p>You haven&apos;t placed any orders yet.</p>;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Your orders</h1>
      {orders.map((order) => (
        <div key={order.id} className="rounded border border-black/10 p-4 dark:border-white/10">
          <div className="flex items-center justify-between">
            <span className="font-medium">Order #{order.id}</span>
            <span className="rounded bg-black/5 px-2 py-1 text-xs uppercase dark:bg-white/10">
              {order.status}
            </span>
          </div>
          <ul className="mt-2 flex flex-col gap-1 text-sm opacity-80">
            {order.items.map((item, i) => (
              <li key={i}>
                {item.quantity} x {item.name} — {formatPrice(item.price_cents * item.quantity)}
              </li>
            ))}
          </ul>
          <p className="mt-2 font-medium">Total: {formatPrice(order.total_cents)}</p>
        </div>
      ))}
    </div>
  );
}
