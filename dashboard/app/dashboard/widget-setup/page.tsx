"use client";

import { useEffect, useState } from "react";
import { API_BASE, MyOrganization, getMyOrganization } from "@/lib/api-client";

/**
 * Turns "which org am I" into a ready-to-paste <script> tag, so an admin
 * never has to hand-assemble the embed the way earlier setup here did.
 * The org's slug and this deployment's API base are the only two values
 * that have to be correct — everything else is branding the admin can
 * edit inline before copying.
 */
export default function WidgetSetupPage() {
  const [org, setOrg] = useState<MyOrganization | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const [title, setTitle] = useState("Welcome!");
  const [subtitle, setSubtitle] = useState("Text us");
  const [agentName, setAgentName] = useState("Chat Support");
  const [greeting, setGreeting] = useState("Hi! Ask us anything.");
  const [launcherText, setLauncherText] = useState("Chat with Us");
  const [color, setColor] = useState("#0e7c66");

  useEffect(() => {
    getMyOrganization()
      .then(setOrg)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load your organization"));
  }, []);

  const widgetSrc = `${API_BASE.replace(/\/$/, "")}/oasis-chatbot-widget.js`;

  const snippet = org
    ? [
        `<script`,
        `  src="${widgetSrc}"`,
        `  data-org-slug="${org.slug}"`,
        `  data-api-base="${API_BASE}"`,
        `  data-title="${title}"`,
        `  data-subtitle="${subtitle}"`,
        `  data-agent-name="${agentName}"`,
        `  data-greeting="${greeting}"`,
        `  data-launcher-text="${launcherText}"`,
        `  data-color="${color}"`,
        `></script>`,
      ].join("\n")
    : "";

  async function copySnippet() {
    await navigator.clipboard.writeText(snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="page">
      <div className="page-head">
        <h2>Website widget</h2>
      </div>
      <p style={{ color: "var(--muted)", fontSize: 13.5, marginTop: -8, marginBottom: 20 }}>
        Paste this into your site's HTML, right before <code>&lt;/body&gt;</code>. That's the
        whole integration — one script tag, no build step.
      </p>

      {error && <div className="alert alert-error">{error}</div>}

      {!org && !error && <p className="empty">Loading…</p>}

      {org && (
        <>
          <div className="panel" style={{ padding: 20, marginBottom: 20 }}>
            <h3 style={{ marginTop: 0 }}>Customize the branding</h3>
            <div className="filters" style={{ marginBottom: 10 }}>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Header title"
                className="date-input"
              />
              <input
                value={subtitle}
                onChange={(e) => setSubtitle(e.target.value)}
                placeholder="Header subtitle"
                className="date-input"
              />
              <input
                value={agentName}
                onChange={(e) => setAgentName(e.target.value)}
                placeholder="Agent display name"
                className="date-input"
              />
            </div>
            <div className="filters" style={{ marginBottom: 10 }}>
              <input
                value={greeting}
                onChange={(e) => setGreeting(e.target.value)}
                placeholder="Opening greeting"
                className="date-input"
                style={{ minWidth: 260 }}
              />
              <input
                value={launcherText}
                onChange={(e) => setLauncherText(e.target.value)}
                placeholder="Launcher button text"
                className="date-input"
              />
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13.5 }}>
                Color
                <input
                  type="color"
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  style={{ width: 36, height: 28, padding: 0, border: "none", background: "none" }}
                />
              </label>
            </div>
          </div>

          <div className="panel" style={{ padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0 }}>Your embed code</h3>
              <button className="btn" onClick={copySnippet} type="button">
                {copied ? "Copied" : "Copy code"}
              </button>
            </div>
            <pre
              style={{
                marginTop: 14,
                padding: 14,
                background: "var(--surface)",
                borderRadius: 8,
                fontSize: 12.5,
                overflowX: "auto",
                whiteSpace: "pre",
              }}
            >
              {snippet}
            </pre>
            <p style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 0 }}>
              Workspace slug: <code>{org.slug}</code> — this is what routes a visitor's message
              to your dashboard rather than someone else's.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
