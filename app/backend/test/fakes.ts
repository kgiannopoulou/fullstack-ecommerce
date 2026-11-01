import Stripe from "stripe";
import { vi } from "vitest";
import type { Mail } from "../src/lib/mailer";

// --- Stripe -----------------------------------------------------------------
// A stand-in for the Stripe API: sessions live in a Map, refunds are
// recorded. Webhook signing/verification uses the real Stripe library, so
// the signature check in the webhook handler is exercised for real.

type FakeSession = {
  id: string;
  url: string;
  status: "open" | "complete" | "expired";
  payment_status: "paid" | "unpaid";
  payment_intent: string | null;
  metadata: Record<string, string>;
};

export const sessions = new Map<string, FakeSession>();

const realWebhooks = new Stripe("sk_test_fake").webhooks;

export const fakeStripe = {
  webhooks: realWebhooks,
  checkout: {
    sessions: {
      create: vi.fn(),
      retrieve: vi.fn(),
      expire: vi.fn(),
    },
  },
  refunds: { create: vi.fn() },
};

export function resetFakeStripe() {
  sessions.clear();
  fakeStripe.checkout.sessions.create.mockReset().mockImplementation(async (params) => {
    const id = `cs_test_${params.metadata.orderId}`;
    const session: FakeSession = {
      id,
      url: `https://checkout.stripe.test/${id}`,
      status: "open",
      payment_status: "unpaid",
      payment_intent: null,
      metadata: params.metadata,
    };
    sessions.set(id, session);
    return session;
  });
  fakeStripe.checkout.sessions.retrieve.mockReset().mockImplementation(async (id: string) => {
    const session = sessions.get(id);
    if (!session) throw new Error(`No such session: ${id}`);
    return { ...session };
  });
  fakeStripe.checkout.sessions.expire.mockReset().mockImplementation(async (id: string) => {
    const session = sessions.get(id);
    if (!session || session.status !== "open") throw new Error("Session is not open");
    session.status = "expired";
    return { ...session };
  });
  fakeStripe.refunds.create.mockReset().mockImplementation(async () => ({ id: "re_test" }));
}

// Simulates the customer paying on Stripe's hosted page.
export function completeSession(sessionId: string, paymentIntent = `pi_${sessionId}`) {
  const session = sessions.get(sessionId)!;
  Object.assign(session, { status: "complete", payment_status: "paid", payment_intent: paymentIntent });
  return session;
}

// --- Mail -------------------------------------------------------------------

export const outbox: Mail[] = [];

export const fakeSendMail = vi.fn(async (mail: Mail) => {
  outbox.push(mail);
});

// Pulls the ?token= value out of the last link sent to `to`.
export function lastTokenSentTo(to: string, path: "verify-email" | "reset-password") {
  const mail = [...outbox].reverse().find((m) => m.to === to && m.text.includes(`/${path}?token=`));
  if (!mail) throw new Error(`No ${path} email sent to ${to}`);
  return new URL(mail.text.match(/https?:\/\/\S+/)![0]).searchParams.get("token")!;
}
