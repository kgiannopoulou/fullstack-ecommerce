// Inserts sample products and two demo accounts for local development and
// the hosted demo. Not run automatically — invoked explicitly via
// `npm run db:seed`. Safe to re-run: existing rows are left alone.
import bcrypt from "bcryptjs";
import { pool } from "./pool";

const products = [
  ["Wireless Headphones", "Over-ear headphones with active noise cancellation.", 9999, 25],
  ["Mechanical Keyboard", "Tactile mechanical keyboard with hot-swappable switches.", 12999, 15],
  ["Ceramic Coffee Mug", "350ml matte-finish ceramic mug, dishwasher safe.", 1499, 100],
  ["Canvas Backpack", "Water-resistant canvas backpack with laptop sleeve.", 5999, 40],
  ["USB-C Hub", "7-in-1 hub: HDMI, SD card, 3x USB-A and 100W pass-through charging.", 3999, 60],
  ["Desk Lamp", "Dimmable LED desk lamp with adjustable colour temperature.", 4499, 30],
  ["Notebook Set", "Three A5 dotted notebooks, 120gsm paper.", 1799, 80],
  ["Water Bottle", "750ml insulated steel bottle, keeps drinks cold for 24 hours.", 2499, 70],
  ["Wireless Mouse", "Silent-click ergonomic mouse with USB-C charging.", 2999, 45],
  ["Laptop Stand", "Aluminium stand with six height settings.", 3499, 35],
  ["Phone Charger", "30W USB-C fast charger.", 1999, 90],
  ["Bluetooth Speaker", "Portable waterproof speaker with 12-hour battery.", 6999, 20],
  ["Webcam", "1080p webcam with privacy shutter and dual microphones.", 5499, 25],
  ["Cable Organizer", "Silicone cable clips, pack of 10.", 899, 150],
  // Exactly one in stock, to try the "last unit" race by hand.
  ["Limited Edition Print", "Signed art print, 1 of 1.", 14999, 1],
  // Sold out, to see the out-of-stock filter and UI.
  ["Vintage Camera", "Restored 35mm film camera.", 24999, 0],
] as const;

function slugify(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

// Demo logins, documented in the README. Both are pre-verified so the
// checkout flow works straight away.
export const DEMO_ACCOUNTS = [
  { email: "admin@demo.test", password: "demo-admin-pass", role: "admin" },
  { email: "customer@demo.test", password: "demo-customer-pass", role: "user" },
] as const;

async function main() {
  for (const [name, description, priceCents, stock] of products) {
    const slug = slugify(name);
    // ON CONFLICT DO NOTHING makes this idempotent: re-running the seed
    // script after products already exist just skips them instead of
    // erroring on the unique slug constraint.
    await pool.query(
      `INSERT INTO products (name, slug, description, price_cents, image_url, stock)
       VALUES ($1, $2, $3, $4, $5, $6)
       ON CONFLICT (slug) DO NOTHING`,
      [name, slug, description, priceCents, `https://placehold.co/600x400?text=${encodeURIComponent(name)}`, stock]
    );
  }

  for (const account of DEMO_ACCOUNTS) {
    await pool.query(
      `INSERT INTO users (email, password_hash, role, email_verified_at)
       VALUES ($1, $2, $3, now())
       ON CONFLICT (email) DO NOTHING`,
      [account.email, await bcrypt.hash(account.password, 10), account.role]
    );
  }

  console.log(`Seeded ${products.length} products and ${DEMO_ACCOUNTS.length} demo accounts.`);
  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
