const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const ACCESS_KEY = "oasis_access_token";
const REFRESH_KEY = "oasis_refresh_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(ACCESS_KEY, token);
}

export function setTokens(tokens: TokenResponse): void {
  window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
  // The refresh token used to be thrown away here, which is why the
  // dashboard died with "Invalid or expired token" every 30 minutes and
  // needed a manual log out / log in. Keeping it lets refreshAccessToken()
  // below renew the session silently.
  if (tokens.refresh_token) {
    window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  }
}

export function clearToken(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

// Only one refresh should ever be in flight; several parallel 401s (the
// conversation list and the agent roster load together) must not each
// burn a refresh token.
let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) {
          clearToken();
          return null;
        }
        const tokens: TokenResponse = await res.json();
        setTokens(tokens);
        return tokens.access_token;
      } catch {
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (res.status === 401 && retry) {
    const fresh = await refreshAccessToken();
    if (fresh) return request<T>(path, options, false);
    if (typeof window !== "undefined") window.location.href = "/login";
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---------- Auth ----------

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
}

export interface WorkspaceSettings {
  timezone: string;
  available_timezones: Record<string, string>;
}

export function getWorkspaceSettings(): Promise<WorkspaceSettings> {
  return request<WorkspaceSettings>("/api/v1/workspace/settings");
}

export function setWorkspaceTimezone(timezone: string): Promise<WorkspaceSettings> {
  return request<WorkspaceSettings>("/api/v1/workspace/settings", {
    method: "PATCH",
    body: JSON.stringify({ timezone }),
  });
}

export function login(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

// ---------- Conversations ----------

export interface ConversationSummary {
  id: string;
  status: string;
  assigned_agent_id: string | null;
  customer_id: string;
  last_message_at: string | null;
  customer_name: string | null;
  customer_phone: string | null;
  customer_email: string | null;
  customer_last_read_at: string | null;
  agent_last_read_at: string | null;
}

export interface Message {
  id: string;
  sender_type: string;
  sender_id: string | null;
  content: string;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[];
}

export function listConversations(status?: string): Promise<ConversationSummary[]> {
  const query = status ? `?status=${status}` : "";
  return request<ConversationSummary[]>(`/api/v1/conversations${query}`);
}

export function getConversation(id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/v1/conversations/${id}`);
}

export function sendAgentMessage(id: string, content: string): Promise<Message> {
  return request<Message>(`/api/v1/conversations/${id}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

/**
 * Hand a conversation to another agent, or return it to the shared queue
 * by passing null. Same endpoint as closing — the backend notifies the new
 * assignee and pushes the change to every open dashboard.
 */
export function transferConversation(
  id: string,
  agentId: string | null
): Promise<ConversationSummary> {
  return request<ConversationSummary>(`/api/v1/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ assigned_agent_id: agentId }),
  });
}

/**
 * Tells the server the agent is looking at this chat, which turns the
 * customer's "sent" into "seen" on their side within a second.
 */
export function markConversationRead(id: string): Promise<void> {
  return request<void>(`/api/v1/conversations/${id}/read`, { method: "POST" });
}

export function closeConversation(id: string): Promise<ConversationSummary> {
  return request<ConversationSummary>(`/api/v1/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status: "closed" }),
  });
}

// ---------- Users ----------

export interface UserSummary {
  id: string;
  email: string;
  full_name: string;
  status: string;
  roles: string[];
  allowed_ip: string | null;
  last_blocked_ip: string | null;
  last_blocked_at: string | null;
}

export interface MyIp {
  address: string | null;
  trusting_proxy_header: boolean;
}

export interface AgentSummary {
  id: string;
  full_name: string;
  status: string;
}

/** Admin-only: full user records including roles. */
export function listUsers(): Promise<UserSummary[]> {
  return request<UserSummary[]>("/api/v1/users");
}

/**
 * Names only, readable by agents too. Use this for "assigned to" labels —
 * listUsers() 403s for agent accounts and would take the page down with it.
 */
export function listAgents(): Promise<AgentSummary[]> {
  return request<AgentSummary[]>("/api/v1/users/agents");
}

export interface CurrentUser {
  id: string;
  roles: string[];
}

/**
 * Reads the logged-in user out of the access token instead of calling the
 * API. The token already carries `sub` and `roles` (that is how the
 * backend authorizes without a DB lookup), so a round-trip would tell us
 * nothing new. This is display-only — every real permission decision is
 * made server-side, where a tampered token would fail signature checks.
 */
export function getCurrentUser(): CurrentUser | null {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(
      atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))
    );
    return { id: payload.sub, roles: payload.roles || [] };
  } catch {
    return null;
  }
}

/**
 * Pins a user to one address, or clears it by passing null. Clearing is
 * how an admin lets someone work from elsewhere for a while.
 */
export function setUserIpRestriction(
  userId: string,
  allowedIp: string | null
): Promise<UserSummary> {
  return request<UserSummary>(`/api/v1/users/${userId}/ip-restriction`, {
    method: "POST",
    body: JSON.stringify({ allowed_ip: allowedIp }),
  });
}

/** The address this server sees the admin on — safer than guessing it. */
export function getMyIp(): Promise<MyIp> {
  return request<MyIp>("/api/v1/users/my-ip");
}

