"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CurrentUser, clearToken, getCurrentUser, getToken } from "@/lib/api-client";

/**
 * Guards the whole /platform section.
 *
 * Deliberately separate from /dashboard's layout rather than sharing it:
 * that layout's sidebar (Conversations, Tickets, Users) describes one
 * organization's day-to-day work, none of which applies to a platform
 * owner who belongs to no organization at all. Two audiences, two shells.
 */
export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<CurrentUser | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    const current = getCurrentUser();
    if (!current?.roles.includes("super_admin")) {
      // Someone without the role reached this URL directly. The API
      // would refuse every call anyway (403), but bouncing them here
      // means they see their own dashboard instead of a screen that
      // fails to load.
      router.push("/dashboard");
      return;
    }
    setMe(current);
    setReady(true);
  }, [router]);

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  if (!ready) return null;

  return (
    <div className="platform-shell">
      <header className="platform-header">
        <div className="platform-header-title">
          <strong>Chat Support</strong>
          <span>Platform</span>
        </div>
        <button className="btn btn-quiet" onClick={handleLogout}>
          Log out
        </button>
      </header>
      <main className="platform-main">{children}</main>
    </div>
  );
}
