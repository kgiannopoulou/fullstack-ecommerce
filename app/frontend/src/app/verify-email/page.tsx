"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

// Landing page for the link in the verification email (?token=...).
function VerifyEmail() {
  const token = useSearchParams().get("token");
  const { refresh } = useAuth();
  const [state, setState] = useState<"verifying" | "done" | "failed">(token ? "verifying" : "failed");
  const [message, setMessage] = useState(token ? "" : "This link is missing its token.");
  // React's dev-mode double effect would otherwise spend the single-use
  // token on the first call and show an error from the second.
  const sent = useRef(false);

  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true;
    apiFetch("/api/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) })
      .then(async () => {
        setState("done");
        await refresh();
      })
      .catch((err) => {
        setState("failed");
        setMessage(err instanceof Error ? err.message : "Verification failed");
      });
  }, [token, refresh]);

  if (state === "verifying") return <p>Verifying your email...</p>;
  if (state === "done") {
    return (
      <p>
        Your email is verified. <Link href="/cart" className="underline">Continue to your cart</Link>.
      </p>
    );
  }
  return (
    <p className="text-red-600">
      {message} You can request a new link from your <Link href="/cart" className="underline">cart</Link>.
    </p>
  );
}

export default function VerifyEmailPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Verify email</h1>
      <Suspense>
        <VerifyEmail />
      </Suspense>
    </div>
  );
}
