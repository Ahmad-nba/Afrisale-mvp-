"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/Card";
import {
  CatalogueItem,
  getAuthToken,
  getCatalogue,
} from "@/lib/api";
import { formatPrice, stockBadgeColor, stockBadgeText } from "@/lib/format";

export default function CataloguePage() {
  const [items, setItems] = useState<CatalogueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasToken, setHasToken] = useState(true);

  useEffect(() => {
    setHasToken(Boolean(getAuthToken()));
    let mounted = true;
    setLoading(true);
    getCatalogue()
      .then((data) => {
        if (!mounted) return;
        setItems(data);
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
          Catalogue
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Read-only view of every product currently visible to buyers in the
          chat.
        </p>
      </header>

      {!hasToken ? (
        <Card className="border-amber-200 bg-amber-50 text-amber-900">
          Missing access token. Reopen this page from the link sent to your
          WhatsApp.
        </Card>
      ) : null}

      {loading ? (
        <Card className="text-slate-500">Loading catalogue...</Card>
      ) : null}
      {error ? (
        <Card className="border-rose-200 bg-rose-50 text-rose-800">{error}</Card>
      ) : null}

      {items && items.length === 0 ? (
        <Card className="text-slate-500">
          No products yet. Use Upload to add your first one.
        </Card>
      ) : null}

      <div className="space-y-3">
        {(items || []).map((item) => (
          <Card key={item.id} className="flex gap-4">
            <div className="h-24 w-24 shrink-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
              {item.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={item.image_url}
                  alt={item.name}
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-xs text-slate-400">
                  No photo
                </div>
              )}
            </div>
            <div className="flex min-w-0 flex-1 flex-col justify-between">
              <div>
                <h2 className="truncate text-base font-semibold text-slate-900">
                  {item.name}
                </h2>
                {item.description ? (
                  <p className="mt-1 line-clamp-2 text-sm text-slate-500">
                    {item.description}
                  </p>
                ) : null}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="text-base font-bold text-slate-900">
                  {formatPrice(item.price)}
                </span>
                <span
                  className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${stockBadgeColor(
                    item.stock_label,
                  )}`}
                >
                  {stockBadgeText(item.stock_label, item.stock_total)}
                </span>
                {item.variants_count > 1 ? (
                  <span className="text-xs text-slate-500">
                    {item.variants_count} variants
                  </span>
                ) : null}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
