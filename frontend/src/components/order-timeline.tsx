// Renders an order's audit trail (GET /api/orders/:id or
// /api/admin/orders/:id/history). Admin entries also say who did it.
export type OrderEvent = {
  type: string;
  from_status: string | null;
  to_status: string | null;
  created_at: string;
  actor?: string;
  actor_email?: string | null;
};

const LABELS: Record<string, string> = {
  created: "Order placed, stock reserved",
  checkout_session_created: "Payment page opened",
  paid: "Payment received",
  stock_reacquired: "Stock re-reserved after a late payment",
  stock_released: "Reserved stock returned",
  refunded: "Refunded automatically (item no longer available)",
  cancelled: "Cancelled",
  shipped: "Shipped",
};

export function OrderTimeline({ events }: { events: OrderEvent[] }) {
  return (
    <ol className="flex flex-col gap-1 border-l border-black/10 pl-4 text-sm dark:border-white/10">
      {events.map((event, i) => (
        <li key={i}>
          <span className="opacity-60">{new Date(event.created_at).toLocaleString()}</span>{" "}
          {LABELS[event.type] ?? event.type}
          {event.actor && (
            <span className="opacity-60">
              {" "}
              · {event.actor}
              {event.actor_email ? ` (${event.actor_email})` : ""}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}
