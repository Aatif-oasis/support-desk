"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { CurrentUser, clearToken, getCurrentUser, getToken } from "@/lib/api-client";
import { useAgentSocket } from "@/lib/use-agent-socket";
import {
  askForNotifications,
  bumpTitleCount,
  clearTitleCount,
  isMuted,
  notificationPermission,
  playMessageBlip,
  playNewVisitorChime,
  primeAudio,
  setMuted,
  showNotification,
} from "@/lib/notify";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [muted, setMutedState] = useState(false);
  const [permission, setPermission] = useState("default");
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    const user = getCurrentUser();
    // A super_admin has no organization — this whole screen (agent
    // socket, conversation list) is scoped to one, so sending them here
    // is a dead end, not a lesser view. Platform is where they belong.
    if (user?.roles.includes("super_admin")) {
      router.push("/platform");
      return;
    }
    setMe(user);
    setMutedState(isMuted());
    setPermission(notificationPermission());
    setReady(true);
  }, [router]);

  useEffect(() => {
    // Audio can only start from a user gesture, and a WebSocket event is
    // not one. Any click anywhere unlocks it, long before a visitor turns
    // up.
    const unlock = () => primeAudio();
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });

    // Coming back to the tab is the agent seeing it — drop the counter.
    const onVisible = () => {
      if (document.visibilityState === "visible") clearTitleCount();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  function flash(message: string) {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 6000);
  }

  // Alerts live in the layout rather than the conversation list so an
  // agent hears a new visitor arrive while they're on Tickets or Users
  // — the whole point is catching someone who isn't watching the inbox.
  useAgentSocket((event) => {
    if (event.type === "new_conversation") {
      playNewVisitorChime();
      bumpTitleCount();
      showNotification("New visitor", "Someone just started a chat on your website.");
      flash("New visitor just started a chat.");
    }
    if (event.type === "new_message") {
      const message = event.message as { sender_type?: string } | undefined;
      // An agent's own reply echoes back over the socket; only a customer
      // saying something is worth a sound.
      if (message?.sender_type === "customer") {
        playMessageBlip();
        bumpTitleCount();
      }
    }
  });

  if (!ready) return null;

  // Only admins can manage people, so only admins are shown the door.
  const canManageUsers = !!me?.roles.includes("org_admin");

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="wordmark">Chat Support</div>
        <div className="wordmark-sub">Live chat console</div>

        <Link
          href="/dashboard"
          className="nav-link"
          aria-current={pathname === "/dashboard" ? "page" : undefined}
        >
          Conversations
        </Link>

        <Link
          href="/dashboard/tickets"
          className="nav-link"
          aria-current={pathname?.startsWith("/dashboard/tickets") ? "page" : undefined}
        >
          Tickets
        </Link>

        {canManageUsers && (
          <Link
            href="/dashboard/users"
            className="nav-link"
            aria-current={pathname?.startsWith("/dashboard/users") ? "page" : undefined}
          >
            Users
          </Link>
        )}

        {canManageUsers && (
          <Link
            href="/dashboard/widget-setup"
            className="nav-link"
            aria-current={pathname?.startsWith("/dashboard/widget-setup") ? "page" : undefined}
          >
            Website Widget
          </Link>
        )}

        {canManageUsers && (
          <Link
            href="/dashboard/integrations"
            className="nav-link"
            aria-current={pathname?.startsWith("/dashboard/integrations") ? "page" : undefined}
          >
            Integrations
          </Link>
        )}

        <div className="sidebar-foot">
          <button
            className="nav-link alert-toggle"
            onClick={() => {
              const next = !muted;
              setMuted(next);
              setMutedState(next);
              if (!next) {
                primeAudio();
                playNewVisitorChime();
              }
            }}
            title={muted ? "Turn the new-visitor sound back on" : "Silence the new-visitor sound"}
          >
            {muted ? "Sound off" : "Sound on"}
          </button>

          {permission === "default" && (
            <button
              className="nav-link alert-toggle"
              onClick={async () => setPermission(await askForNotifications())}
              title="Show a desktop notification when this tab is in the background"
            >
              Enable alerts
            </button>
          )}

          {me && (
            <div className="who">
              <strong>{me.roles.includes("org_admin") ? "Administrator" : "Agent"}</strong>
              signed in
            </div>
          )}
          <button
            className="btn btn-ghost-light"
            onClick={() => {
              clearToken();
              router.push("/login");
            }}
          >
            Log out
          </button>
        </div>
      </nav>

      <main className="main">{children}</main>

      {toast && (
        <div className="toast" role="status">
          <span className="toast-dot" aria-hidden="true" />
          {toast}
          <Link href="/dashboard" className="toast-link" onClick={() => setToast(null)}>
            Open inbox
          </Link>
        </div>
      )}
    </div>
  );
}
