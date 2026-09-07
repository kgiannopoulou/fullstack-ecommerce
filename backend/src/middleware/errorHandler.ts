import { NextFunction, Request, Response } from "express";
import { ZodError } from "zod";

// Route handlers throw this for expected failures (404, 409, etc.) instead
// of manually calling res.status(...).json(...) everywhere — thrown errors
// are routed here by Express because every controller is async and any
// rejected promise/throw lands in this handler.
export class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Express recognizes this as an error-handling middleware specifically
// because it declares 4 parameters (err first) — it must be registered
// last, after all routes, see index.ts. `next` is required by that
// signature even though it's unused here.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function errorHandler(err: unknown, req: Request, res: Response, next: NextFunction) {
  if (err instanceof ZodError) {
    // Request body/query failed schema validation.
    return res.status(400).json({ error: "Invalid request", details: err.flatten() });
  }
  if (err instanceof HttpError) {
    return res.status(err.status).json({ error: err.message });
  }
  // Anything unexpected: log the real error server-side, but don't leak
  // internals (stack traces, SQL errors, etc.) to the client.
  console.error(err);
  return res.status(500).json({ error: "Internal server error" });
}
