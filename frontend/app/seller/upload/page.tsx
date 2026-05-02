"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { Field, inputClass, textareaClass } from "@/components/Field";
import { createProduct, getAuthToken } from "@/lib/api";

interface FlashMessage {
  kind: "success" | "error";
  text: string;
}

export default function UploadPage() {
  const formRef = useRef<HTMLFormElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const [flash, setFlash] = useState<FlashMessage | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [hasToken, setHasToken] = useState(true);

  useEffect(() => {
    setHasToken(Boolean(getAuthToken()));
  }, []);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (submitting) return;
    setFlash(null);
    setSubmitting(true);
    try {
      const form = formRef.current;
      if (!form) return;
      const data = new FormData(form);
      // Drop empty image inputs so backend treats them as no-image rather than
      // an empty UploadFile.
      const file = data.get("image");
      if (file instanceof File && file.size === 0) {
        data.delete("image");
      }
      const result = await createProduct(data);
      const note = result.image_error
        ? `Saved "${result.name}" but image upload failed: ${result.image_error}`
        : `Saved "${result.name}" (id ${result.id}).`;
      setFlash({ kind: "success", text: note });
      form.reset();
      nameInputRef.current?.focus();
    } catch (err) {
      setFlash({
        kind: "error",
        text: err instanceof Error ? err.message : "Could not save product.",
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Add a product
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Quick add: name, price, stock, optional photo. Submit to save and
          immediately enter the next product.
        </p>
      </header>

      {!hasToken ? (
        <Card className="border-amber-200 bg-amber-50 text-amber-900">
          Missing seller access token. Open this page from the link sent to
          your WhatsApp (it ends with <code className="font-mono">?t=...</code>).
        </Card>
      ) : null}

      {flash ? (
        <Card
          className={
            flash.kind === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-rose-200 bg-rose-50 text-rose-800"
          }
        >
          {flash.text}
        </Card>
      ) : null}

      <form ref={formRef} onSubmit={onSubmit} className="space-y-4">
        <Card className="space-y-4">
          <Field label="Product name" htmlFor="name" required>
            <input
              ref={nameInputRef}
              id="name"
              name="name"
              type="text"
              required
              autoComplete="off"
              autoFocus
              maxLength={200}
              className={inputClass}
              placeholder="e.g. Classic Tee 5-Pack"
            />
          </Field>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Price" htmlFor="price" hint="Whole number" required>
              <input
                id="price"
                name="price"
                type="number"
                inputMode="numeric"
                min={0}
                required
                className={inputClass}
                placeholder="25000"
              />
            </Field>
            <Field
              label="Stock quantity"
              htmlFor="stock_quantity"
              hint="Available units"
              required
            >
              <input
                id="stock_quantity"
                name="stock_quantity"
                type="number"
                inputMode="numeric"
                min={0}
                required
                className={inputClass}
                placeholder="20"
              />
            </Field>
          </div>

          <Field label="Description" htmlFor="description">
            <textarea
              id="description"
              name="description"
              rows={3}
              maxLength={1000}
              className={textareaClass}
              placeholder="One or two sentences a buyer will read."
            />
          </Field>

          <Field label="Image" htmlFor="image" hint="JPG / PNG, optional">
            <input
              id="image"
              name="image"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
              className="block w-full text-sm text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-brand file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-brand-dark"
            />
          </Field>
        </Card>

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <Button
            type="reset"
            variant="secondary"
            disabled={submitting}
            onClick={() => setFlash(null)}
          >
            Clear
          </Button>
          <Button type="submit" disabled={submitting || !hasToken}>
            {submitting ? "Saving..." : "Save product"}
          </Button>
        </div>
      </form>
    </div>
  );
}
