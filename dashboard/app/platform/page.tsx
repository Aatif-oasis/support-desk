"use client";

import { useEffect, useState } from "react";
import {
  Organization,
  createOrganization,
  listOrganizations,
  setOrganizationStatus,
} from "@/lib/api-client";
import { fullTimestamp } from "@/lib/format-time";

const STATUS_LABEL: Record<string, string> = {
  active: "active",
  suspended: "suspended",
  cancelled: "cancelled",
};

export default function PlatformPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // New-client form.
  const [showForm, setShowForm] = useState(false);
  const [orgName, setOrgName] = useState("");
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [creating, setCreating] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const page = await listOrganizations();
      setOrgs(page.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load organizations");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const org = await createOrganization({
        organization_name: orgName,
        admin_full_name: adminName,
        admin_email: adminEmail,
        admin_password: adminPassword,
      });
      setNotice(
        `${org.name} is live. Widget slug: ${org.slug}. Give ${adminEmail} their password to sign in.`
      );
      setOrgName("");
      setAdminName("");
      setAdminEmail("");
      setAdminPassword("");
      setShowForm(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the organization");
    } finally {
      setCreating(false);
    }
  }

  async function handleStatus(org: Organization, status: string) {
    if (
      status === "suspended" &&
      !confirm(`Suspend ${org.name}? Their agents and widget stop working until reactivated.`)
    ) {
      return;
    }
    setBusyId(org.id);
    setError(null);
    try {
      await setOrganizationStatus(org.id, status);
      setNotice(`${org.name} is now ${status}.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update that organization");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h2>Organizations</h2>
        <button className="btn" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancel" : "New organization"}
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-info">{notice}</div>}

      {showForm && (
        <form className="panel" style={{ padding: 20, marginBottom: 20 }} onSubmit={handleCreate}>
          <p style={{ marginTop: 0, color: "var(--muted)", fontSize: 13.5 }}>
            Creates the organization and its first admin in one step. That admin can invite
            agents and manage everything about their own workspace from here on — you will not
            need to touch this again for them.
          </p>

          <div className="filters" style={{ marginBottom: 10 }}>
            <input
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="Organization name"
              required
              style={{ minWidth: 220 }}
              className="date-input"
            />
            <input
              value={adminName}
              onChange={(e) => setAdminName(e.target.value)}
              placeholder="Admin full name"
              required
              style={{ minWidth: 200 }}
              className="date-input"
            />
          </div>
          <div className="filters" style={{ marginBottom: 14 }}>
            <input
              type="email"
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
              placeholder="Admin email"
              required
              style={{ minWidth: 240 }}
              className="date-input"
            />
            <input
              type="password"
              value={adminPassword}
              onChange={(e) => setAdminPassword(e.target.value)}
              placeholder="Temporary password (8+ characters)"
              required
              minLength={8}
              style={{ minWidth: 240 }}
              className="date-input"
            />
          </div>

          <button className="btn" type="submit" disabled={creating}>
            {creating ? "Creating…" : "Create organization"}
          </button>
        </form>
      )}

      <div className="panel">
        {loading ? (
          <p className="empty">Loading…</p>
        ) : orgs.length === 0 ? (
          <p className="empty">
            <strong>No organizations yet</strong>
            Create the first one above.
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Slug</th>
                <th>Status</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {orgs.map((org) => (
                <tr key={org.id}>
                  <td>{org.name}</td>
                  <td style={{ fontFamily: "monospace", fontSize: 13 }}>{org.slug}</td>
                  <td>
                    <span
                      className={
                        org.subscription_status === "active" ? "pill pill-open" : "pill pill-urgent"
                      }
                    >
                      {STATUS_LABEL[org.subscription_status] || org.subscription_status}
                    </span>
                  </td>
                  <td style={{ whiteSpace: "nowrap", color: "var(--muted)" }}>
                    {fullTimestamp(org.created_at)}
                  </td>
                  <td>
                    {org.subscription_status === "active" ? (
                      <button
                        className="btn btn-quiet"
                        disabled={busyId === org.id}
                        onClick={() => handleStatus(org, "suspended")}
                      >
                        Suspend
                      </button>
                    ) : (
                      <button
                        className="btn btn-quiet"
                        disabled={busyId === org.id}
                        onClick={() => handleStatus(org, "active")}
                      >
                        Reactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
