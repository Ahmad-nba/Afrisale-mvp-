"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/Card";
import { SellerOrder, getAuthToken, getOrders } from "@/lib/api";
import { formatPrice } from "@/lib/format";

function statusPalette(status: string): string {
  const s = (status || "").toLowerCase();
  if (s === "pending") return "bg-amber-100 text-amber-800 border-amber-200";
  if (s === "fulfilled" || s === "completed" || s === "delivered")
    return "bg-emerald-100 text-emerald-700 border-emerald-200";
  if (s === "cancelled" || s === "canceled")
    return "bg-rose-100 text-rose-700 border-rose-200";
  return "bg-slate-100 text-slate-700 border-slate-200";
}

export default function OrdersPage() {
  const [orders, setOrders] = useState<SellerOrder[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasToken, setHasToken] = useState(true);

  useEffect(() => {
    setHasToken(Boolean(getAuthToken()));
    let mounted = true;
    setLoading(true);
    getOrders()
      .then((data) => {
        if (!mounted) return;
        setOrders(data);
        setError(null);
      })
      .catch((err) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Orders
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Most recent first. Each card shows buyer details, items, and total.
        </p>
      </header>

      {!hasToken ? (
        <Card className="border-amber-200 bg-amber-50 text-amber-900">
          Missing access token. Reopen this page from the link sent to your
          WhatsApp.
        </Card>
      ) : null}

      {loading ? (
        <Card className="text-slate-500">Loading orders...</Card>
      ) : null}
      {error ? (
        <Card className="border-rose-200 bg-rose-50 text-rose-800">{error}</Card>
      ) : null}

      {orders && orders.length === 0 ? (
        <Card className="text-slate-500">No orders yet.</Card>
      ) : null}

      <div className="space-y-3">
        {(orders || []).map((order) => (
          <Card key={order.id} className="space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400">
                  Order #{order.id}
                </p>
                <h2 className="text-base font-semibold text-slate-900">
                  {order.buyer_name || "Anonymous"}
                </h2>
                {order.phone ? (
                  <p className="text-sm text-slate-500">{order.phone}</p>
                ) : null}
              </div>
              <span
                className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${statusPalette(
                  order.status,
                )}`}
              >
                {order.status || "pending"}
              </span>
            </div>

            {order.delivery_location ? (
              <p className="text-sm text-slate-600">
                <span className="font-medium text-slate-700">Deliver to:</span>{" "}
                {order.delivery_location}
              </p>
            ) : (
              <p className="text-sm italic text-slate-400">
                No delivery location captured.
              </p>
            )}

            <ul className="space-y-1 text-sm text-slate-700">
              {order.items.map((it, idx) => (
                <li
                  key={idx}
                  className="flex items-baseline justify-between gap-3"
                >
                  <span className="truncate">
                    {it.product_name || "Item"}
                    {it.size || it.color ? (
                      <span className="text-slate-500">
                        {" "}
                        ({[it.size, it.color].filter(Boolean).join(", ")})
                      </span>
                    ) : null}
                    <span className="text-slate-500"> &times; {it.quantity}</span>
                  </span>
                  <span className="shrink-0 text-slate-600">
                    {formatPrice(it.unit_price * it.quantity)}
                  </span>
                </li>
              ))}
            </ul>

            <div className="flex items-center justify-end border-t border-slate-100 pt-2">
              <span className="text-sm text-slate-500">Total</span>
              <span className="ml-3 text-lg font-bold text-slate-900">
                {formatPrice(order.total_price)}
              </span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
