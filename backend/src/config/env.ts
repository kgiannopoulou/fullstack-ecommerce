// Loads backend/.env into process.env before anything below reads it.
import "dotenv/config";

// Fail fast at startup if a required var is missing, instead of letting
// something downstream (e.g. a JWT sign call) blow up with a cryptic error.
function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

// Central place the rest of the app reads config from, so no other file
// touches process.env directly.
export const env = {
  port: Number(process.env.PORT ?? 4000),
  databaseUrl: required("DATABASE_URL"),
  jwtSecret: required("JWT_SECRET"),
  corsOrigin: required("CORS_ORIGIN"),
  clientUrl: required("CLIENT_URL"),
  stripeSecretKey: required("STRIPE_SECRET_KEY"),
  stripeWebhookSecret: required("STRIPE_WEBHOOK_SECRET"),
};
