# Afrisale Seller (Next.js)

Mobile-first seller dashboard. Three pages, single shared bearer token, no
auth library.

## Getting started

```
cd frontend
npm install
cp .env.local.example .env.local   # edit if backend lives elsewhere
npm run dev
```

Then open `http://localhost:3000/seller/upload?t=<SELLER_ACCESS_TOKEN>`. The
token is read from `?t=` once and cached in `sessionStorage`, so subsequent
navigations between `/seller/upload`, `/seller/catalogue` and
`/seller/orders` keep working without the query string.

## Pages

- `/seller/upload` — POST `multipart/form-data` to `/api/seller/products`
- `/seller/catalogue` — GET `/api/seller/catalogue`
- `/seller/orders` — GET `/api/seller/orders`

Auth header on every request: `Authorization: Bearer <token>`.

## Configuration

Set `NEXT_PUBLIC_API_BASE_URL` if the backend lives somewhere other than
`http://localhost:8000`. The seller backend must whitelist this app's
origin via `SELLER_BASE_URL` for CORS to pass.
