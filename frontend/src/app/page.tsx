import Link from "next/link";
import { API_URL, formatPrice, Product } from "@/lib/api";

// This page is a React Server Component (no "use client"), so it fetches
// products directly on the server on every request — cache: "no-store"
// opts out of Next's fetch caching so stock/price edits show up immediately.
async function getProducts(q: string): Promise<Product[]> {
  const url = new URL("/api/products", API_URL);
  if (q) url.searchParams.set("q", q);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) return [];
  const data = await res.json();
  return data.products;
}

export default async function HomePage(props: PageProps<"/">) {
  // The search box below submits as a plain GET form (no JS), landing back
  // on this same page with ?q=<term> in the URL — searchParams reads it.
  const searchParams = await props.searchParams;
  const q = typeof searchParams.q === "string" ? searchParams.q : "";
  const products = await getProducts(q);

  return (
    <div className="flex flex-col gap-6">
      <form className="flex gap-2">
        <input
          type="text"
          name="q"
          defaultValue={q}
          placeholder="Search products..."
          className="flex-1 rounded border border-black/20 px-3 py-2 dark:border-white/20"
        />
        <button
          type="submit"
          className="rounded bg-black px-4 py-2 text-white dark:bg-white dark:text-black"
        >
          Search
        </button>
      </form>

      {products.length === 0 ? (
        <p className="text-sm opacity-70">No products found.</p>
      ) : (
        <div className="grid grid-cols-2 gap-6 sm:grid-cols-3">
          {products.map((product) => (
            <Link
              key={product.id}
              href={`/products/${product.slug}`}
              className="flex flex-col gap-2 rounded border border-black/10 p-3 hover:border-black/30 dark:border-white/10 dark:hover:border-white/30"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={product.image_url ?? "https://placehold.co/600x400"}
                alt={product.name}
                className="aspect-video w-full rounded object-cover"
              />
              <span className="font-medium">{product.name}</span>
              <span className="text-sm opacity-70">{formatPrice(product.price_cents)}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
