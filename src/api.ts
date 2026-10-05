import type { components } from "./api.generated";
export type Message = components["schemas"]["MessageView"];
export type Person = components["schemas"]["PersonView"];
export type Workspace = components["schemas"]["WorkspaceView"];
export type Filters = {
  start?: number;
  end?: number;
  person?: string;
  era?: string;
  topic?: number;
  session?: string;
  reply_person?: string;
  started_by?: string;
  with_person?: string;
};
export type Era = {
  id: string;
  name: string;
  start: number;
  end: number;
  summary: string;
  sources: string[];
  manual: number;
};
export const API = "/api/v1";
let token = "";
export async function request<T = any>(
  path: string,
  options?: RequestInit,
  retry = true,
): Promise<T> {
  if (!token) {
    const c = await fetch(API + "/config");
    if (!c.ok) throw new Error("The local server is unavailable.");
    token = (await c.json()).session_token;
  }
  const response = await fetch(API + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Session-Token": token,
      ...options?.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    if (
      response.status === 403 &&
      error.detail === "Invalid local session token" &&
      retry
    ) {
      token = "";
      return request<T>(path, options, false);
    }
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Could not complete this request.",
    );
  }
  return response.json();
}
export const mutate = <T = any>(path: string, body: unknown, method = "POST") =>
  request<T>(path, { method, body: JSON.stringify(body) });
export function params(values: Record<string, any>) {
  const p = new URLSearchParams();
  Object.entries(values).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  return p.toString();
}
export const num = (n?: number) => (n ?? 0).toLocaleString();
let timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
export function setTimeZone(zone: string) {
  timeZone = zone;
}
export const clockTime = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString(undefined, {
    timeZone,
    hour: "numeric",
    minute: "2-digit",
  });
export const isoDay = (ts: number) =>
  new Date(ts * 1000).toLocaleDateString("en-CA", { timeZone });
export const date = (ts?: number, options?: Intl.DateTimeFormatOptions) =>
  ts !== undefined && ts !== null
    ? new Date(ts * 1000).toLocaleDateString(undefined, {
        timeZone,
        ...(options ?? { month: "short", day: "numeric", year: "numeric" }),
      })
    : "—";
export function dayStart(day: string) {
  const target = Date.parse(day + "T00:00:00Z");
  let guess = target;
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  for (let i = 0; i < 3; i++) {
    const parts = Object.fromEntries(
      fmt.formatToParts(new Date(guess)).map((p) => [p.type, p.value]),
    );
    const represented = Date.UTC(
      +parts.year,
      +parts.month - 1,
      +parts.day,
      +parts.hour,
      +parts.minute,
      +parts.second,
    );
    guess += target - represented;
  }
  return guess / 1000;
}
export function dayEnd(day: string) {
  const next = new Date(Date.parse(day + "T12:00:00Z") + 86400000)
    .toISOString()
    .slice(0, 10);
  return dayStart(next) - 0.001;
}
export const monthEnd = (month: string) =>
  dayEnd(
    new Date(Date.UTC(+month.slice(0, 4), +month.slice(5), 0, 12))
      .toISOString()
      .slice(0, 10),
  );
