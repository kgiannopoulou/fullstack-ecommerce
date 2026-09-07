// Shape of the JWT payload (see middleware/auth.ts), reused as the type of
// req.user everywhere a route needs the current user's id/email/role.
export interface AuthUser {
  id: number;
  email: string;
  role: "user" | "admin";
}

// Augments Express's built-in Request type so `req.user` type-checks in
// every route/controller without each file redeclaring it.
declare global {
  namespace Express {
    interface Request {
      user?: AuthUser;
    }
  }
}
