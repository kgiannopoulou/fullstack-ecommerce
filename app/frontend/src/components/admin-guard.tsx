"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

// Wraps every page under /admin (see app/admin/*/page.tsx) to redirect
// non-admins away. This is a UX convenience only, NOT the real security
// boundary — a user could disable JS and never see this redirect. The
// actual enforcement is server-side: every /api/admin/* route is behind
// requireAuth + requireAdmin (backend/src/features/admin/routes.ts), so
// even if someone bypassed this guard, the API calls the admin pages make
// would still be rejected with 403.
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.push("/login?next=/admin");
    } else if (user.role !== "admin") {
      router.push("/");
    }
  }, [loading, user, router]);

  if (loading || !user || user.role !== "admin") {
    return <p>Loading...</p>;
  }

  return <>{children}</>;
}