export function resetUserPassword(userId: string, newPassword: string): Promise<UserSummary> {
  return request<UserSummary>(`/api/v1/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword }),
  });
}

export function suspendUser(userId: string): Promise<void> {
  return request<void>(`/api/v1/users/${userId}`, { method: "DELETE" });
}

export function reactivateUser(userId: string): Promise<UserSummary> {
  return request<UserSummary>(`/api/v1/users/${userId}/reactivate`, { method: "POST" });
}

export function inviteUser(
  email: string,
  fullName: string,
  temporaryPassword: string,
  role: string
): Promise<UserSummary> {
  return request<UserSummary>("/api/v1/users", {
    method: "POST",
    body: JSON.stringify({
      email,
      full_name: fullName,
      temporary_password: temporaryPassword,
      role,
    }),
  });
}

// ---------- Tickets ----------

export interface Ticket {
  id: string;
  customer_id: string;
  conversation_id: string | null;
  assigned_agent_id: string | null;
  created_by_user_id: string;
  subject: string;
  description: string;
  status: string;
  priority: string;
  resolved_at: string | null;
  created_at: string;
  customer_name: string | null;
  customer_phone: string | null;
}

export interface TicketComment {
  id: string;
  ticket_id: string;
  author_user_id: string;
  text: string;
  created_at: string;
}

export interface TicketDetail extends Ticket {
  comments: TicketComment[];
}

export function listTickets(filters: { status?: string; priority?: string } = {}): Promise<Ticket[]> {
  const query = new URLSearchParams();
  if (filters.status) query.set("status", filters.status);
  if (filters.priority) query.set("priority", filters.priority);
  const suffix = query.toString() ? `?${query}` : "";
  return request<Ticket[]>(`/api/v1/tickets${suffix}`);
}

export function getTicket(id: string): Promise<TicketDetail> {
  return request<TicketDetail>(`/api/v1/tickets/${id}`);
}

export function createTicket(body: {
  customer_id: string;
  conversation_id?: string | null;
  subject: string;
  description: string;
  priority: string;
}): Promise<Ticket> {
  return request<Ticket>("/api/v1/tickets", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateTicket(
  id: string,
  changes: { status?: string; priority?: string; assigned_agent_id?: string | null }
): Promise<Ticket> {
  return request<Ticket>(`/api/v1/tickets/${id}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export function addTicketComment(id: string, text: string): Promise<TicketComment> {
  return request<TicketComment>(`/api/v1/tickets/${id}/comments`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export { API_BASE };

// ---------- Platform (super_admin only) ----------

export interface Organization {
  id: string;
  name: string;
  slug: string;
  subscription_plan: string;
  subscription_status: string;
  settings: Record<string, unknown>;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export function listOrganizations(limit = 100, offset = 0): Promise<Page<Organization>> {
  return request<Page<Organization>>(`/api/v1/organizations?limit=${limit}&offset=${offset}`);
}

export interface CreateOrganizationRequest {
  organization_name: string;
  admin_full_name: string;
  admin_email: string;
  admin_password: string;
}

/** Onboards a new client: the org and its first admin, in one call. */
export function createOrganization(payload: CreateOrganizationRequest): Promise<Organization> {
  return request<Organization>("/api/v1/organizations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** "active" | "suspended" | "cancelled" */
export function setOrganizationStatus(
  organizationId: string,
  subscriptionStatus: string
): Promise<Organization> {
  return request<Organization>(`/api/v1/organizations/${organizationId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ subscription_status: subscriptionStatus }),
  });
}

// ---------- Integrations: API keys and webhooks (org_admin only) ----------

export interface ApiKeySummary {
  id: string;
  name: string;
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKeySummary {
  // Only present in the response that created it — shown once, then gone.
  api_key: string;
}

export function listApiKeys(): Promise<ApiKeySummary[]> {
  return request<ApiKeySummary[]>("/api/v1/auth/api-keys");
}

export function createApiKey(name: string): Promise<ApiKeyCreated> {
  return request<ApiKeyCreated>("/api/v1/auth/api-keys", {
    method: "POST",
    body: JSON.stringify({ name, scopes: [] }),
  });
}

export function revokeApiKey(apiKeyId: string): Promise<void> {
  return request<void>(`/api/v1/auth/api-keys/${apiKeyId}`, { method: "DELETE" });
}

export interface WebhookSubscription {
  id: string;
  url: string;
  events: string[];
  is_active: boolean;
  created_at: string;
}

export interface WebhookSubscriptionCreated extends WebhookSubscription {
  // Only present at creation — used to verify delivery signatures.
  // Shown once; the server keeps it, never returns it again.
  secret: string;
}

export const WEBHOOK_EVENTS = [
  "chat.created",
  "chat.closed",
  "message.received",
  "message.sent",
  "customer.created",
  "customer.updated",
  "ticket.created",
  "ticket.updated",
] as const;

export function listWebhooks(): Promise<WebhookSubscription[]> {
  return request<WebhookSubscription[]>("/api/v1/webhooks");
}

export function createWebhook(
  url: string,
  events: string[]
): Promise<WebhookSubscriptionCreated> {
  return request<WebhookSubscriptionCreated>("/api/v1/webhooks", {
    method: "POST",
    body: JSON.stringify({ url, events }),
  });
}

export function deleteWebhook(subscriptionId: string): Promise<void> {
  return request<void>(`/api/v1/webhooks/${subscriptionId}`, { method: "DELETE" });
}

// ---------- My organization (for the widget setup screen) ----------

export interface MyOrganization {
  id: string;
  name: string;
  slug: string;
  subscription_plan: string;
  subscription_status: string;
  settings: Record<string, unknown>;
  created_at: string;
}

export function getMyOrganization(): Promise<MyOrganization> {
  return request<MyOrganization>("/api/v1/my-organization");
}
