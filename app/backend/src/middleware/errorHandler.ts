import { NextFunction, Request, Response } from "express";
import { ZodError } from "zod";

// Every error response from this API has the same shape (documented in
// docs/API.md), so the frontend and any other client only need one parser:
//
//   { "error": { "code": "OUT_OF_STOCK", "message": "...", "details"?: [...], "requestId": "..." } }
//
// `code` is a stable machine-readable identifier; `message` is safe to show
// to a user; `details` is only present for validation errors.
export type ErrorCode =
  | "VALIDATION_FAILED"
  | "INVALID_JSON"
  | "UNAUTHENTICATED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "CONFLICT"
  | "RATE_LIMITED"
  | "INVALID_CREDENTIALS"
  | "EMAIL_TAKEN"
  | "EMAIL_NOT_VERIFIED"
  | "INVALID_TOKEN"
  | "OUT_OF_STOCK"
  | "INVALID_TRANSITION"
  | "PAYMENT_PROVIDER_ERROR"
  | "INTERNAL";

const DEFAULT_CODE: Record<number, ErrorCode> = {
  400: "VALIDATION_FAILED",
  401: "UNAUTHENTICATED",
  403: "FORBIDDEN",
  404: "NOT_FOUND",
  409: "CONFLICT",
  429: "RATE_LIMITED",
  502: "PAYMENT_PROVIDER_ERROR",
};

// Route handlers throw this for expected failures (404, 409, etc.) instead
// of manually calling res.status(...).json(...) everywhere — thrown errors
// are routed here by Express because every controller is async and any
// rejected promise/throw lands in this handler.
export class HttpError extends Error {
  public code: ErrorCode;
  constructor(public status: number, message: string, code?: ErrorCode) {
    super(message);
    this.code = code ?? DEFAULT_CODE[status] ?? "INTERNAL";
  }
}

export function sendError(
  req: Request,
  res: Response,
  status: number,
  code: ErrorCode,
  message: string,
  details?: { path: string; message: string }[]
) {
  return res.status(status).json({
    error: { code, message, ...(details ? { details } : {}), requestId: req.id },
  });
}

// Express recognizes this as an error-handling middleware specifically
// because it declares 4 parameters (err first) — it must be registered
// last, after all routes, see app.ts. `next` is required by that
// signature even though it's unused here.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function errorHandler(err: unknown, req: Request, res: Response, next: NextFunction) {
  if (err instanceof ZodError) {
    // Request body/query/params failed schema validation.
    const details = err.issues.map((issue) => ({
      path: issue.path.join("."),
      message: issue.message,
    }));
    return sendError(req, res, 400, "VALIDATION_FAILED", "Invalid request", details);
  }
  if (err instanceof HttpError) {
    return sendError(req, res, err.status, err.code, err.message);
  }
  // express.json() throws this for a malformed body.
  if (err instanceof SyntaxError && (err as { type?: string }).type === "entity.parse.failed") {
    return sendError(req, res, 400, "INVALID_JSON", "Request body is not valid JSON");
  }
  // Constraint violations from Postgres, e.g. a duplicate product slug or
  // deleting a product that past orders still reference.
  const pgCode = (err as { code?: unknown } | null)?.code;
  if (pgCode === "23505") {
    return sendError(req, res, 409, "CONFLICT", "A record with these values already exists");
  }
  if (pgCode === "23503") {
    return sendError(req, res, 409, "CONFLICT", "This record is still referenced by other records");
  }
  // Anything unexpected: log the real error server-side, but don't leak
  // internals (stack traces, SQL errors, etc.) to the client.
  console.error(`[${req.id}]`, err);
  return sendError(req, res, 500, "INTERNAL", "Internal server error");
}

export function notFoundHandler(req: Request, res: Response) {
  return sendError(req, res, 404, "NOT_FOUND", `No route for ${req.method} ${req.path}`);
}
