import { createApp } from "./app";
import { env } from "./config/env";
import { startReservationSweeper } from "./features/checkout/orderLifecycle";

// Server entry point: builds the app (see app.ts) and starts listening.
const app = createApp();

app.listen(env.port, () => {
  console.log(`Backend listening on http://localhost:${env.port}`);
  // Once a minute, cancel abandoned checkouts and return their reserved
  // stock (see features/checkout/orderLifecycle.ts).
  startReservationSweeper();
});
