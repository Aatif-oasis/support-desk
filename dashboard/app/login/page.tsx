"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUser, login, setTokens } from "@/lib/api-client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const tokens = await login(email, password);
      // Store the refresh token as well, so the session renews itself
      // instead of expiring mid-shift.
      setTokens(tokens);

      // A super_admin has no organization — the agent dashboard's
      // conversation list and WebSocket both correctly reject that
      // (403), so sending them there instead of Platform isn't a
      // softer landing, it's a broken one.
      const me = getCurrentUser();
      router.push(me?.roles.includes("super_admin") ? "/platform" : "/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "That email and password didn't match");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>Chat Support</h1>
        <p className="login-lede">Sign in to answer your website visitors.</p>

        <form onSubmit={handleSubmit}>
          <label className="field">
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="username"
            />
          </label>

          <label className="field">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>

          {error && <div className="alert alert-error">{error}</div>}

          <button type="submit" className="btn" disabled={loading} style={{ width: "100%" }}>
            {loading ? "Signing in" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
