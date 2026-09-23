/**
 * Time formatting for the agent console.
 *
 * The backend stores everything in UTC with an offset. Display is pinned
 * to India Standard Time rather than the viewer's own machine clock, so
 * the console reads the same for every agent and every server, whatever
 * timezone that particular computer happens to be set to.
 *
 * Two different jobs, deliberately formatted differently:
 *
 *  - In a list, an agent is asking "how stale is this?" — a relative
 *    phrase ("4 min ago") answers that instantly, while a clock time
 *    forces them to do the subtraction themselves.
 *  - Inside a chat, they're asking "when exactly was this said?" — there
 *    an actual clock time is what's wanted, since it may end up quoted
 *    back to a customer.
 */

// The workspace's chosen zone, applied everywhere below. Starts at the
// same default the backend uses, so a page that hasn't loaded the
// workspace settings yet still renders something sensible rather than
// falling back to the viewer's own machine clock.
//
// A plain mutable module variable rather than React context: these are
// pure formatting functions called from many components, and threading
// a timezone prop through every one of them for a value that changes
// once per session (on login, or when an admin changes it) is more
// machinery than the problem needs.
let currentTimezone = "Asia/Kolkata";

export function setDisplayTimezone(timezone: string): void {
  currentTimezone = timezone;
}

export function getDisplayTimezone(): string {
  return currentTimezone;
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";

  const elapsed = Date.now() - then;

  // A clock skew of a few seconds shouldn't produce "in 3 seconds".
  if (elapsed < MINUTE) return "just now";
  if (elapsed < HOUR) {
    const mins = Math.floor(elapsed / MINUTE);
    return `${mins} min ago`;
  }
  if (elapsed < DAY) {
    const hours = Math.floor(elapsed / HOUR);
    return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
  }
  if (elapsed < 2 * DAY) return "yesterday";
  if (elapsed < 7 * DAY) {
    const days = Math.floor(elapsed / DAY);
    return `${days} days ago`;
  }
  // Past a week, "23 days ago" stops being useful — give the date.
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    timeZone: currentTimezone,
  });
}

/** Clock time only, e.g. "4:12 PM" — used beside each message. */
export function clockTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("en-IN", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: currentTimezone,
  });
}

/** Full date and time, for hover titles and ticket notes. */
export function fullTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: currentTimezone,
  });
}

/**
 * Heading for a day's worth of messages. "Today" and "Yesterday" read
 * faster than a date when that's what the day actually is.
 */
/** en-CA gives YYYY-MM-DD, which is what makes "same calendar day in
 *  IST" a plain string comparison instead of another Date to juggle. */
function istDateKey(iso: string | Date): string {
  const date = typeof iso === "string" ? new Date(iso) : iso;
  return date.toLocaleDateString("en-CA", { timeZone: currentTimezone });
}

export function dayLabel(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";

  const todayKey = istDateKey(new Date());
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayKey = istDateKey(yesterday);
  const thisKey = istDateKey(date);

  if (thisKey === todayKey) return "Today";
  if (thisKey === yesterdayKey) return "Yesterday";

  const daysApart = Math.round(
    (new Date(todayKey).getTime() - new Date(thisKey).getTime()) / DAY
  );
  if (daysApart < 7) {
    return date.toLocaleDateString("en-IN", { weekday: "long", timeZone: currentTimezone });
  }
  return date.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "long",
    year: thisKey.slice(0, 4) === todayKey.slice(0, 4) ? undefined : "numeric",
    timeZone: currentTimezone,
  });
}

/** True when two messages fall on different calendar days. */
export function isDifferentDay(a: string, b: string): boolean {
  return istDateKey(a) !== istDateKey(b);
}

/**
 * Elapsed time as a stopwatch — "0:47", "12:05", "1:04:22".
 *
 * Separate from relativeTime because the question is different: an
 * unanswered chat is a clock ticking, and an agent needs to feel the
 * seconds move. "a minute ago" hides exactly the urgency this is for.
 */
export function stopwatch(iso: string | null): string {
  if (!iso) return "";
  const start = new Date(iso).getTime();
  if (Number.isNaN(start)) return "";

  const seconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const s = seconds % 60;
  const m = Math.floor(seconds / 60) % 60;
  const h = Math.floor(seconds / 3600);

  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/** Minutes of silence before a live chat counts as idle. */
export const IDLE_AFTER_MS = 5 * 60_000;

export function isIdle(iso: string | null): boolean {
  if (!iso) return false;
  const last = new Date(iso).getTime();
  if (Number.isNaN(last)) return false;
  return Date.now() - last > IDLE_AFTER_MS;
}
