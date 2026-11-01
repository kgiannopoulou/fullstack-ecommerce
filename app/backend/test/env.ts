// Environment for the test run. Imported by both the global setup and the
// per-file setup before anything reads src/config/env.ts.
export const TEST_DATABASE_URL =
  process.env.TEST_DATABASE_URL ?? "postgres://test:test@localhost:5437/ecommerce_test";

export const WEBHOOK_SECRET = "whsec_test_secret";

Object.assign(process.env, {
  NODE_ENV: "test",
  DATABASE_URL: TEST_DATABASE_URL,
  JWT_SECRET: "test-jwt-secret",
  CORS_ORIGIN: "http://localhost:3000",
  CLIENT_URL: "http://localhost:3000",
  STRIPE_SECRET_KEY: "sk_test_fake",
  STRIPE_WEBHOOK_SECRET: WEBHOOK_SECRET,
  SMTP_URL: "",
});
