import { randomUUID } from "node:crypto";
import { NextFunction, Request, Response } from "express";

// Tags every request with an id, echoed back in the X-Request-Id header and
// in every error body, so a user-reported error can be matched to the log
// line printed for it. An incoming X-Request-Id (e.g. from a proxy) is kept
// if it looks sane.
export function requestId(req: Request, res: Response, next: NextFunction) {
  const incoming = req.header("x-request-id");
  req.id = incoming && /^[\w-]{1,64}$/.test(incoming) ? incoming : randomUUID();
  res.setHeader("X-Request-Id", req.id);
  next();
}
