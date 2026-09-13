import { NextFunction, Request, Response } from "express";

// Must run after requireAuth (see admin/routes.ts) so req.user is already
// populated. Checks the role embedded in the JWT — see the caveat about
// stale roles in middleware/auth.ts.
export function requireAdmin(req: Request, res: Response, next: NextFunction) {
  if (req.user?.role !== "admin") {
    return res.status(403).json({ error: "Admin access required" });
  }
  next();
}
