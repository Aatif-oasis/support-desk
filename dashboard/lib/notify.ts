/**
 * Alerting an agent who isn't looking at the screen.
 *
 * Three layers, because any one of them can be missed: a sound (heard
 * even when the window is behind something else), a browser notification
 * (visible when the tab is in the background), and a count in the tab
 * title (survives both being muted and notifications being denied).
 */

const MUTE_KEY = "oasis_alerts_muted";

let audioContext: AudioContext | null = null;
let unreadForTitle = 0;
let baseTitle = "";

export function isMuted(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(MUTE_KEY) === "1";
}

export function setMuted(muted: boolean): void {
  window.localStorage.setItem(MUTE_KEY, muted ? "1" : "0");
}

/**
 * Browsers refuse to play audio until the page has been interacted with,
 * and a WebSocket event is not an interaction. So the context is created
 * on the agent's first click anywhere and kept alive from then on — by
 * the time a visitor arrives, it is ready.
 */
export function primeAudio(): void {
  if (typeof window === "undefined") return;
  try {
    const Ctor =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return;
    if (!audioContext) audioContext = new Ctor();
    if (audioContext.state === "suspended") void audioContext.resume();
  } catch {
    // No audio available. The title count and notification still work.
  }
}

/**
 * A short two-note chime, synthesised rather than loaded from a file:
 * no asset to host, no request to fail, and nothing to go missing when
 * the widget is deployed somewhere else.
 */
function tone(startAt: number, frequency: number, duration: number, volume: number): void {
  if (!audioContext) return;
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();

  oscillator.type = "sine";
  oscillator.frequency.value = frequency;

  // Ramped rather than switched on, so it reads as a chime instead of a
  // click.
  gain.gain.setValueAtTime(0.0001, startAt);
  gain.gain.exponentialRampToValueAtTime(volume, startAt + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);

  oscillator.connect(gain);
  gain.connect(audioContext.destination);
  oscillator.start(startAt);
  oscillator.stop(startAt + duration + 0.05);
}

/** A new visitor: two rising notes, deliberately hard to miss. */
export function playNewVisitorChime(): void {
  if (isMuted()) return;
  primeAudio();
  if (!audioContext) return;
  const now = audioContext.currentTime;
  tone(now, 660, 0.18, 0.18);
  tone(now + 0.16, 880, 0.26, 0.18);
}

/** A reply in a chat already in progress: one quieter note. */
export function playMessageBlip(): void {
  if (isMuted()) return;
  primeAudio();
  if (!audioContext) return;
  tone(audioContext.currentTime, 760, 0.12, 0.08);
}

// ---------- Browser notifications ----------

export function notificationPermission(): string {
  if (typeof window === "undefined" || !("Notification" in window)) return "unsupported";
  return Notification.permission;
}

export async function askForNotifications(): Promise<string> {
  if (typeof window === "undefined" || !("Notification" in window)) return "unsupported";
  try {
    return await Notification.requestPermission();
  } catch {
    return "denied";
  }
}

/**
 * Only shown when the tab is in the background. Popping a notification
 * over a screen the agent is already reading is noise, not help.
 */
export function showNotification(title: string, body: string): void {
  if (typeof document === "undefined") return;
  if (document.visibilityState === "visible") return;
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  try {
    const notification = new Notification(title, { body, tag: "oasis-chat" });
    notification.onclick = () => {
      window.focus();
      notification.close();
    };
  } catch {
    // Some browsers throw when the page isn't a secure context.
  }
}

// ---------- Tab title ----------

export function bumpTitleCount(): void {
  if (typeof document === "undefined") return;
  if (document.visibilityState === "visible") return;
  if (!baseTitle) baseTitle = document.title.replace(/^\(\d+\)\s*/, "");
  unreadForTitle += 1;
  document.title = `(${unreadForTitle}) ${baseTitle}`;
}

export function clearTitleCount(): void {
  if (typeof document === "undefined" || unreadForTitle === 0) return;
  unreadForTitle = 0;
  if (baseTitle) document.title = baseTitle;
}
