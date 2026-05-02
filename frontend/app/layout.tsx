import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Afrisale Seller",
  description: "Manage your Afrisale catalogue and orders.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
            <Link
              href="/seller/upload"
              className="text-base font-semibold tracking-tight text-brand"
            >
              Afrisale Seller
            </Link>
            <nav className="flex items-center gap-4 text-sm font-medium text-slate-600">
              <Link href="/seller/upload" className="hover:text-brand">
                Upload
              </Link>
              <Link href="/seller/catalogue" className="hover:text-brand">
                Catalogue
              </Link>
              <Link href="/seller/orders" className="hover:text-brand">
                Orders
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-3xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
