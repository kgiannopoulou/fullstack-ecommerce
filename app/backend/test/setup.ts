import "./env";
import { afterAll, beforeEach, vi } from "vitest";
import { fakeSendMail, outbox, resetFakeStripe } from "./fakes";

// Every test file talks to the fake Stripe and the in-memory outbox, never
// to the network.
vi.mock("../src/lib/stripe", async () => ({ stripe: (await import("./fakes")).fakeStripe }));
vi.mock("../src/lib/mailer", async () => ({ sendMail: (await import("./fakes")).fakeSendMail }));

beforeEach(async () => {
  const { resetDb } = await import("./helpers");
  await resetDb();
  resetFakeStripe();
  outbox.length = 0;
  fakeSendMail.mockClear();
});

afterAll(async () => {
  const { pool } = await import("../src/db/pool");
  await pool.end();
});
