import { Router } from "express";
import { attachUserIfPresent } from "../../middleware/auth";
import { login, logout, me, signup } from "./controller";

export const authRouter = Router();

authRouter.post("/signup", signup);
authRouter.post("/login", login);
authRouter.post("/logout", logout);
// Only /me needs to read the cookie if present; signup/login/logout don't
// care about an existing session.
authRouter.get("/me", attachUserIfPresent, me);
