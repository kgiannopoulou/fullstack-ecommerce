// The signed-in user, as loaded from the database on every request by
// requireAuth (see middleware/auth.ts) and reused as the type of req.user
// everywhere a route needs the current user's id/email/role.
export interface AuthUser {
  id: number;
  email: string;
  role: "user" | "admin";
  emailVerified: boolean;
}

// Augments Express's built-in Request type so `req.user` / `req.id`
// type-check in every route/controller without each file redeclaring them.
declare global {
  namespace Express {
    interface Request {
      user?: AuthUser;
      id: string;
    }
  }
}
