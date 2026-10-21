import Link from "next/link";
import { formatPrice, Pagination, Product, SERVER_API_URL } from "@/lib/api";

// Filters the catalog understands (see backend products/controller.ts).
// They live in the URL, so every filtered page is shareable and works
// without client-side JS.
const FILTER_KEYS = ["q", "sort", "inStock", "minPrice", "maxPrice", "page"] as const;
type Filters = Partial<Record<(typeof FILTER_KEYS)[number], string>>;

const SORT_OPTIONS = [
  ["newest", "Newest"],
  ["price_asc", "Price: low to high"],
  ["price_desc", "Price: high to low"],
  ["name", "Name"],
] as const;

// This page is a React Server Component (no "use client"), so it fetches
// products directly on the server on every request — cache: "no-store"
// opts out of Next's fetch caching so stock/price edits show up immediately.
async function getProducts(filters: Filters): Promise<{ products: Product[]; pagination: Pagination | null }> {
  const url = new URL("/api/products", SERVER_API_URL);
  for (const [key, value] of Object.entries(filters)) {
    if (!value) continue;
    // Price inputs are in dollars; the API takes cents.
    const apiValue = key === "minPrice" || key === "maxPrice" ? String(Math.round(Number(value) * 100)) : value;
    url.searchParams.set(key, apiValue);
  }
  url.searchParams.set("pageSize", "12");
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) return { products: [], pagination: null };
  return res.json();
}

function pageHref(filters: Filters, page: number) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...filters, page: String(page) })) {
    if (value) params.set(key, value);
  }
  return `/?${params}`;
}

export default async function HomePage(props: PageProps<"/">) {
  // The filter form below submits as a plain GET form (no JS), landing back
  // on this same page with the filters in the URL — searchParams reads them.
  const searchParams = await props.searchParams;
  const filters: Filters = {};
  for (const key of FILTER_KEYS) {
    const value = searchParams[key];
    if (typeof value === "string" && value !== "") filters[key] = value;
  }
  const { products, pagination } = await getProducts(filters);
  const inputClass = "rounded border border-black/20 px-3 py-2 dark:border-white/20";

  return (
    <div className="flex flex-col gap-6">
      <form className="flex flex-wrap gap-2">
        <input
          type="text"
          name="q"
          defaultValue={filters.q}
          placeholder="Search products..."
          aria-label="Search products"
          className={`min-w-48 flex-1 ${inputClass}`}
        />
        <select name="sort" defaultValue={filters.sort ?? "newest"} aria-label="Sort by" className={inputClass}>
          {SORT_OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <input
          type="number"
          name="minPrice"
          min={0}
          step="0.01"
          defaultValue={filters.minPrice}
          placeholder="Min $"
          aria-label="Minimum price"
          className={`w-24 ${inputClass}`}
        />
        <input
          type="number"
          name="maxPrice"
          min={0}
          step="0.01"
          defaultValue={filters.maxPrice}
          placeholder="Max $"
          aria-label="Maximum price"
          className={`w-24 ${inputClass}`}
        />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="inStock" value="true" defaultChecked={filters.inStock === "true"} />
          In stock only
        </label>
        <button type="submit" className="rounded bg-black px-4 py-2 text-white dark:bg-white dark:text-black">
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
              <span className="text-sm opacity-70">
                {formatPrice(product.price_cents)}
                {product.stock === 0 && " · Sold out"}
              </span>
            </Link>
          ))}
        </div>
      )}

      {pagination && pagination.totalPages > 1 && (
        <nav aria-label="Pages" className="flex items-center justify-center gap-4 text-sm">
          {pagination.page > 1 ? (
            <Link href={pageHref(filters, pagination.page - 1)} className="underline">
              Previous
            </Link>
          ) : (
            <span className="opacity-40">Previous</span>
          )}
          <span>
            Page {pagination.page} of {pagination.totalPages} ({pagination.total} products)
          </span>
          {pagination.page < pagination.totalPages ? (
            <Link href={pageHref(filters, pagination.page + 1)} className="underline">
              Next
            </Link>
          ) : (
            <span className="opacity-40">Next</span>
          )}
        </nav>
      )}
    </div>
  );
}
