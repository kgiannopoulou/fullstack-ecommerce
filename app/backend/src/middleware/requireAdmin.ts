import { NextFunction, Request, Response } from "express";
import { HttpError } from "./errorHandler";

// Must run after requireAuth (see admin/routes.ts) so req.user is already
// populated. The role is read from the database on every request, so a
// promotion or demotion applies immediately.
export function requireAdmin(req: Request, _res: Response, next: NextFunction) {
  if (req.user?.role !== "admin") {
    throw new HttpError(403, "Admin access required");
  }
  next();
}
