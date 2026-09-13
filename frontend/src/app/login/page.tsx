import { Suspense } from "react";
import { AuthForm } from "@/components/auth-form";

export default function LoginPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Log in</h1>
      {/* Suspense is required here because AuthForm calls useSearchParams()
          (to read ?next=...), which opts the component out of static
          rendering in the App Router. */}
      <Suspense>
        <AuthForm mode="login" />
      </Suspense>
    </div>
  );
}
