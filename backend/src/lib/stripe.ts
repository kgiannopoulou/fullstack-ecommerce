import Stripe from "stripe";
import { env } from "../config/env";

// Single shared Stripe client, used by checkout/controller.ts to both
// create Checkout Sessions and verify incoming webhook signatures.
export const stripe = new Stripe(env.stripeSecretKey);
