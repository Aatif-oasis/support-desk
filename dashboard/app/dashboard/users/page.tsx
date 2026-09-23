"use client";

import { useEffect, useState } from "react";
import {
  CurrentUser,
  MyIp,
  UserSummary,
  getCurrentUser,
  inviteUser,
  getMyIp,
  listUsers,
  reactivateUser,
  resetUserPassword,
  setUserIpRestriction,
  suspendUser,
} from "@/lib/api-client";
import { fullTimestamp } from "@/lib/format-time";

const ROLE_LABELS: Record<string, string> = {
  org_admin: "Administrator",
  team_manager: "Team manager",
  agent: "Agent",
};

const STATUS_NOTE: Record<string, string> = {
  active: "Can sign in",
  invited: "Has a password from an admin",
  suspended: "Cannot sign in",
};

// The column shows this instead of the raw database value, so the word on
// screen matches the button that produced it.
const STATUS_LABEL: Record<string, string> = {
  active: "active",
  invited: "invited",
  suspended: "deactivated",
};

export default function UsersPage() {
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("agent");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Which row's reset form is open, and what's typed in it.
  const [resetFor, setResetFor] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState("");

  // Which row's location form is open, what's typed in it, and the
  // address this admin is on right now.
  const [ipFor, setIpFor] = useState<string | null>(null);
  const [ipValue, setIpValue] = useState("");
  const [myIp, setMyIp] = useState<MyIp | null>(null);

  async function refresh() {
    try {
      setUsers(await listUsers());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the user list");
    }
  }

  useEffect(() => {
    setMe(getCurrentUser());
    refresh();
    // Shown so an admin can copy the office address instead of typing it
    // from memory. Typing the router's internal address (192.168.x.x) is
    // the usual mistake, and it locks the agent out completely.
    getMyIp().then(setMyIp).catch(() => undefined);
  }, []);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setSaving(true);
    try {
      await inviteUser(email, fullName, password, role);
      setNotice(`${fullName} can now sign in with the password you set.`);
      setEmail("");
      setFullName("");
      setPassword("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add this user");
    } finally {
      setSaving(false);
    }
  }

  async function handleReset(e: React.FormEvent, user: UserSummary) {
    e.preventDefault();
    if (newPassword.length < 8) {
      setError("A password needs at least 8 characters.");
      return;
    }
    setSaving(true);
    try {
      await resetUserPassword(user.id, newPassword);
      // Shown once, here, because nobody can look it up later — not even
      // an admin. The old password was never stored, only its hash.
      setNotice(
        `Password changed for ${user.full_name}. Tell them: ${newPassword} — and ask them to change it after signing in.`
      );
      setResetFor(null);
      setNewPassword("");
      setError(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset that password");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveIp(e: React.FormEvent, user: UserSummary) {
    e.preventDefault();
    setSaving(true);
    try {
      const address = ipValue.trim();
      await setUserIpRestriction(user.id, address || null);
      setNotice(
        address
          ? `${user.full_name} can now sign in only from ${address}.`
          : `${user.full_name} can sign in from anywhere.`
      );
      setIpFor(null);
      setIpValue("");
      setError(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that location");
    } finally {
      setSaving(false);
    }
  }

  async function handleSuspend(user: UserSummary) {
    if (!confirm(`Deactivate ${user.full_name}? They can't sign in, but their chats and tickets stay.`)) return;
    setSaving(true);
    try {
      await suspendUser(user.id);
      setNotice(`${user.full_name} is deactivated and can no longer sign in.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not deactivate this user");
    } finally {
      setSaving(false);
    }
  }

  async function handleReactivate(user: UserSummary) {
    setSaving(true);
    try {
      await reactivateUser(user.id);
      setNotice(`${user.full_name} is active again and can sign in.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not activate this user");
    } finally {
      setSaving(false);
    }
  }

  const isAdmin = !!me?.roles.includes("org_admin");

  return (
    <div className="page">
      <div className="page-head">
        <h2>Users</h2>
        <span className="count">{users.length} in this workspace</span>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-info">{notice}</div>}

      {isAdmin && myIp?.address && (
        <div className="alert alert-info">
          You are connecting from <strong>{myIp.address}</strong>. Use this when
          restricting someone to this office.
          {!myIp.trusting_proxy_header && (
            <div style={{ fontSize: 12.5, marginTop: 4 }}>
              If this server sits behind a proxy, set TRUST_FORWARDED_FOR so the
              real address is read instead of the proxy&apos;s.
            </div>
          )}
        </div>
      )}

      {isAdmin && (
        <div className="panel" style={{ padding: 20, marginBottom: 22 }}>
          <form
            onSubmit={handleInvite}
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: "0 16px",
              alignItems: "end",
            }}
          >
            <label className="field">
              Full name
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
            </label>

            <label className="field">
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="off"
              />
            </label>

            <label className="field">
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </label>

            <label className="field">
              Role
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="agent">Agent</option>
                <option value="team_manager">Team manager</option>
                <option value="org_admin">Administrator</option>
              </select>
            </label>

            <div className="field" style={{ marginBottom: 14 }}>
              <button type="submit" className="btn" disabled={saving} style={{ width: "100%" }}>
                {saving ? "Adding" : "Add user"}
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="panel">
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Sign-in location</th>
              {isAdmin && <th></th>}
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.full_name}</td>
                <td>{u.email}</td>
                <td>{u.roles.map((r) => ROLE_LABELS[r] || r).join(", ") || "No role"}</td>
                <td>
                  <span className={u.status === "suspended" ? "pill pill-urgent" : "pill"}>
                    {STATUS_LABEL[u.status] || u.status}
                  </span>
                  <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 3 }}>
                    {STATUS_NOTE[u.status] || ""}
                  </div>
                </td>
                <td>
                  {u.roles.includes("org_admin") ? (
                    <span style={{ fontSize: 13, color: "var(--muted)" }}>
                      Anywhere (administrator)
                    </span>
                  ) : ipFor === u.id ? (
                    <form onSubmit={(e) => handleSaveIp(e, u)} style={{ display: "flex", gap: 6 }}>
                      <input
                        value={ipValue}
                        onChange={(e) => setIpValue(e.target.value)}
                        placeholder="Leave blank for anywhere"
                        autoFocus
                        style={{
                          padding: "7px 10px",
                          border: "1px solid var(--line)",
                          borderRadius: 6,
                          font: "inherit",
                          fontSize: 14,
                          width: 190,
                        }}
                      />
                      <button type="submit" className="btn" disabled={saving}>
                        Save
                      </button>
                      <button
                        type="button"
                        className="btn btn-quiet"
                        onClick={() => {
                          setIpFor(null);
                          setIpValue("");
                        }}
                      >
                        Cancel
                      </button>
                    </form>
                  ) : (
                    <>
                      <span style={{ fontVariantNumeric: "tabular-nums", fontSize: 14 }}>
                        {u.allowed_ip || "Anywhere"}
                      </span>
                      {isAdmin && (
                        <button
                          className="btn btn-quiet"
                          style={{ marginLeft: 8, padding: "4px 10px", fontSize: 13 }}
                          onClick={() => {
                            setIpFor(u.id);
                            setIpValue(u.allowed_ip || "");
                          }}
                        >
                          {u.allowed_ip ? "Change" : "Restrict"}
                        </button>
                      )}
                      {/* A refused attempt is the admin's only signal that
                          someone has moved — or that someone is trying
                          from somewhere they shouldn't be. */}
                      {u.last_blocked_ip && (
                        <div
                          style={{ fontSize: 12.5, color: "var(--waiting)", marginTop: 4 }}
                          title={u.last_blocked_at ? fullTimestamp(u.last_blocked_at) : ""}
                        >
                          Blocked from {u.last_blocked_ip}
                        </div>
                      )}
                    </>
                  )}
                </td>
                {isAdmin && (
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {resetFor === u.id ? (
                      <form onSubmit={(e) => handleReset(e, u)} style={{ display: "flex", gap: 6 }}>
                        <input
                          type="text"
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder="New password"
                          autoFocus
                          style={{
                            padding: "7px 10px",
                            border: "1px solid var(--line)",
                            borderRadius: 6,
                            font: "inherit",
                            fontSize: 14,
                          }}
                        />
                        <button type="submit" className="btn" disabled={saving}>
                          Set
                        </button>
                        <button
                          type="button"
                          className="btn btn-quiet"
                          onClick={() => {
                            setResetFor(null);
                            setNewPassword("");
                          }}
                        >
                          Cancel
                        </button>
                      </form>
                    ) : (
                      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                        {/* An admin can't lock themselves out of their own workspace. */}
                        {u.id !== me?.id && (
                          <>
                            <button
                              className="btn btn-quiet"
                              onClick={() => setResetFor(u.id)}
                              disabled={saving}
                            >
                              Reset password
                            </button>
                            {u.status === "suspended" ? (
                              <button
                                className="btn btn-quiet"
                                onClick={() => handleReactivate(u)}
                                disabled={saving}
                              >
                                Activate
                              </button>
                            ) : (
                              <button
                                className="btn btn-quiet"
                                onClick={() => handleSuspend(u)}
                                disabled={saving}
                              >
                                Deactivate
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && !error && (
          <p className="empty">
            <strong>Nobody here yet</strong>
            Add your first agent using the form above.
          </p>
        )}
      </div>

    </div>
  );
}
