import { notFound } from "next/navigation";
import { API_URL, formatPrice, Product } from "@/lib/api";
import { AddToCartButton } from "@/components/add-to-cart-button";

// Server Component, same pattern as the homepage: fetched fresh per request.
async function getProduct(slug: string): Promise<Product | null> {
  const res = await fetch(new URL(`/api/products/${slug}`, API_URL), { cache: "no-store" });
  if (!res.ok) return null;
  const data = await res.json();
  return data.product;
}

export default async function ProductPage(props: PageProps<"/products/[slug]">) {
  const { slug } = await props.params;
  const product = await getProduct(slug);
  // Renders Next's not-found page for an unknown slug instead of crashing
  // or showing a blank product.
  if (!product) notFound();

  return (
    <div className="grid gap-8 sm:grid-cols-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={product.image_url ?? "https://placehold.co/600x400"}
        alt={product.name}
        className="w-full rounded object-cover"
      />
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold">{product.name}</h1>
        <p className="text-lg">{formatPrice(product.price_cents)}</p>
        <p className="opacity-80">{product.description}</p>
        <p className="text-sm opacity-60">{product.stock} in stock</p>
        <AddToCartButton product={product} />
      </div>
    </div>
  );
}
