import { pool } from "./pool";

const products = [
  {
    name: "Wireless Headphones",
    slug: "wireless-headphones",
    description: "Over-ear headphones with active noise cancellation.",
    price_cents: 9999,
    image_url: "https://placehold.co/600x400?text=Headphones",
    stock: 25,
  },
  {
    name: "Mechanical Keyboard",
    slug: "mechanical-keyboard",
    description: "Tactile mechanical keyboard with hot-swappable switches.",
    price_cents: 12999,
    image_url: "https://placehold.co/600x400?text=Keyboard",
    stock: 15,
  },
  {
    name: "Ceramic Coffee Mug",
    slug: "ceramic-coffee-mug",
    description: "350ml matte-finish ceramic mug, dishwasher safe.",
    price_cents: 1499,
    image_url: "https://placehold.co/600x400?text=Mug",
    stock: 100,
  },
  {
    name: "Canvas Backpack",
    slug: "canvas-backpack",
    description: "Water-resistant canvas backpack with laptop sleeve.",
    price_cents: 5999,
    image_url: "https://placehold.co/600x400?text=Backpack",
    stock: 40,
  },
];

async function main() {
  for (const product of products) {
    await pool.query(
      `INSERT INTO products (name, slug, description, price_cents, image_url, stock)
       VALUES ($1, $2, $3, $4, $5, $6)
       ON CONFLICT (slug) DO NOTHING`,
      [
        product.name,
        product.slug,
        product.description,
        product.price_cents,
        product.image_url,
        product.stock,
      ]
    );
  }
  console.log(`Seeded ${products.length} products.`);
  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
