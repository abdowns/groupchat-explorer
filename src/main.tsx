import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";
import {
  QueryClient,
  QueryClientProvider,
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  ArrowDownToLine,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  Compass,
  Heart,
  History,
  Image,
  Layers3,
  MessageCircle,
  Plus,
  Search,
  Settings2,
  Sparkles,
  Trophy,
  Users,
  X,
  Zap,
  Quote,
  Menu,
  Moon,
  Sun,
  LoaderCircle,
  Play,
  Pause,
  RefreshCw,
  Pin,
  BookOpen,
  SlidersHorizontal,
  ExternalLink,
  Pencil,
  Shuffle,
} from "lucide-react";
import * as echarts from "echarts/core";
import {
  LineChart,
  BarChart,
  PieChart,
  HeatmapChart,
  GraphChart,
} from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CalendarComponent,
  VisualMapComponent,
  DataZoomComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
echarts.use([
  LineChart,
  BarChart,
  PieChart,
  HeatmapChart,
  GraphChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CalendarComponent,
  VisualMapComponent,
  DataZoomComponent,
  SVGRenderer,
]);
import { toPng } from "html-to-image";
import {
  API,
  type Era,
  type Filters,
  type Message,
  type Person,
  type Workspace,
  date,
  dayEnd,
  dayStart,
  monthEnd,
  setTimeZone,
  isoDay,
  clockTime,
  mutate,
  num,
  params,
  request,
} from "./api";
import "./style.css";

const client = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30000, retry: 1, refetchOnWindowFocus: false },
  },
});
const NAV = [
  ["overview", "Overview", Compass],
  ["timeline", "Timeline", History],
  ["people", "People", Users],
  ["reactions", "Reactions", Heart],
  ["words", "Words & phrases", Quote],
  ["conversations", "Conversations", MessageCircle],
  ["topics", "Topics & search", Search],
  ["lore", "Group lore", BookOpen],
  ["media", "Media & links", Image],
  ["recaps", "Recaps & games", Trophy],
] as const;
const COLORS = [
  "#df7253",
  "#638b70",
  "#6c84b1",
  "#b987b7",
  "#c4a34e",
  "#5c9eaa",
];
const REACTIONS: Record<string, string> = {
  heart: "❤️",
  like: "👍",
  dislike: "👎",
  laugh: "😂",
  emphasize: "‼️",
  question: "❓",
  sticker: "🎟️",
};
type DrawerSpec = {
  title: string;
  ids?: string[];
  mid?: string;
  thread?: string;
  extra?: Filters;
  word?: { q: string; mode?: string };
  semantic?: { q: string; threshold: number };
  reaction?: {
    actor?: string;
    recipient?: string;
    reaction_type?: string;
    basis?: string;
  };
};
type Context = {
  wid: string;
  workspace?: Workspace;
  filters: Filters;
  setFilters: React.Dispatch<React.SetStateAction<Filters>>;
  people: Person[];
  open: (s: DrawerSpec) => void;
  go: (s: string) => void;
  toast: (s: string) => void;
  jobs: any[];
};
const AppContext = createContext<Context>(null!);
const useApp = () => useContext(AppContext);
function useData<T = any>(
  path: string,
  extra: Record<string, any> = {},
  enabled = true,
) {
  const { wid, filters } = useApp();
  return useQuery<T>({
    queryKey: [wid, path, filters, extra],
    queryFn: () =>
      request(`/workspaces/${wid}/${path}?${params({ ...filters, ...extra })}`),
    enabled: Boolean(wid) && enabled,
  });
}
function Avatar({
  person,
  size = "normal",
}: {
  person?: Person;
  size?: string;
}) {
  return (
    <span
      className={`avatar ${size}`}
      style={{ background: person?.color ?? "#b7afa4" }}
    >
      {person?.name.slice(0, 1).toUpperCase() ?? "?"}
    </span>
  );
}
function Member({ id }: { id: string }) {
  const { people } = useApp();
  const p = people.find((p) => p.id === id);
  return (
    <span className="member">
      <Avatar person={p} size="small" />
      {p?.name ?? id}
    </span>
  );
}
function Panel({
  title,
  subtitle,
  children,
  action,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-head">
          <div>
            <h3>{title}</h3>
            {subtitle && <p>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
function State({
  query,
  children,
}: {
  query: any;
  children: (data: any) => React.ReactNode;
}) {
  if (query.isPending)
    return (
      <div className="loading">
        <LoaderCircle className="spin" />
        Opening the archive…
      </div>
    );
  if (query.error)
    return (
      <div className="empty">
        <p>{query.error.message}</p>
        <button onClick={() => query.refetch()}>Try again</button>
      </div>
    );
  return <>{children(query.data)}</>;
}
function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <Sparkles />
      <h3>{title}</h3>
      {children}
    </div>
  );
}
function Chart({
  option,
  onClick,
  height = 270,
  label,
}: {
  option: any;
  onClick?: (p: any) => void;
  height?: number;
  label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const dark = document.documentElement.dataset.theme === "dark";
  useEffect(() => {
    const chart = echarts.init(ref.current, undefined, { renderer: "svg" });
    const base = {
      textStyle: { fontFamily: "inherit", color: dark ? "#c6bfb4" : "#827d75" },
      tooltip: { trigger: "axis" },
      grid: { left: 42, right: 20, top: 20, bottom: 35 },
      ...option,
    };
    chart.setOption(base);
    if (onClick) chart.on("click", onClick);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current!);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option, dark]);
  const tableRows = (option.series ?? []).flatMap((s: any) => {
    if (s.type === "graph")
      return (s.links ?? []).map((l: any) => [l.source, l.target, l.value]);
    return (s.data ?? []).map((point: any, index: number) => {
      const value = point?.value ?? point;
      if (Array.isArray(value)) {
        if (value.length === 3)
          return [
            option.xAxis?.data?.[value[0]] ?? value[0],
            option.yAxis?.data?.[value[1]] ?? value[1],
            value[2],
          ];
        return [s.name ?? "Value", value[0], value[1]];
      }
      return [
        s.name ?? "Value",
        point?.name ?? option.xAxis?.data?.[index] ?? index,
        value,
      ];
    });
  });
  return (
    <>
      <div
        className="chart"
        ref={ref}
        style={{ height }}
        role="img"
        aria-label={label}
      />
      <details className="chart-alternative">
        <summary>View chart data</summary>
        <div className="table-wrap">
          <table>
            <caption>{label}</caption>
            <thead>
              <tr>
                <th>Series / source</th>
                <th>Category / target</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row: any, i: number) => (
                <tr key={i}>
                  {row.map((v: any, j: number) => (
                    <td key={j}>{String(v ?? "—")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
function Bar({
  rows,
  field = "messages",
  onClick,
  sample,
}: {
  rows: any[];
  sample?: "messages" | "total_words";
  field?: string;
  onClick?: (r: any) => void;
}) {
  const { people } = useApp();
  const max = Math.max(...rows.map((p) => p[field]), 1);
  return (
    <div className="bars">
      {rows.map((r, i) => {
        const p = people.find((p) => p.id === (r.id ?? r.actor ?? r.starter));
        return (
          <button
            className="bar-row"
            key={r.id ?? r.actor ?? r.starter ?? i}
            onClick={() => onClick?.(r)}
          >
            <span className="bar-member">
              <Member id={r.id ?? r.actor ?? r.starter} />
              {sample && (
                <small>
                  {num(r[sample])}{" "}
                  {sample === "total_words" ? "authored words" : "messages"}
                </small>
              )}
            </span>
            <div className="bar-track">
              <span
                style={{
                  width: `${(r[field] / max) * 100}%`,
                  background: p?.color ?? COLORS[i % 6],
                }}
              />
            </div>
            <strong>
              {field === "reaction_rate"
                ? `${(r[field] * 100).toFixed(1)}%`
                : typeof r[field] === "number" && field.includes("per")
                  ? r[field].toFixed(2)
                  : r[field] === null
                    ? "—"
                    : num(r[field])}
            </strong>
          </button>
        );
      })}
    </div>
  );
}
function Sources({
  ids,
  label = "Explore messages",
}: {
  ids: string[];
  label?: string;
}) {
  const { open } = useApp();
  return (
    <button className="text-button" onClick={() => open({ title: label, ids })}>
      {label}
      <ArrowRight size={14} />
    </button>
  );
}
function MessageCard({
  m,
  highlight = false,
  onClick,
}: {
  m: Message;
  highlight?: boolean;
  onClick?: () => void;
}) {
  const { wid, people, open } = useApp();
  const p = people.find((p) => p.id === m.person_id);
  return (
    <article className={`message-card ${highlight ? "highlight" : ""}`}>
      <div className="message-meta">
        <Avatar person={p} size="small" />
        <strong>{p?.name ?? m.person_id}</strong>
        <time>
          {date(m.ts)} · {clockTime(m.ts)}
        </time>
      </div>
      {m.reply_to && (
        <button
          className="reply-link"
          onClick={() => open({ title: "Original message", mid: m.reply_to! })}
        >
          ↳ View original reply
        </button>
      )}
      {m.reply_to && (
        <button
          className="reply-link"
          onClick={() => open({ title: "Explicit reply tree", thread: m.id })}
        >
          View reply tree
        </button>
      )}
      <button
        className="message-text"
        onClick={
          onClick ?? (() => open({ title: "Conversation context", mid: m.id }))
        }
      >
        {m.text ||
          (m.attachments.length ? "[Attachment]" : "[No text available]")}
      </button>
      {Object.keys(m.source_metadata ?? {}).length > 0 && (
        <details className="source-details">
          <summary>Source details</summary>
          <pre>{JSON.stringify(m.source_metadata, null, 2)}</pre>
        </details>
      )}
      {m.reactions.length > 0 && (
        <div className="reaction-chips">
          {Object.entries(
            m.reactions.reduce(
              (a: any, r: any) => ({ ...a, [r.type]: (a[r.type] ?? 0) + 1 }),
              {},
            ),
          ).map(([type, n]) => (
            <span
              key={type}
              title={m.reactions
                .filter((r: any) => r.type === type)
                .map(
                  (r: any) =>
                    people.find((p) => p.id === r.actor)?.name ?? r.actor,
                )
                .join(", ")}
            >
              {REACTIONS[type] ?? type} {n as number}
            </span>
          ))}
        </div>
      )}
      {m.attachments.length > 0 && (
        <div className="attachment-chips">
          {m.attachments.map((a: any) => (
            <a
              key={a.id}
              href={`${API}/workspaces/${wid}/attachments/${encodeURIComponent(a.id)}`}
              target="_blank"
              rel="noreferrer"
            >
              {a.exists_local ? "↗" : "Unavailable:"} {a.name}
            </a>
          ))}
        </div>
      )}
      {m.edits.length > 0 && (
        <details>
          <summary>Edit history</summary>
          {m.edits.map((e: any, i) => (
            <div key={i}>
              {e.status}
              {e.history?.map((h: any, j: number) => (
                <p key={j}>
                  {date(h.ts)} — {h.text}
                </p>
              ))}
            </div>
          ))}
        </details>
      )}
    </article>
  );
}

function Drawer({ spec, close }: { spec: DrawerSpec; close: () => void }) {
  const { wid, filters, toast, open } = useApp();
  const parent = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const [replay, setReplay] = useState(false);
  const [visible, setVisible] = useState(1);
  const [speed, setSpeed] = useState(60);
  const [pinning, setPinning] = useState<Message | null>(null);
  const infinite = useInfiniteQuery({
    queryKey: [wid, "drawer", spec, filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      spec.thread
        ? request(
            `/workspaces/${wid}/messages/${encodeURIComponent(spec.thread)}/thread`,
          )
        : spec.mid
          ? request(
              `/workspaces/${wid}/messages/${encodeURIComponent(spec.mid)}/context`,
            )
          : spec.reaction
            ? request(
                `/workspaces/${wid}/reaction-targets?${params({ ...filters, ...spec.extra, ...spec.reaction, cursor: pageParam, limit: 100 })}`,
              )
            : spec.semantic
              ? request(
                  `/workspaces/${wid}/semantic-matches?${params({ ...filters, ...spec.extra, ...spec.semantic, cursor: pageParam, limit: 100 })}`,
                )
              : request(
                  `/workspaces/${wid}/messages?${params({ ...filters, ...spec.extra, word: spec.word?.q, word_mode: spec.word?.mode, ids: spec.ids?.join(","), kind: spec.ids ? "all" : "message", cursor: pageParam, direction: spec.extra?.session ? "asc" : "desc", limit: 100 })}`,
                ),
    getNextPageParam: (last: any) => last.next_cursor ?? undefined,
  });
  const rows: Message[] =
    infinite.data?.pages.flatMap((p: any) => p.items) ?? [];
  const shown = replay ? rows.slice(0, visible) : rows;
  const virtual = useVirtualizer({
    count: shown.length,
    getScrollElement: () => parent.current,
    estimateSize: () => 170,
    overscan: 6,
  });
  const positioned = useRef(false);
  useEffect(() => {
    if (!spec.mid || !rows.length || positioned.current) return;
    const index = rows.findIndex((m) => m.id === spec.mid);
    if (index >= 0) {
      requestAnimationFrame(() =>
        virtual.scrollToIndex(index, { align: "center" }),
      );
      positioned.current = true;
    }
  }, [rows.length, spec.mid]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const controls = () =>
      Array.from(
        dialog.current?.querySelectorAll<HTMLElement>(
          "button:not([disabled]),input,select,a[href]",
        ) ?? [],
      ).filter((el) => el.getClientRects().length > 0);
    requestAnimationFrame(() => controls()[0]?.focus());
    const key = (e: KeyboardEvent) => {
      if (document.querySelector(".modal")) return;
      if (e.key === "Tab") {
        const list = controls();
        const index = list.indexOf(document.activeElement as HTMLElement);
        if (e.shiftKey && index <= 0) {
          e.preventDefault();
          list.at(-1)?.focus();
        } else if (!e.shiftKey && (index === list.length - 1 || index === -1)) {
          e.preventDefault();
          list[0]?.focus();
        }
      }
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, []);
  useEffect(() => {
    if (
      replay &&
      visible >= rows.length &&
      infinite.hasNextPage &&
      !infinite.isFetchingNextPage
    ) {
      infinite.fetchNextPage();
      return;
    }
    if (!replay || visible >= rows.length) return;
    const delay = Math.max(
      80,
      Math.min(
        3000,
        (((rows[visible]?.ts ?? 0) - (rows[visible - 1]?.ts ?? 0)) * 1000) /
          speed,
      ),
    );
    const timer = setTimeout(() => setVisible((v) => v + 1), delay);
    return () => clearTimeout(timer);
  }, [replay, visible, speed, rows.length]);
  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <aside
        className="drawer"
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-label={spec.title}
      >
        <div className="drawer-head">
          <div>
            <small>THE ORIGINAL CONVERSATION</small>
            <h2>{spec.title}</h2>
          </div>
          <button
            className="icon-button"
            aria-label="Close messages"
            onClick={close}
          >
            <X />
          </button>
        </div>
        <div className="drawer-toolbar">
          <span>{num(rows.length)} messages loaded</span>
          {spec.extra?.session && (
            <>
              <button
                onClick={() => {
                  if (!replay && visible >= rows.length) setVisible(1);
                  setReplay((r) => !r);
                }}
              >
                {replay ? <Pause size={15} /> : <Play size={15} />}Replay
              </button>
              <select
                aria-label="Replay speed"
                value={speed}
                onChange={(e) => setSpeed(+e.target.value)}
              >
                <option value={30}>30×</option>
                <option value={60}>60×</option>
                <option value={300}>300×</option>
              </select>
            </>
          )}
        </div>
        {infinite.error ? (
          <Empty title={infinite.error.message} />
        ) : (
          <div ref={parent} className="drawer-scroll">
            <div
              style={{ height: virtual.getTotalSize(), position: "relative" }}
            >
              {virtual.getVirtualItems().map((v) => {
                const m = shown[v.index];
                return (
                  <div
                    key={m.id}
                    ref={virtual.measureElement}
                    data-index={v.index}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      transform: `translateY(${v.start}px)`,
                    }}
                  >
                    <MessageCard
                      m={m}
                      highlight={m.id === spec.mid}
                      onClick={() => {}}
                    />
                    <button
                      className="pin-message"
                      onClick={() =>
                        open({ title: "Surrounding conversation", mid: m.id })
                      }
                    >
                      View surrounding exchange <ArrowRight size={12} />
                    </button>
                    <button
                      className="pin-message"
                      onClick={() => setPinning(m)}
                    >
                      <Pin size={12} />
                      Pin as a milestone
                    </button>
                  </div>
                );
              })}
            </div>
            {infinite.hasNextPage && !replay && (
              <button
                className="load-more"
                onClick={() => infinite.fetchNextPage()}
              >
                Load more messages
              </button>
            )}
          </div>
        )}
        {pinning && (
          <div className="drawer-pin">
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                try {
                  await mutate(`/workspaces/${wid}/events`, {
                    title: f.get("title"),
                    ts: pinning.ts,
                    sources: [pinning.id],
                    summary: pinning.text,
                  });
                  toast("Milestone pinned");
                  setPinning(null);
                  client.invalidateQueries();
                } catch (e: any) {
                  toast(e.message);
                }
              }}
            >
              <input
                name="title"
                placeholder="Give this moment a name"
                required
                autoFocus
              />
              <button className="primary">Pin</button>
              <button type="button" onClick={() => setPinning(null)}>
                Cancel
              </button>
            </form>
          </div>
        )}
      </aside>
    </div>
  );
}

function Overview() {
  const q = useData("analytics/overview");
  const { open, people } = useApp();
  const discoveries = useData("timeline");
  const [calendarYear, setCalendarYear] = useState(0);
  return (
    <State query={q}>
      {(d) => {
        const byMonth: any = {};
        d.activity.forEach((r: any) => {
          const month = r.day.slice(0, 7);
          byMonth[month] ??= {};
          byMonth[month][r.person_id] =
            (byMonth[month][r.person_id] ?? 0) + r.count;
        });
        const months = Object.keys(byMonth).sort();
        const chart = {
          color: people.map((p) => p.color),
          xAxis: {
            type: "category",
            data: months,
            axisLabel: {
              formatter: (v: string) =>
                v.endsWith("-01") ? v.slice(0, 4) : "",
              interval: 0,
            },
            axisLine: { show: false },
            axisTick: { show: false },
          },
          yAxis: {
            type: "value",
            splitLine: { lineStyle: { color: "#eae6dd", type: "dashed" } },
            axisLabel: { fontSize: 11 },
          },
          series: people.map((p) => ({
            name: p.name,
            type: "line",
            stack: "messages",
            smooth: 0.25,
            symbol: "none",
            areaStyle: { opacity: 0.62 },
            lineStyle: { width: 1.5 },
            data: months.map((m) => byMonth[m][p.id] ?? 0),
          })),
        };
        const lastYear =
          calendarYear ||
          (d.totals.end
            ? new Date(d.totals.end * 1000).getFullYear()
            : new Date().getFullYear());
        const daily: Record<string, number> = {};
        d.activity.forEach(
          (r: any) => (daily[r.day] = (daily[r.day] ?? 0) + r.count),
        );
        return (
          <>
            <div className="hero-note">
              <span className="hero-orbit">
                <MessageCircle size={23} />
                <Sparkles size={14} />
              </span>
              <div>
                <small>EVERY CHAT HAS A STORY</small>
                <p>Years of little moments. One big history.</p>
              </div>
              <span className="hero-date">
                {date(d.totals.start, { year: "numeric", month: "short" })} —{" "}
                {date(d.totals.end, { year: "numeric", month: "short" })}
              </span>
            </div>
            <div className="stats-grid">
              {[
                {
                  name: "Messages sent",
                  value: num(d.totals.messages),
                  detail: "Every thought, plan & “lmao”",
                  icon: MessageCircle,
                },
                {
                  name: "Words exchanged",
                  value: num(d.totals.words),
                  detail: "A story written together",
                  icon: Quote,
                },
                {
                  name: "Current reactions",
                  value: num(d.totals.reactions),
                  detail: "A little love goes a long way",
                  icon: Heart,
                },
                {
                  name: "Days of conversation",
                  value: num(d.totals.active_days),
                  detail: `Across ${d.totals.members} members`,
                  icon: CalendarDays,
                },
              ].map((s, i) => (
                <button
                  className="stat-card"
                  key={s.name}
                  onClick={() =>
                    open({
                      title: s.name,
                      ...(i === 2 ? { reaction: {} } : {}),
                    })
                  }
                >
                  <span className={`stat-icon tone-${i}`}>
                    <s.icon size={18} />
                  </span>
                  <small>{s.name}</small>
                  <strong>{s.value}</strong>
                  <span>{s.detail}</span>
                </button>
              ))}
            </div>
            <div className="grid-wide">
              <Panel
                title="The conversation, over time"
                subtitle="A little quieter. A little louder. Always you."
                action={<span className="badge">MONTHLY</span>}
              >
                <Chart
                  option={chart}
                  label="Monthly messages by member"
                  onClick={(p) =>
                    open({
                      title: p.name,
                      extra: {
                        start: dayStart(p.name + "-01"),
                        end: dayEnd(
                          new Date(+p.name.slice(0, 4), +p.name.slice(5), 0)
                            .toISOString()
                            .slice(0, 10),
                        ),
                      },
                    })
                  }
                />
                <div className="legend">
                  {people.map((p) => (
                    <span key={p.id}>
                      <i style={{ background: p.color }} />
                      {p.name}
                    </span>
                  ))}
                </div>
              </Panel>
              <Panel
                title="Who keeps it going?"
                subtitle="Messages sent, by member"
                action={<Users size={16} />}
              >
                <Bar
                  rows={d.people}
                  onClick={(p) =>
                    open({
                      title: `Messages from ${p.name}`,
                      extra: { person: p.id },
                    })
                  }
                />
                <p className="footnote">
                  Click a member to explore their messages.
                </p>
              </Panel>
            </div>
            <Panel
              title="Little moments, big milestones"
              subtitle="Observed history in your current selection"
            >
              <div className="chips">
                {(discoveries.data?.milestones ?? []).map((m: any) => (
                  <button
                    key={m.title}
                    onClick={() => open({ title: m.title, mid: m.sources[0] })}
                  >
                    {m.title} · {date(m.ts)}
                  </button>
                ))}
              </div>
              {(discoveries.data?.events ?? [])
                .slice(-3)
                .reverse()
                .map((e: any) => (
                  <button
                    className="text-button"
                    key={e.id}
                    onClick={() => open({ title: e.title, ids: e.sources })}
                  >
                    {e.title} · {date(e.ts)} <ArrowRight size={12} />
                  </button>
                ))}
            </Panel>
            <div className="grid-wide">
              <Panel
                title="A year in little squares"
                action={
                  <select
                    aria-label="Calendar year"
                    value={lastYear}
                    onChange={(e) => setCalendarYear(+e.target.value)}
                  >
                    {[...new Set(d.activity.map((r: any) => r.day.slice(0, 4)))]
                      .sort()
                      .map((y: any) => (
                        <option key={y} value={y}>
                          {y}
                        </option>
                      ))}
                  </select>
                }
                subtitle={`Every active day in ${lastYear}. Click one to revisit it.`}
              >
                <Chart
                  height={160}
                  label="Daily message activity calendar"
                  option={{
                    tooltip: {
                      formatter: (p: any) =>
                        `${p.value[0]} · ${num(p.value[1])} messages`,
                    },
                    visualMap: {
                      min: 0,
                      max: Math.max(20, ...Object.values(daily)),
                      show: false,
                      inRange: {
                        color: ["#eee9df", "#eec7b4", "#df7253", "#a84930"],
                      },
                    },
                    calendar: {
                      range: String(lastYear),
                      left: 35,
                      right: 15,
                      top: 30,
                      bottom: 15,
                      cellSize: ["auto", 14],
                      splitLine: { show: false },
                      yearLabel: { show: false },
                      dayLabel: { firstDay: 1, nameMap: "en", fontSize: 10 },
                      monthLabel: { nameMap: "en", fontSize: 10 },
                      itemStyle: { borderWidth: 3, borderColor: "transparent" },
                    },
                    series: [
                      {
                        type: "heatmap",
                        coordinateSystem: "calendar",
                        data: Object.entries(daily).filter(([day]) =>
                          day.startsWith(String(lastYear)),
                        ),
                      },
                    ],
                  }}
                  onClick={(p) =>
                    open({
                      title: date(dayStart(p.value[0])),
                      extra: {
                        start: dayStart(p.value[0]),
                        end: dayEnd(p.value[0]),
                      },
                    })
                  }
                />
                <div className="heat-legend">
                  <span>Quiet</span>
                  {["#eee9df", "#eec7b4", "#df7253", "#a84930"].map((c) => (
                    <i key={c} style={{ background: c }} />
                  ))}
                  <span>Chaotic</span>
                </div>
              </Panel>
              <Panel title="On this day" subtitle="A small time machine">
                <div className="memory-card">
                  <CalendarDays />
                  <small>
                    {new Date().toLocaleDateString(undefined, {
                      month: "long",
                      day: "numeric",
                    })}
                  </small>
                  {d.memories.length ? (
                    <>
                      <p>“{d.memories[0].text}”</p>
                      <Member id={d.memories[0].person_id} />
                      <Sources
                        ids={d.memories.map((m: Message) => m.id)}
                        label="Take me back"
                      />
                    </>
                  ) : (
                    <>
                      <p>No messages on this date in your selection.</p>
                      <span>Try another day in the activity calendar.</span>
                    </>
                  )}
                </div>
              </Panel>
            </div>
            <Panel
              title="The messages that landed"
              subtitle="A few moments everyone had something to say about"
              action={<span className="badge">HALL OF FAME</span>}
            >
              <div className="message-grid">
                {d.top_messages.slice(0, 3).map((m: Message) => (
                  <MessageCard key={m.id} m={m} />
                ))}
              </div>
            </Panel>
          </>
        );
      }}
    </State>
  );
}

function Timeline() {
  const q = useData("timeline");
  const { wid, open, toast } = useApp();
  const [editing, setEditing] = useState<Partial<Era> | null>(null);
  const [merge, setMerge] = useState<string[]>([]);
  const save = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      const data = {
        name: f.get("name"),
        start: dayStart(String(f.get("start"))),
        end: dayEnd(String(f.get("end"))),
        summary: f.get("summary"),
        sources: editing?.sources ?? [],
      };
      await mutate(
        `/workspaces/${wid}/eras${editing?.id ? "/" + editing.id : ""}`,
        data,
        editing?.id ? "PUT" : "POST",
      );
      setEditing(null);
      client.invalidateQueries();
      toast("Chapter saved");
    } catch (e: any) {
      toast(e.message);
    }
  };
  return (
    <>
      <div className="view-actions">
        <p className="explain">
          Suggested chapters are starting points. Name the history your way.
        </p>
        <CloudButton kind="eras" />
        <button onClick={() => setEditing({})}>
          <Plus size={15} />
          Add an era
        </button>
      </div>
      <State query={q}>
        {(d) => (
          <>
            <Panel
              title="The shape of your history"
              subtitle="Drag the zoom handles to explore a stretch of time"
            >
              <Chart
                label="Zoomable monthly group chat activity"
                option={{
                  xAxis: {
                    type: "category",
                    data: d.activity.map((r: any) => r.month),
                  },
                  yAxis: { type: "value" },
                  dataZoom: [
                    { type: "inside" },
                    { type: "slider", height: 16, bottom: 0 },
                  ],
                  grid: { bottom: 60 },
                  series: [
                    {
                      type: "bar",
                      data: d.activity.map((r: any) => r.count),
                      itemStyle: {
                        color: "#df7253",
                        borderRadius: [3, 3, 0, 0],
                      },
                    },
                  ],
                }}
                onClick={(p) =>
                  open({
                    title: p.name,
                    extra: {
                      start: dayStart(p.name + "-01"),
                      end: monthEnd(p.name),
                    },
                  })
                }
              />
            </Panel>
            <div className="section-label">
              <Layers3 size={16} />
              <h3>The chapters</h3>
              <span>{d.eras.length} eras</span>
            </div>
            {d.eras.length ? (
              <div className="era-grid">
                {d.eras.map((e: Era, i: number) => (
                  <article
                    className="era-card"
                    key={e.id}
                    style={
                      { "--era-color": COLORS[i % 6] } as React.CSSProperties
                    }
                  >
                    <div className="era-top">
                      <small>CHAPTER {String(i + 1).padStart(2, "0")}</small>
                      <label>
                        <input
                          type="checkbox"
                          checked={merge.includes(e.id)}
                          onChange={(ev) =>
                            setMerge((s) =>
                              ev.target.checked
                                ? [...s, e.id]
                                : s.filter((id) => id !== e.id),
                            )
                          }
                        />
                        Select
                      </label>
                    </div>
                    <h3>{e.name}</h3>
                    <time>
                      {date(e.start, { month: "short", year: "numeric" })} —{" "}
                      {date(e.end, { month: "short", year: "numeric" })}
                    </time>
                    <p>{e.summary}</p>
                    <div className="era-bottom">
                      <button
                        className="text-button"
                        onClick={() =>
                          open({
                            title: e.name,
                            extra: { start: e.start, end: e.end },
                          })
                        }
                      >
                        Enter this era
                        <ArrowRight size={14} />
                      </button>
                      <button
                        className="icon-button"
                        aria-label={`Edit ${e.name}`}
                        onClick={() => setEditing(e)}
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        className="text-button"
                        onClick={async () => {
                          const point = prompt("Split date (YYYY-MM-DD)");
                          if (!point) return;
                          const split = dayStart(point);
                          if (
                            !Number.isFinite(split) ||
                            split <= e.start ||
                            split >= e.end
                          ) {
                            toast("Choose a date inside this era");
                            return;
                          }
                          await mutate(
                            `/workspaces/${wid}/eras/${e.id}`,
                            { ...e, end: split - 1 },
                            "PUT",
                          );
                          await mutate(`/workspaces/${wid}/eras`, {
                            ...e,
                            name: e.name + " · Part 2",
                            start: split,
                          });
                          client.invalidateQueries();
                        }}
                      >
                        Split
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <Empty title="A history waiting for chapters">
                <p>Import more history or add your first era.</p>
              </Empty>
            )}
            {merge.length >= 2 && (
              <button
                onClick={async () => {
                  const selected = d.eras.filter((e: Era) =>
                    merge.includes(e.id),
                  );
                  await mutate(`/workspaces/${wid}/eras`, {
                    name: selected.map((e: Era) => e.name).join(" & "),
                    start: Math.min(...selected.map((e: Era) => e.start)),
                    end: Math.max(...selected.map((e: Era) => e.end)),
                    sources: selected.flatMap((e: Era) => e.sources),
                    summary: "Combined chapter",
                  });
                  for (const e of selected)
                    await mutate(
                      `/workspaces/${wid}/eras/${e.id}`,
                      undefined,
                      "DELETE",
                    );
                  setMerge([]);
                  client.invalidateQueries();
                }}
              >
                Merge selected eras
              </button>
            )}
            <div className="section-label">
              <Zap size={16} />
              <h3>Moments worth revisiting</h3>
            </div>
            <div className="event-list">
              {d.events.map((e: any) => (
                <article className="event" key={e.id}>
                  <div className="event-date">
                    {date(e.ts, { month: "short", day: "numeric" })}
                    <small>{date(e.ts, { year: "numeric" })}</small>
                  </div>
                  <span className={`event-icon ${e.kind}`}>
                    <Zap size={17} />
                  </span>
                  <div>
                    <span className="badge">{e.kind}</span>
                    <h3>{e.title}</h3>
                    <p>{e.summary}</p>
                  </div>
                  <Sources ids={e.sources} label="Revisit" />
                </article>
              ))}
            </div>
            <Narratives kind="eras" />
          </>
        )}
      </State>
      {editing && (
        <Modal
          title={editing.id ? "Edit this chapter" : "Add a chapter"}
          close={() => setEditing(null)}
        >
          <form className="form" onSubmit={save}>
            <label>
              Name
              <input name="name" required defaultValue={editing.name} />
            </label>
            <div className="two-inputs">
              <label>
                Start
                <input
                  type="date"
                  name="start"
                  required
                  defaultValue={
                    editing.start
                      ? new Date(editing.start * 1000)
                          .toISOString()
                          .slice(0, 10)
                      : ""
                  }
                />
              </label>
              <label>
                End
                <input
                  type="date"
                  name="end"
                  required
                  defaultValue={
                    editing.end
                      ? new Date(editing.end * 1000).toISOString().slice(0, 10)
                      : ""
                  }
                />
              </label>
            </div>
            <label>
              The story
              <textarea name="summary" defaultValue={editing.summary} />
            </label>
            <button className="primary">Save chapter</button>
            {editing.id && (
              <button
                type="button"
                className="danger"
                onClick={async () => {
                  await mutate(
                    `/workspaces/${wid}/eras/${editing.id}`,
                    undefined,
                    "DELETE",
                  );
                  setEditing(null);
                  client.invalidateQueries();
                }}
              >
                Delete chapter
              </button>
            )}
          </form>
        </Modal>
      )}
    </>
  );
}

function People() {
  const q = useData("analytics/overview");
  const { people, open, wid, toast } = useApp();
  const [selected, setSelected] = useState("");
  const [editing, setEditing] = useState<Person | null>(null);
  const profile = useData(
    `people/${encodeURIComponent(selected)}`,
    {},
    Boolean(selected),
  );
  return (
    <>
      <State query={q}>
        {(d) => (
          <div className="people-grid">
            {d.people.map((p: any) => (
              <button
                className={`person-card ${selected === p.id ? "selected" : ""}`}
                key={p.id}
                onClick={() => setSelected(p.id)}
              >
                <Avatar person={p} size="large" />
                <h3>{p.name}</h3>
                <p>{(p.share * 100).toFixed(1)}% of the conversation</p>
                <div>
                  <strong>
                    {num(p.messages)}
                    <small>messages</small>
                  </strong>
                  <strong>
                    {p.reactions_per_message.toFixed(2)}
                    <small>reactions / msg</small>
                  </strong>
                </div>
                <span className="text-button">
                  Get to know their stats
                  <ArrowRight size={13} />
                </span>
              </button>
            ))}
          </div>
        )}
      </State>
      {selected ? (
        <State query={profile}>
          {(d) => (
            <>
              <div className="section-label">
                <h3>
                  {people.find((p) => p.id === selected)?.name}’s corner of the
                  chat
                </h3>
                <button
                  onClick={() =>
                    setEditing(people.find((p) => p.id === selected)!)
                  }
                >
                  <Pencil size={14} />
                  Name & identity
                </button>
                <button
                  onClick={() =>
                    open({
                      title: "Member messages",
                      extra: { person: selected },
                    })
                  }
                >
                  Explore messages
                  <ArrowRight size={14} />
                </button>
              </div>
              <div className="stats-grid">
                <MiniStat
                  title="Active days"
                  value={num(d.totals.active_days)}
                />
                <MiniStat
                  title="Longest streak"
                  value={`${d.longest_streak} days`}
                />
                <MiniStat title="Words shared" value={num(d.totals.words)} />
                <MiniStat
                  title="Typical length"
                  value={`${Math.round(d.people[0]?.avg_length ?? 0)} characters`}
                />
              </div>
              <div className="grid-even">
                <Panel title="Their vocabulary">
                  <div className="word-cloud">
                    {d.favorite_words.map((w: any) => (
                      <button
                        key={w.word}
                        onClick={() =>
                          open({
                            title: `${w.word} by this member`,
                            extra: { person: selected },
                            word: { q: w.word },
                          })
                        }
                        style={{
                          fontSize: Math.max(
                            14,
                            Math.min(30, 12 + w.count / 10),
                          ),
                        }}
                      >
                        {w.word}
                        <small>{num(w.count)}</small>
                      </button>
                    ))}
                  </div>
                </Panel>
                <Panel title="Signature phrases & emoji">
                  <div className="phrase-list">
                    {d.phrases.map((w: any) => (
                      <span key={w.word}>
                        {w.word}
                        <strong>{num(w.count)}</strong>
                      </span>
                    ))}
                  </div>
                  <div className="emoji-list">
                    {d.emoji.map((w: any) => (
                      <span key={w.word}>
                        {w.word}
                        <small>{num(w.count)}</small>
                      </span>
                    ))}
                  </div>
                </Panel>
                <Panel title="When they show up">
                  <Chart
                    label="Member activity by hour and weekday"
                    option={{
                      tooltip: { position: "top" },
                      xAxis: {
                        type: "category",
                        data: Array.from({ length: 24 }, (_, i) => `${i}:00`),
                      },
                      yAxis: {
                        type: "category",
                        data: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                      },
                      visualMap: {
                        show: false,
                        min: 0,
                        max: Math.max(1, ...d.heatmap.map((r: any) => r.count)),
                        inRange: {
                          color: [
                            "#f2eadf",
                            people.find((p) => p.id === selected)?.color,
                          ],
                        },
                      },
                      series: [
                        {
                          type: "heatmap",
                          data: d.heatmap.map((r: any) => [
                            r.hour,
                            r.weekday,
                            r.count,
                          ]),
                        },
                      ],
                    }}
                  />
                </Panel>
                <Panel title="Topics & message lengths">
                  <div className="chips">
                    {d.topics.map((t: any) => (
                      <span key={t.id}>
                        {t.label} · {num(t.count)}
                      </span>
                    ))}
                  </div>
                  <Chart
                    label="Distribution of member message lengths in words"
                    height={190}
                    option={{
                      xAxis: {
                        type: "category",
                        data: Object.keys(d.word_lengths).map(
                          (x) => x + "–" + (+x + 4),
                        ),
                      },
                      yAxis: { type: "value" },
                      series: [
                        {
                          type: "bar",
                          data: Object.values(d.word_lengths),
                          itemStyle: {
                            color: people.find((p) => p.id === selected)?.color,
                            borderRadius: [3, 3, 0, 0],
                          },
                        },
                      ],
                    }}
                  />
                </Panel>
              </div>
            </>
          )}
        </State>
      ) : (
        <p className="explain center">
          Select a member to explore their habits, language, and interests.
        </p>
      )}
      {editing && (
        <Modal title="Names & identities" close={() => setEditing(null)}>
          <form
            className="form"
            onSubmit={async (e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              try {
                await mutate(
                  `/workspaces/${wid}/people/${encodeURIComponent(editing.id)}`,
                  { name: f.get("name"), merge_into: f.get("merge") || null },
                  "PATCH",
                );
                client.invalidateQueries();
                setEditing(null);
                setSelected("");
                toast("Member updated");
              } catch (e: any) {
                toast(e.message);
              }
            }}
          >
            <label>
              Display name
              <input name="name" defaultValue={editing.name} />
            </label>
            <label>
              Combine with another identity
              <select name="merge">
                <option value="">Keep this identity</option>
                {people
                  .filter((p) => p.id !== editing.id)
                  .map((p) => (
                    <option value={p.id} key={p.id}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </label>
            <p className="footnote">
              Combining identities treats their messages and reactions as one
              person, including future refreshes.
            </p>
            <button className="primary">Save identity</button>
          </form>
        </Modal>
      )}
    </>
  );
}

function MiniStat({ title, value }: { title: string; value: string }) {
  return (
    <div className="stat-card mini">
      <small>{title}</small>
      <strong>{value}</strong>
    </div>
  );
}
function Reactions() {
  const [minimum, setMinimum] = useState(20);
  const [metric, setMetric] = useState("reactions_per_message");
  const q = useData("analytics/reactions", { minimum });
  const { people, open } = useApp();
  return (
    <>
      <div className="view-actions">
        <p className="explain">
          Who brings the laughs? Who hands out the love?
        </p>
        <label className="inline-label">
          Minimum messages
          <input
            type="number"
            min={1}
            value={minimum}
            onChange={(e) => setMinimum(Math.max(1, +e.target.value))}
          />
        </label>
      </div>
      <State query={q}>
        {(d) => {
          const types: Record<string, number> = {};
          d.matrix.forEach(
            (r: any) => (types[r.type] = (types[r.type] ?? 0) + r.count),
          );
          const given: Record<string, any> = {};
          d.given.forEach((r: any) => {
            given[r.actor] ??= { actor: r.actor, count: 0 };
            given[r.actor].count += r.count;
          });
          const matrix = people.flatMap((p, x) =>
            people.map((r, y) => [
              x,
              y,
              d.matrix
                .filter((n: any) => n.actor === p.id && n.recipient === r.id)
                .reduce((s: number, n: any) => s + n.count, 0),
            ]),
          );
          const rank =
            metric === "reactions_per_message"
              ? d.rankings
              : [...d.people]
                  .filter(
                    (p: any) =>
                      metric !== "reaction_rate" || p.messages >= minimum,
                  )
                  .sort((a: any, b: any) => b[metric] - a[metric]);
          return (
            <>
              <div className="grid-even">
                <Panel
                  title="The crowd favorites"
                  subtitle="Received reactions. Zero-reaction messages included."
                  action={
                    <select
                      aria-label="Reaction ranking"
                      value={metric}
                      onChange={(e) => setMetric(e.target.value)}
                    >
                      <option value="reactions_per_message">Per message</option>
                      <option value="reactions">Total received</option>
                      <option value="reaction_rate">
                        % of messages reacted to
                      </option>
                    </select>
                  }
                >
                  <Bar
                    rows={rank}
                    field={metric}
                    sample="messages"
                    onClick={(p) =>
                      open({
                        title: `Messages from ${p.name}`,
                        extra: { person: p.id },
                      })
                    }
                  />
                  {rank.length === 0 && (
                    <Empty title="No members meet this threshold" />
                  )}
                  <p className="footnote">
                    Each rate includes all messages; the sample size appears
                    under each member.
                  </p>
                </Panel>
                <Panel
                  title="The generous ones"
                  subtitle="Observed reaction additions, by giver"
                >
                  <Bar
                    rows={Object.values(given).sort(
                      (a: any, b: any) => b.count - a.count,
                    )}
                    field="count"
                    onClick={(p) =>
                      open({
                        title: "Messages they reacted to",
                        reaction: { actor: p.actor, basis: "given" },
                      })
                    }
                  />
                  <p className="footnote">
                    Given uses reaction-event dates; received uses
                    target-message dates. Full history may be unavailable.
                  </p>
                </Panel>
                <Panel title="A language of reactions">
                  <Chart
                    label="Breakdown by reaction type"
                    option={{
                      tooltip: { trigger: "item" },
                      legend: { type: "scroll", bottom: 0, left: 0, right: 0 },
                      series: [
                        {
                          type: "pie",
                          top: 0,
                          bottom: 44,
                          radius: ["45%", "72%"],
                          center: ["50%", "50%"],
                          label: { show: false },
                          color: COLORS,
                          data: Object.entries(types).map(([name, value]) => ({
                            name: `${REACTIONS[name] ?? name} ${name}`,
                            reaction_type: name,
                            value,
                          })),
                        },
                      ],
                    }}
                    onClick={(p) =>
                      open({
                        title: "Messages with this reaction",
                        reaction: { reaction_type: p.data.reaction_type },
                      })
                    }
                  />
                </Panel>
                <Panel
                  title="Who reacts to whom?"
                  subtitle="Columns give. Rows receive."
                >
                  <Chart
                    label="Reaction giver to recipient matrix"
                    option={{
                      tooltip: {
                        formatter: (p: any) =>
                          `${people[p.value[0]]?.name} → ${people[p.value[1]]?.name}: ${p.value[2]}`,
                      },
                      xAxis: {
                        type: "category",
                        data: people.map((p) => p.name),
                      },
                      yAxis: {
                        type: "category",
                        data: people.map((p) => p.name),
                      },
                      visualMap: {
                        show: false,
                        min: 0,
                        max: Math.max(1, ...matrix.map((r) => r[2])),
                        inRange: { color: ["#f3ede3", "#edbcaa", "#ce694b"] },
                      },
                      series: [
                        {
                          type: "heatmap",
                          data: matrix,
                          label: { show: true, color: "#574a40" },
                        },
                      ],
                    }}
                    onClick={(p) =>
                      open({
                        title: `${people[p.value[0]].name} → ${people[p.value[1]].name}`,
                        reaction: {
                          actor: people[p.value[0]].id,
                          recipient: people[p.value[1]].id,
                        },
                      })
                    }
                  />
                </Panel>
              </div>
              <Panel
                title="Reactions through time"
                subtitle="Current received reactions by target-message month"
              >
                <Chart
                  label="Monthly reaction types"
                  option={{
                    legend: { type: "scroll", bottom: 0, left: 0, right: 0 },
                    grid: {
                      left: 42,
                      right: 20,
                      top: 20,
                      bottom: 65,
                      containLabel: true,
                    },
                    xAxis: {
                      type: "category",
                      data: [
                        ...new Set(d.trend.map((r: any) => r.month)),
                      ].sort(),
                    },
                    yAxis: { type: "value" },
                    series: [...new Set(d.trend.map((r: any) => r.type))].map(
                      (type: any, i: number) => ({
                        name: type,
                        type: "bar",
                        stack: "reactions",
                        itemStyle: { color: COLORS[i % COLORS.length] },
                        data: [...new Set(d.trend.map((r: any) => r.month))]
                          .sort()
                          .map(
                            (month) =>
                              d.trend.find(
                                (r: any) =>
                                  r.month === month && r.type === type,
                              )?.count ?? 0,
                          ),
                      }),
                    ),
                  }}
                  onClick={(p) =>
                    open({
                      title: `${p.seriesName} reactions in ${p.name}`,
                      reaction: { reaction_type: p.seriesName },
                      extra: {
                        start: dayStart(p.name + "-01"),
                        end: monthEnd(p.name),
                      },
                    })
                  }
                />
              </Panel>
              <Panel
                title="Hall of fame"
                subtitle="The original messages, with their current reactions"
              >
                <div className="message-grid">
                  {d.top_messages.map((m: Message) => (
                    <MessageCard m={m} key={m.id} />
                  ))}
                </div>
              </Panel>
              {d.unresolved > 0 && (
                <p className="footnote">
                  {num(d.unresolved)} reaction records point to unavailable
                  messages.
                </p>
              )}
            </>
          );
        }}
      </State>
    </>
  );
}

function SemanticWords({ term }: { term: string }) {
  const { wid, filters, open, toast, go } = useApp();
  const [threshold, setThreshold] = useState(0.35);
  const [minimum, setMinimum] = useState(20);
  const [metric, setMetric] = useState("per_1000");
  const [busy, setBusy] = useState(false);
  const q = useQuery({
    queryKey: [wid, "semantic-words", filters, term, threshold, minimum],
    queryFn: () =>
      request(
        `/workspaces/${wid}/semantic-words?${params({ ...filters, q: term, threshold, minimum })}`,
      ),
    enabled: Boolean(wid && term.trim()),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.status) ? 2000 : false,
  });
  const evidence = (title: string, extra: Filters = {}) =>
    open({
      title,
      semantic: { q: term, threshold },
      extra,
    });
  async function analyze() {
    setBusy(true);
    try {
      await mutate(`/workspaces/${wid}/semantic-words/analyze`, {
        q: term,
        threshold,
      });
      await client.invalidateQueries({ queryKey: [wid] });
      toast("Semantic comparison queued");
    } catch (e: any) {
      toast(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Panel
        title="Explore a meaning"
        subtitle="Local semantic matching of each member’s own messages"
      >
        <p className="explain">
          Try a topic like “girls”, or describe what you mean: “dating, crushes,
          and romantic relationships”. Matches can use different words. Each
          message is counted once; other speakers in the conversation get no
          automatic credit.
        </p>
        <div className="form">
          <label>
            Similarity cutoff: {threshold.toFixed(2)}
            <input
              aria-label="Semantic similarity cutoff"
              type="range"
              min="0.1"
              max="0.95"
              step="0.05"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
            />
          </label>
          <p className="footnote">
            Lower includes broader associations; higher keeps closer matches.
            Cosine similarity is not a confidence percentage.
          </p>
          <label>
            Minimum authored messages per member
            <input
              type="number"
              min={1}
              max={1000000}
              value={minimum}
              onChange={(e) =>
                setMinimum(
                  Math.max(1, Math.min(1000000, Number(e.target.value) || 1)),
                )
              }
            />
          </label>
        </div>
      </Panel>
      {!term.trim() ? (
        <Empty title="Enter a topic to explore" />
      ) : (
        <State query={q}>
          {(d) =>
            !d.ready ? (
              <Panel
                title={
                  d.status === "index_required"
                    ? "Build your message index first"
                    : `Semantic matches for “${term}”`
                }
              >
                {d.status === "index_required" ? (
                  <>
                    <p className="explain">
                      Build or rebuild the local semantic index in Settings
                      &amp; analysis. This version indexes short messages
                      individually too.
                    </p>
                    <button className="primary" onClick={() => go("settings")}>
                      Open Settings &amp; analysis
                    </button>
                  </>
                ) : ["queued", "running"].includes(d.status) ? (
                  <>
                    <p role="status">
                      {d.message || "Waiting to compare every indexed message…"}
                    </p>
                    <progress value={d.progress ?? 0} max={1} />
                    <p className="footnote">
                      You can keep browsing. Progress and cancellation are
                      available in Settings &amp; analysis.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="explain">
                      Compare this meaning against the full archive. Results are
                      cached locally, so date, member, and era filters can
                      update without rerunning the model.
                    </p>
                    {d.message && <p role="status">{d.message}</p>}
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={analyze}
                    >
                      {busy ? "Queuing…" : "Analyze meaning"}
                    </button>
                  </>
                )}
              </Panel>
            ) : (
              <>
                <div className="stats-grid">
                  <MiniStat
                    title="Semantically matching messages"
                    value={num(d.matching_messages)}
                  />
                  <MiniStat
                    title="Authored messages in selection"
                    value={num(d.total_messages)}
                  />
                  <MiniStat
                    title="Matches per 1,000 messages"
                    value={
                      d.total_messages
                        ? (
                            (d.matching_messages * 1000) /
                            d.total_messages
                          ).toFixed(2)
                        : "—"
                    }
                  />
                  <MiniStat
                    title="Similarity cutoff"
                    value={threshold.toFixed(2)}
                  />
                </div>
                <div className="grid-even">
                  <Panel
                    title={`Who talks about “${term}” most?`}
                    subtitle="Model-selected matches, normalized by all authored messages under the same filters."
                    action={
                      <select
                        aria-label="Semantic ranking metric"
                        value={metric}
                        onChange={(e) => setMetric(e.target.value)}
                      >
                        <option value="per_1000">Per 1,000 messages</option>
                        <option value="matches">Matching messages</option>
                      </select>
                    }
                  >
                    <Bar
                      rows={[...d.people].sort(
                        (a: any, b: any) => b[metric] - a[metric],
                      )}
                      field={metric}
                      sample="messages"
                      onClick={(p) =>
                        evidence(`${p.name} talking about “${term}”`, {
                          person: p.id,
                        })
                      }
                    />
                    {!d.people.length && (
                      <Empty title="No members meet this sample size" />
                    )}
                    <p className="footnote">
                      All authored messages count in the denominator, including
                      messages without text or a semantic match. Reactions,
                      system events, OCR, and transcripts are excluded.
                    </p>
                  </Panel>
                  <Panel
                    title="The topic through time"
                    subtitle="Matching authored messages by month"
                  >
                    <Chart
                      label="Semantic topic matches over time"
                      option={{
                        xAxis: {
                          type: "category",
                          data: d.trend.map((r: any) => r.date),
                        },
                        yAxis: { type: "value" },
                        series: [
                          {
                            type: "bar",
                            data: d.trend.map((r: any) => r.count),
                            itemStyle: { color: "#638b70" },
                          },
                        ],
                      }}
                      onClick={(p) =>
                        evidence(`“${term}” in ${p.name}`, {
                          start: dayStart(p.name + "-01"),
                          end: monthEnd(p.name),
                        })
                      }
                    />
                  </Panel>
                </div>
                <Panel
                  title="Check the meaning matches"
                  subtitle="Similarity can include false positives or miss subtle references. Inspect the original messages to judge the result."
                  action={
                    <button
                      className="subtle"
                      onClick={() =>
                        evidence(`All semantic matches for “${term}”`)
                      }
                    >
                      Browse all semantic matches
                    </button>
                  }
                >
                  <div className="message-grid">
                    {d.messages.map((m: Message) => (
                      <MessageCard key={m.id} m={m} />
                    ))}
                  </div>
                  {!d.messages.length && (
                    <Empty title="No messages meet this cutoff" />
                  )}
                </Panel>
              </>
            )
          }
        </State>
      )}
    </>
  );
}

function Words() {
  const [draft, setDraft] = useState("lmao");
  const [term, setTerm] = useState("lmao");
  const [mode, setMode] = useState("word");
  const [rank, setRank] = useState("occurrences");
  const q = useData("words", { q: term, mode }, mode !== "semantic");
  const { open } = useApp();
  return (
    <>
      <form
        className="search-box"
        onSubmit={(e) => {
          e.preventDefault();
          setTerm(draft);
        }}
      >
        <Search size={21} />
        <input
          aria-label="Word or phrase"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Who says ‘lmao’ the most?"
        />
        <select
          aria-label="Word matching mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="word">Whole word</option>
          <option value="phrase">Exact phrase</option>
          <option value="substring">Substring</option>
          <option value="variants">English variants</option>
          <option value="semantic">Semantic meaning</option>
        </select>
        <button className="primary">
          Explore
          <ArrowRight size={15} />
        </button>
      </form>
      <div className="quick-terms">
        <span>TRY A CLASSIC</span>
        {["lmao", "say less", "iconic", "the council", "coffee"].map((w) => (
          <button
            key={w}
            onClick={() => {
              setDraft(w);
              setTerm(w);
              setMode(w.includes(" ") ? "phrase" : "word");
            }}
          >
            {w}
          </button>
        ))}
      </div>
      {mode === "semantic" ? (
        <SemanticWords term={term} />
      ) : (
        <State query={q}>
          {(d) => (
            <>
              <div className="stats-grid">
                <MiniStat
                  title={`Uses of “${term}”`}
                  value={num(d.occurrences)}
                />
                <MiniStat
                  title="Messages containing it"
                  value={num(d.matching_messages)}
                />
                <MiniStat title="Earliest observed use" value={date(d.first)} />
                <MiniStat title="Latest observed use" value={date(d.last)} />
              </div>
              <div className="grid-even">
                <Panel
                  title={`Who owns “${term}”?`}
                  subtitle="Compare total usage or account for how much each person writes."
                  action={
                    <select
                      aria-label="Word ranking metric"
                      value={rank}
                      onChange={(e) => setRank(e.target.value)}
                    >
                      <option value="occurrences">Total uses</option>
                      <option value="messages">Matching messages</option>
                      <option value="per_1000">Per 1,000 words</option>
                    </select>
                  }
                >
                  <Bar
                    rows={[...d.people].sort(
                      (a: any, b: any) => b[rank] - a[rank],
                    )}
                    field={rank}
                    sample={rank === "per_1000" ? "total_words" : undefined}
                    onClick={(p) =>
                      open({
                        title: `${p.name} saying “${term}”`,
                        word: { q: term, mode },
                        extra: { person: p.id },
                      })
                    }
                  />
                  {!d.people.length && (
                    <Empty title="No matches in this selection" />
                  )}
                </Panel>
                <Panel
                  title="A phrase through time"
                  subtitle="Monthly occurrences in authored messages"
                >
                  <Chart
                    label="Word usage over time"
                    option={{
                      xAxis: {
                        type: "category",
                        data: d.trend.map((r: any) => r.date),
                      },
                      yAxis: { type: "value" },
                      series: [
                        {
                          type: "bar",
                          data: d.trend.map((r: any) => r.count),
                          itemStyle: {
                            color: "#638b70",
                            borderRadius: [4, 4, 0, 0],
                          },
                        },
                      ],
                    }}
                    onClick={(p) =>
                      open({
                        title: `“${term}” in ${p.name}`,
                        word: { q: term, mode },
                        extra: {
                          start: dayStart(p.name + "-01"),
                          end: monthEnd(p.name),
                        },
                      })
                    }
                  />
                </Panel>
              </div>
              {Object.keys(d.variants ?? {}).length > 0 && (
                <div className="chips">
                  {Object.entries(d.variants).map(([w, n]) => (
                    <span key={w}>
                      {w} · {n as number}
                    </span>
                  ))}
                </div>
              )}
              <Panel
                title="The receipts"
                subtitle="Click a message for the full exchange"
                action={
                  <button
                    className="subtle"
                    onClick={() =>
                      open({
                        title: `All matches for “${term}”`,
                        word: { q: term, mode },
                      })
                    }
                  >
                    Browse all matches
                  </button>
                }
              >
                <div className="message-grid">
                  {d.messages.slice(0, 12).map((m: Message) => (
                    <MessageCard key={m.id} m={m} />
                  ))}
                </div>
              </Panel>
            </>
          )}
        </State>
      )}
    </>
  );
}

function Conversations() {
  const q = useData("analytics/conversations");
  const { open, people } = useApp();
  return (
    <State query={q}>
      {(d) => (
        <>
          <p className="explain">
            A new session starts after {d.session_gap} minutes of silence. Reply
            links are explicit; shared sessions are inferred.
          </p>
          <div className="grid-even">
            <Panel title="Who starts things?">
              <Bar
                rows={d.starters.sort((a: any, b: any) => b.count - a.count)}
                field="count"
                onClick={(p) =>
                  open({
                    title: "Conversations they started",
                    extra: { started_by: p.starter },
                  })
                }
              />
            </Panel>
            <Panel
              title="In the conversation together"
              subtitle="Shared sessions, not a measure of friendship"
            >
              <Chart
                label="Co-participation network"
                onClick={(p) =>
                  open(
                    p.dataType === "edge"
                      ? {
                          title: "Shared conversations",
                          extra: {
                            person: p.data.source,
                            with_person: p.data.target,
                          },
                        }
                      : {
                          title: `${p.name} in conversation`,
                          extra: { person: p.data.id },
                        },
                  )
                }
                option={{
                  tooltip: { trigger: "item" },
                  series: [
                    {
                      type: "graph",
                      layout: "circular",
                      roam: true,
                      label: { show: true, position: "bottom" },
                      data: people.map((p) => ({
                        name: p.name,
                        id: p.id,
                        symbolSize: 44,
                        itemStyle: { color: p.color },
                      })),
                      links: d.co_participation.map((p: any) => ({
                        source: p.actor,
                        target: p.recipient,
                        value: p.count,
                        lineStyle: {
                          width: Math.max(1, Math.log(p.count)),
                          opacity: 0.3,
                        },
                      })),
                    },
                  ],
                }}
              />
            </Panel>
          </div>
          <Panel
            title="Explicit reply partners"
            subtitle="Only recorded reply links; time is measured from original message to reply"
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Replier</th>
                    <th>Original author</th>
                    <th>Replies</th>
                    <th>Average elapsed time</th>
                  </tr>
                </thead>
                <tbody>
                  {d.replies.map((r: any) => (
                    <tr
                      key={r.actor + r.recipient}
                      onClick={() =>
                        open({
                          title: "Explicit replies",
                          extra: { person: r.actor, reply_person: r.recipient },
                        })
                      }
                    >
                      <td>
                        <Member id={r.actor} />
                      </td>
                      <td>
                        <Member id={r.recipient} />
                      </td>
                      <td>{num(r.count)}</td>
                      <td>{Math.round(r.seconds / 60)} min</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!d.replies.length && (
              <Empty title="No explicit replies in this archive" />
            )}
          </Panel>
          <Panel
            title="Inferred response rhythms"
            subtitle="Adjacent different-speaker messages within a session; these are not explicit replies"
          >
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Next speaker</th>
                    <th>Previous speaker</th>
                    <th>Transitions</th>
                    <th>Average gap</th>
                  </tr>
                </thead>
                <tbody>
                  {d.inferred_responses.map((r: any) => (
                    <tr key={r.actor + r.recipient}>
                      <td>
                        <Member id={r.actor} />
                      </td>
                      <td>
                        <Member id={r.recipient} />
                      </td>
                      <td>{num(r.count)}</td>
                      <td>{Math.round(r.seconds)} sec</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel
            title="The longest nights (and afternoons)"
            subtitle="Open an exchange, then use Replay to watch it unfold"
          >
            <div className="session-list">
              {d.sessions.map((s: any) => (
                <button
                  className="session-row"
                  key={s.id}
                  onClick={() =>
                    open({
                      title: `Conversation on ${date(s.start)}`,
                      extra: { session: s.id },
                    })
                  }
                >
                  <span className="session-icon">
                    <MessageCircle size={18} />
                  </span>
                  <div>
                    <h4>{date(s.start)}</h4>
                    <p>
                      Started by {people.find((p) => p.id === s.starter)?.name}{" "}
                      · {Math.max(1, Math.round((s.end - s.start) / 60))}{" "}
                      minutes
                    </p>
                  </div>
                  <strong>
                    {num(s.filtered_count)}
                    <small>messages</small>
                  </strong>
                  <Play size={17} />
                </button>
              ))}
            </div>
          </Panel>
        </>
      )}
    </State>
  );
}

function Topics() {
  const q = useData("topics");
  const [draft, setDraft] = useState("");
  const [term, setTerm] = useState("");
  const [mode, setMode] = useState("hybrid");
  const search = useData("search", { q: term, mode }, Boolean(term));
  const { wid, open, toast } = useApp();
  return (
    <>
      <form
        className="search-box"
        onSubmit={(e) => {
          e.preventDefault();
          setTerm(draft);
        }}
      >
        <Search />
        <input
          aria-label="Search the history"
          placeholder="That time we almost missed our flight…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <select
          aria-label="Search mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="hybrid">Hybrid</option>
          <option value="keyword">Keywords</option>
          <option value="semantic">Meaning</option>
        </select>
        <button className="primary">
          Find it
          <ArrowRight size={15} />
        </button>
      </form>
      {term && (
        <State query={search}>
          {(d) => (
            <Panel
              title={`Found in the archive`}
              subtitle={
                d.mode_used === "keyword" && mode !== "keyword"
                  ? "Keyword results · build the local index to add semantic matches"
                  : `${d.items.length} results · ${d.mode_used} search`
              }
            >
              <div className="message-grid">
                {d.items.map((m: Message) => (
                  <MessageCard m={m} key={m.id} />
                ))}
              </div>
              {!d.items.length && (
                <Empty title="No supporting messages found" />
              )}
            </Panel>
          )}
        </State>
      )}
      <div className="section-label">
        <Sparkles size={17} />
        <h3>Ask your archive</h3>
      </div>
      <QuestionBox />
      <State query={q}>
        {(d) => (
          <>
            {!d.ready ? (
              <Panel>
                <Empty title="Give the history a little more meaning">
                  <p>
                    Build a local index to search by meaning and discover
                    conversation topics. The first run downloads model weights;
                    your messages stay here.
                  </p>
                  <button
                    className="primary"
                    onClick={async () => {
                      try {
                        await mutate(`/workspaces/${wid}/jobs`, {
                          kind: "semantic",
                        });
                        toast("Local analysis queued");
                        client.invalidateQueries();
                      } catch (e: any) {
                        toast(e.message);
                      }
                    }}
                  >
                    <Sparkles size={16} />
                    Build semantic index
                  </button>
                </Empty>
              </Panel>
            ) : (
              <>
                <div className="section-label">
                  <h3>What you keep coming back to</h3>
                </div>
                <div className="topic-grid">
                  {d.topics.map((t: any, i: number) => (
                    <article className="topic-card" key={t.id}>
                      <span
                        className="topic-icon"
                        style={{
                          background: COLORS[i % 6] + "22",
                          color: COLORS[i % 6],
                        }}
                      >
                        <Layers3 size={22} />
                      </span>
                      <h3>{t.label}</h3>
                      <p>{num(t.count)} messages</p>
                      <div className="chips">
                        {t.terms.map((w: string) => (
                          <span key={w}>{w}</span>
                        ))}
                      </div>
                      <button
                        className="text-button"
                        onClick={() =>
                          open({ title: t.label, extra: { topic: t.id } })
                        }
                      >
                        Follow this topic
                        <ArrowRight size={14} />
                      </button>
                    </article>
                  ))}
                </div>
                {d.topics.length === 0 && (
                  <Empty title="No stable topic clusters found">
                    <p>
                      The semantic index is ready; search still works. A small
                      or varied archive may not form clear clusters.
                    </p>
                  </Empty>
                )}
                <Panel title="Interests come and go">
                  <Chart
                    label="Topics over time"
                    option={{
                      color: COLORS,
                      xAxis: {
                        type: "category",
                        data: [
                          ...new Set(d.trend.map((r: any) => r.month)),
                        ].sort(),
                      },
                      yAxis: { type: "value" },
                      legend: { bottom: 0, type: "scroll" },
                      grid: { bottom: 65 },
                      series: d.topics.slice(0, 8).map((t: any) => ({
                        name: t.label,
                        type: "line",
                        smooth: true,
                        symbol: "none",
                        data: [...new Set(d.trend.map((r: any) => r.month))]
                          .sort()
                          .map(
                            (month) =>
                              d.trend.find(
                                (r: any) =>
                                  r.month === month && r.topic_id === t.id,
                              )?.count ?? 0,
                          ),
                      })),
                    }}
                  />
                </Panel>
              </>
            )}
          </>
        )}
      </State>
    </>
  );
}

function Lore() {
  const q = useData("lore");
  const [journey, setJourney] = useState<string>("");
  const detail = useData(`lore/${journey}/journey`, {}, Boolean(journey));
  const { open } = useApp();
  return (
    <>
      <div className="view-actions">
        <p className="explain">
          The things only this chat understands. Origins mean earliest observed
          use.
        </p>
        <CloudButton kind="lore" />
      </div>
      <State query={q}>
        {(d) => (
          <div className="lore-grid">
            {d.map((l: any, i: number) => (
              <article className="lore-card" key={l.id}>
                <div className="lore-number">
                  {String(i + 1).padStart(2, "0")}
                </div>
                <span className="badge">A RUNNING BIT</span>
                <h3>“{l.title}”</h3>
                <p>{l.summary}</p>
                <div className="lore-metrics">
                  <span>
                    <strong>{num(l.count)}</strong> messages
                  </span>
                  <span>
                    <strong>{l.people.length}</strong> members
                  </span>
                </div>
                <div className="lore-period">
                  {date(l.start)}
                  <span>→</span>
                  {date(l.end)}
                </div>
                <button
                  className="text-button"
                  onClick={() => setJourney(l.id)}
                >
                  Trace the lore <ArrowRight size={13} />
                </button>
              </article>
            ))}
            {d.length === 0 && (
              <Empty title="The lore takes time">
                <p>
                  Recurring phrases need several appearances across members. Try
                  widening the filters.
                </p>
              </Empty>
            )}
          </div>
        )}
      </State>
      {journey && (
        <Modal title="A bit through the years" close={() => setJourney("")}>
          <State query={detail}>
            {(d) => (
              <>
                <h3>“{d.title}”</h3>
                <p className="footnote">
                  Earliest observed use: {date(d.first)} ·{" "}
                  {num(d.matching_messages)} messages
                </p>
                <button
                  className="text-button"
                  onClick={() => {
                    setJourney("");
                    open({
                      title: d.title,
                      word: { q: d.title, mode: "phrase" },
                    });
                  }}
                >
                  Open every matching conversation
                </button>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Member</th>
                        <th>First observed</th>
                        <th>Uses</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...d.people]
                        .sort((a: any, b: any) => a.first - b.first)
                        .map((p: any) => (
                          <tr key={p.id}>
                            <td>{p.name}</td>
                            <td>{date(p.first)}</td>
                            <td>{num(p.occurrences)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                <Chart
                  label="Lore usage over time"
                  option={{
                    xAxis: {
                      type: "category",
                      data: d.trend.map((p: any) => p.date),
                    },
                    yAxis: { type: "value" },
                    series: [
                      {
                        type: "bar",
                        data: d.trend.map((p: any) => p.count),
                        itemStyle: { color: "#638b70" },
                      },
                    ],
                  }}
                  onClick={(p) => {
                    setJourney("");
                    open({
                      title: d.title,
                      word: { q: d.title, mode: "phrase" },
                      extra: {
                        start: dayStart(p.name + "-01"),
                        end: monthEnd(p.name),
                      },
                    });
                  }}
                />
                <h4>Related conversation candidates</h4>
                <p className="footnote">
                  Similar language or meaning may suggest callbacks; inspect the
                  context.
                </p>
                {d.related.map((m: Message) => (
                  <MessageCard
                    key={m.id}
                    m={m}
                    onClick={() => {
                      setJourney("");
                      open({ title: "Related conversation", mid: m.id });
                    }}
                  />
                ))}
              </>
            )}
          </State>
        </Modal>
      )}
      <Narratives kind="lore" />
    </>
  );
}

function Media() {
  const [draft, setDraft] = useState("");
  const [term, setTerm] = useState("");
  const [similar, setSimilar] = useState<string | undefined>();
  const q = useData("media", { q: term, similar });
  const { wid, open } = useApp();
  return (
    <>
      <form
        className="search-box"
        onSubmit={(e) => {
          e.preventDefault();
          setTerm(draft);
        }}
      >
        <Image />
        <input
          aria-label="Search media"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Find a screenshot, voice note, or photo…"
        />
        <button className="primary">Search media</button>
      </form>
      {similar && (
        <button onClick={() => setSimilar(undefined)}>
          Clear similarity filter
          <X size={13} />
        </button>
      )}
      <State query={q}>
        {(d) => (
          <>
            <div className="media-grid">
              {d.attachments.map((a: any) => (
                <article className="media-card" key={a.id}>
                  <div className="media-preview">
                    {!a.exists_local ? (
                      <span>File unavailable</span>
                    ) : a.mime?.startsWith("image/") ? (
                      <img
                        loading="lazy"
                        src={`${API}/workspaces/${wid}/attachments/${encodeURIComponent(a.id)}`}
                        alt={a.name}
                      />
                    ) : a.mime?.startsWith("video/") ? (
                      <video
                        controls
                        preload="metadata"
                        src={`${API}/workspaces/${wid}/attachments/${encodeURIComponent(a.id)}`}
                      />
                    ) : a.mime?.startsWith("audio/") ? (
                      <audio
                        controls
                        src={`${API}/workspaces/${wid}/attachments/${encodeURIComponent(a.id)}`}
                      />
                    ) : (
                      <a
                        href={`${API}/workspaces/${wid}/attachments/${encodeURIComponent(a.id)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open file
                        <ExternalLink size={15} />
                      </a>
                    )}
                  </div>
                  <div className="media-info">
                    <Member id={a.person_id} />
                    <time>{date(a.ts)}</time>
                    <h4>{a.name}</h4>
                    {a.extracted && (
                      <details>
                        <summary>
                          {a.annotation.text_source ?? "Extracted text"}
                        </summary>
                        <p>{a.extracted}</p>
                      </details>
                    )}
                    {a.annotation.error && (
                      <p className="error-note">{a.annotation.error}</p>
                    )}
                    <div className="media-actions">
                      <button
                        className="text-button"
                        onClick={() =>
                          open({ title: "Media in context", mid: a.message_id })
                        }
                      >
                        View context
                        <ArrowRight size={13} />
                      </button>
                      {a.hash && (
                        <button onClick={() => setSimilar(a.id)}>
                          Find similar
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              ))}
            </div>
            {!d.attachments.length && (
              <Panel>
                <Empty
                  title={
                    term
                      ? "No media matches"
                      : "The memories behind the messages"
                  }
                >
                  <p>
                    {term
                      ? "Try another description or run OCR in Settings."
                      : "Imported attachments appear here. Missing files are tracked, and local OCR, transcription, and image analysis can be started in Settings."}
                  </p>
                </Empty>
              </Panel>
            )}
            <div className="grid-even">
              <Panel title="Your shared corner of the internet">
                <div className="domain-list">
                  {d.domains.map((r: any) => (
                    <div key={r.domain}>
                      <span>{r.domain}</span>
                      <strong>{num(r.count)}</strong>
                    </div>
                  ))}
                </div>
                {!d.domains.length && (
                  <p className="footnote">No shared URLs in this selection.</p>
                )}
              </Panel>
              <Panel title="The memes that came back">
                <div className="domain-list">
                  {d.duplicates.map((r: any) => (
                    <button key={r.hash} onClick={() => setSimilar(r.example)}>
                      <span>Repeated image</span>
                      <strong>{r.count} times</strong>
                    </button>
                  ))}
                </div>
                {!d.duplicates.length && (
                  <p className="footnote">
                    Run local media analysis to discover repeated images.
                  </p>
                )}
              </Panel>
            </div>
            <Panel
              title="Link archive"
              subtitle="Stored links only. Previews are never fetched automatically."
            >
              <div className="link-list">
                {d.links.map((l: any) => (
                  <div key={l.id}>
                    <div>
                      <Member id={l.person_id} />
                      <small>{date(l.ts)}</small>
                      <a href={l.url} target="_blank" rel="noreferrer">
                        {l.url}
                        <ExternalLink size={12} />
                      </a>
                    </div>
                    <button
                      className="text-button"
                      onClick={() =>
                        open({ title: "Shared link", mid: l.message_id })
                      }
                    >
                      Context
                      <ArrowRight size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </Panel>
          </>
        )}
      </State>
    </>
  );
}

function Recaps() {
  const q = useData("analytics/recap");
  const manual = useData("awards");
  const { wid, people, toast, open } = useApp();
  const [kind, setKind] = useState("who");
  const [game, setGame] = useState<any>();
  const [answer, setAnswer] = useState<any>();
  const [award, setAward] = useState<any>(null);
  const card = useRef<HTMLDivElement>(null);
  async function next() {
    try {
      setGame(
        await request(
          `/workspaces/${wid}/games?${params({ ...useFiltersSnapshot(), kind })}`,
        ),
      );
      setAnswer(undefined);
    } catch (e: any) {
      toast(e.message);
    }
  }
  const app = useApp();
  function useFiltersSnapshot() {
    return app.filters;
  }
  return (
    <>
      <div className="view-actions">
        <p className="explain">
          A little celebration of a lot of conversation.
        </p>
        <CloudButton kind="recap" />
        <button
          disabled={!q.data || q.isLoading}
          onClick={async () => {
            if (card.current) {
              try {
                const a = document.createElement("a");
                a.href = await toPng(card.current, {
                  pixelRatio: 2,
                  backgroundColor: "#faf8f4",
                });
                a.download = "group-chat-recap.png";
                a.click();
              } catch (e: any) {
                toast(e.message);
              }
            }
          }}
        >
          <ArrowDownToLine size={15} />
          Save recap card
        </button>
      </div>
      <State query={q}>
        {(d) => (
          <>
            <div ref={card} className="recap-card">
              <span className="badge">THE GROUP CHAT, REMEMBERED</span>
              <h2>
                Same people.
                <br />
                So many stories.
              </h2>
              <p>
                {date(d.totals.start)} — {date(d.totals.end)}
              </p>
              <div className="recap-numbers">
                <span>
                  <strong>{num(d.totals.messages)}</strong>messages
                </span>
                <span>
                  <strong>{num(d.totals.reactions)}</strong>reactions
                </span>
                <span>
                  <strong>{num(d.totals.active_days)}</strong>days together
                </span>
              </div>
              <div className="recap-members">
                {people.map((p) => (
                  <Avatar key={p.id} person={p} />
                ))}
              </div>
              <small>GROUP CHAT EXPLORER · YOUR HISTORY, AT HOME</small>
            </div>
            <div className="section-label">
              <Trophy size={17} />
              <h3>The unofficial awards</h3>
              <button onClick={() => setAward({})}>
                <Pencil size={13} />
                Add your own
              </button>
            </div>
            <div className="award-grid">
              {[...d.awards, ...(manual.data ?? [])].map(
                (a: any, i: number) => (
                  <article className="award-card" key={i}>
                    <Trophy size={26} />
                    <h3>{a.title}</h3>
                    <Member id={a.person} />
                    <p>{a.metric}</p>
                    <button
                      className="text-button"
                      onClick={() =>
                        open({ title: a.title, extra: { person: a.person } })
                      }
                    >
                      View messages <ArrowRight size={12} />
                    </button>
                    {a.id && (
                      <button
                        className="text-button"
                        aria-label={`Edit ${a.title}`}
                        onClick={() => setAward(a)}
                      >
                        Edit award <Pencil size={12} />
                      </button>
                    )}
                  </article>
                ),
              )}
            </div>
            <Panel title="Different eras, different energy">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Era</th>
                      <th>Messages</th>
                      <th>Words</th>
                      <th>Reactions</th>
                      <th>Members</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.era_comparison.map((e: any) => (
                      <tr
                        key={e.id}
                        onClick={() =>
                          open({ title: e.name, extra: { era: e.id } })
                        }
                      >
                        <td>{e.name}</td>
                        <td>{num(e.messages)}</td>
                        <td>{num(e.words)}</td>
                        <td>{num(e.reactions)}</td>
                        <td>{e.members}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </>
        )}
      </State>
      <Narratives kind="recap" />
      <Panel
        title="How well do you know your chat?"
        subtitle="Actual messages. Actual memories. No cheating."
      >
        <div className="game-toolbar">
          <div className="segmented">
            {[
              ["who", "Who said it?"],
              ["finish", "Finish the quote"],
              ["year", "Guess the year"],
            ].map(([k, n]) => (
              <button
                className={kind === k ? "active" : ""}
                key={k}
                onClick={() => {
                  setKind(k);
                  setGame(undefined);
                  setAnswer(undefined);
                }}
              >
                {n}
              </button>
            ))}
          </div>
          <button onClick={next}>
            <Shuffle size={15} />
            {game ? "Next round" : "Play a round"}
          </button>
        </div>
        {game && (
          <div className="game">
            <Quote size={24} />
            <blockquote>{game.question}</blockquote>
            <div className="game-options">
              {game.options.map((o: any) => (
                <button
                  disabled={Boolean(answer)}
                  key={o.id}
                  onClick={async () =>
                    setAnswer(
                      await mutate(
                        `/workspaces/${wid}/games/${game.id}/answer`,
                        { answer: o.id },
                      ),
                    )
                  }
                >
                  {o.name}
                </button>
              ))}
            </div>
            {answer && (
              <div className="game-answer">
                <strong>
                  {answer.correct ? "You know this chat. ✨" : "A plot twist!"}
                </strong>
                <p>
                  {kind === "who"
                    ? people.find((p) => p.id === answer.answer)?.name
                    : answer.answer}
                </p>
                <button
                  className="text-button"
                  onClick={() =>
                    open({
                      title: "The original exchange",
                      mid: answer.message_id,
                    })
                  }
                >
                  Reveal the conversation
                  <ArrowRight size={14} />
                </button>
              </div>
            )}
          </div>
        )}
      </Panel>
      {award && (
        <Modal
          title="An award only your group would give"
          close={() => setAward(null)}
        >
          <form
            className="form"
            onSubmit={async (e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              await mutate(
                `/workspaces/${wid}/awards${award.id ? `/${award.id}` : ""}`,
                Object.fromEntries(f),
                award.id ? "PUT" : "POST",
              );
              setAward(null);
              client.invalidateQueries();
            }}
          >
            <label>
              Title
              <input
                name="title"
                required
                defaultValue={award.title ?? ""}
                placeholder="Most likely to say ‘on my way’"
              />
            </label>
            <label>
              Winner
              <select name="person" defaultValue={award.person}>
                {people.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              The reason
              <input name="metric" defaultValue={award.metric ?? ""} required />
            </label>
            <button className="primary">Save award</button>
            {award.id && (
              <button
                type="button"
                className="text-button"
                onClick={async () => {
                  await mutate(
                    `/workspaces/${wid}/awards/${award.id}`,
                    {},
                    "DELETE",
                  );
                  setAward(null);
                  client.invalidateQueries();
                }}
              >
                Delete award
              </button>
            )}
          </form>
        </Modal>
      )}
    </>
  );
}

function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
}) {
  const box = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const elements = () =>
      Array.from(
        box.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]),input,select,a[href],textarea,[tabindex="0"]',
        ) ?? [],
      ).filter((el) => el.getClientRects().length > 0);
    requestAnimationFrame(() => elements()[0]?.focus());
    const f = (e: KeyboardEvent) => {
      if (e.key === "Tab") {
        const list = elements();
        const index = list.indexOf(document.activeElement as HTMLElement);
        if (e.shiftKey && index <= 0) {
          e.preventDefault();
          list.at(-1)?.focus();
        } else if (!e.shiftKey && (index === list.length - 1 || index === -1)) {
          e.preventDefault();
          list[0]?.focus();
        }
      }
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", f);
    return () => {
      document.removeEventListener("keydown", f);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <section
        className="modal"
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={close}
          >
            <X size={20} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
function CloudButton({
  kind,
  question = "",
  onResult,
  label,
}: {
  kind: string;
  question?: string;
  onResult?: (r: any) => void;
  label?: string;
}) {
  const { wid, filters, toast, go, jobs } = useApp();
  const [preview, setPreview] = useState<any>();
  const [jid, setJid] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const job = jobs.find((j) => j.id === jid);
    if (job?.status === "complete") {
      onResult?.(job.result);
      client.invalidateQueries();
      setJid("");
      toast("Your source-linked story is ready");
    }
  }, [jobs, jid]);
  const start = async () => {
    setBusy(true);
    try {
      setPreview(
        await mutate(`/workspaces/${wid}/cloud/preview`, {
          kind,
          question,
          filters,
        }),
      );
    } catch (e: any) {
      toast(e.message);
    }
    setBusy(false);
  };
  return (
    <>
      <button disabled={busy || Boolean(jid)} onClick={start}>
        <Sparkles size={15} />
        {jid ? "Writing…" : busy ? "Preparing…" : (label ?? "Add an AI story")}
      </button>
      {preview && (
        <Modal
          title="Review this cloud analysis"
          close={() => setPreview(undefined)}
        >
          <div className="form">
            <p>{preview.note}</p>
            <div className="preview-stats">
              <span>{preview.messages} excerpts</span>
              <span>~{num(preview.estimated_input_tokens)} input tokens</span>
              <span>Up to {num(preview.max_output_tokens)} output tokens</span>
            </div>
            <p className="footnote">
              Model: {preview.model || "Not configured"}. Token estimates are
              approximate; charges depend on your provider account.
            </p>
            {(!preview.cloud_enabled || !preview.has_key || !preview.model) &&
            kind !== "qa" ? (
              <button
                className="primary"
                onClick={() => {
                  setPreview(undefined);
                  go("settings");
                }}
              >
                Configure cloud in Settings
              </button>
            ) : (
              <button
                className="primary"
                onClick={async () => {
                  try {
                    const r = await mutate(
                      `/workspaces/${wid}/cloud/generate`,
                      { kind, question, filters, approved: true },
                    );
                    if (r.result) onResult?.(r.result);
                    else setJid(r.job_id);
                    setPreview(undefined);
                  } catch (e: any) {
                    toast(e.message);
                  }
                }}
              >
                Generate with this scope
                <ArrowRight size={15} />
              </button>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
function Narrative({ body }: { body: any }) {
  return (
    <article className="narrative">
      <span className="badge">
        {body.method ? "CALCULATED" : "AI INTERPRETATION · CHECK THE SOURCES"}
      </span>
      <h3>{body.title}</h3>
      <p>{body.summary}</p>
      {body.claims.map((c: any, i: number) => (
        <div className="claim" key={i}>
          <p>{c.text}</p>
          <Sources ids={c.sources} label="See evidence" />
        </div>
      ))}
    </article>
  );
}
function Narratives({ kind }: { kind: string }) {
  const q = useData("artifacts", { kind });
  return (
    <>
      {q.data?.map((a: any) => (
        <Narrative key={a.id} body={a.body} />
      ))}
    </>
  );
}
function QuestionBox() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<any>();
  return (
    <Panel>
      <div className="question-row">
        <input
          aria-label="Question for the archive"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Who sends the most messages? What happened on the road trip?"
        />
        <CloudButton
          kind="qa"
          question={question}
          onResult={setResult}
          label="Ask the archive"
        />
      </div>
      <p className="footnote">
        Supported count questions use exact analytics. Narrative answers require
        optional cloud configuration.
      </p>
      {result && <Narrative body={result} />}
    </Panel>
  );
}

function Settings() {
  const q = useData("settings");
  const { wid, toast, jobs } = useApp();
  const [busy, setBusy] = useState("");
  async function queue(kind: string, extra = {}) {
    try {
      await mutate(`/workspaces/${wid}/jobs`, { kind, ...extra });
      toast("Analysis queued");
      client.invalidateQueries();
    } catch (e: any) {
      toast(e.message);
    }
  }
  return (
    <State query={q}>
      {(d) => (
        <>
          <div className="grid-even">
            <Panel
              title="Make yourself at home"
              subtitle="Time and conversation settings"
            >
              <form
                className="form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  try {
                    await mutate(
                      `/workspaces/${wid}/settings`,
                      {
                        timezone: f.get("timezone"),
                        session_gap: Number(f.get("session_gap")),
                      },
                      "PUT",
                    );
                    client.invalidateQueries();
                    toast("Settings saved");
                  } catch (e: any) {
                    toast(e.message);
                  }
                }}
              >
                <label>
                  Timezone
                  <input name="timezone" defaultValue={d.timezone} />
                </label>
                <label>
                  New conversation after (minutes)
                  <input
                    name="session_gap"
                    type="number"
                    min={1}
                    max={1440}
                    defaultValue={d.session_gap}
                  />
                </label>
                <button className="primary">Save preferences</button>
              </form>
            </Panel>
            <Panel
              title="Saved contact names"
              subtitle="Match members to Contacts on this Mac"
            >
              <p className="explain">
                Use saved names across conversations, charts, and games. Manual
                renames stay in place. Members without a unique match keep their
                current name; identities are never merged automatically.
              </p>
              <p className="footnote">
                macOS may ask for Contacts access. If access is denied, enable
                it in System Settings → Privacy &amp; Security → Contacts for
                the app or terminal running Group Chat Explorer.
              </p>
              {d.contacts.status === "available" && (
                <p role="status">
                  {num(d.contacts.matched)} members matched ·{" "}
                  {num(d.contacts.ambiguous)} ambiguous matches
                </p>
              )}
              {d.contacts.error && <p role="status">{d.contacts.error}</p>}
              {d.contacts.status === "denied" && (
                <p role="status">
                  Contacts access was denied. Enable access, then retry.
                </p>
              )}
              <button
                className="primary"
                disabled={busy === "contacts"}
                onClick={async () => {
                  setBusy("contacts");
                  try {
                    const result = await mutate(
                      `/workspaces/${wid}/contacts/sync`,
                      {},
                    );
                    await client.invalidateQueries();
                    toast(
                      result.status === "available"
                        ? `Updated ${result.updated} member names from Contacts`
                        : (result.error ??
                            "Allow Contacts access in macOS settings, then retry"),
                    );
                  } catch (e: any) {
                    toast(e.message);
                  } finally {
                    setBusy("");
                  }
                }}
              >
                {busy === "contacts"
                  ? "Reading Contacts…"
                  : "Use saved contact names"}
              </button>
            </Panel>
            <Panel
              title="Optional cloud writing"
              subtitle="Your archive stays local. Only reviewed excerpts are sent."
            >
              <form
                className="form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  setBusy("cloud");
                  try {
                    await mutate(
                      `/workspaces/${wid}/settings`,
                      {
                        cloud_model: f.get("model"),
                        cloud_enabled: f.get("enabled") === "on",
                        ...(f.get("key") ? { api_key: f.get("key") } : {}),
                      },
                      "PUT",
                    );
                    (e.target as HTMLFormElement).reset();
                    client.invalidateQueries();
                    toast("Cloud settings saved");
                  } catch (e: any) {
                    toast(e.message);
                  }
                  setBusy("");
                }}
              >
                <label>
                  OpenAI model ID
                  <input
                    name="model"
                    defaultValue={d.cloud_model}
                    placeholder="A model supporting structured outputs"
                  />
                </label>
                <label>
                  API key
                  <input
                    name="key"
                    type="password"
                    autoComplete="off"
                    placeholder={
                      d.has_key
                        ? "Saved in macOS Keychain · leave blank to keep"
                        : "Stored in macOS Keychain"
                    }
                  />
                </label>
                <label className="checkbox">
                  <input
                    name="enabled"
                    type="checkbox"
                    defaultChecked={d.cloud_enabled}
                  />
                  Enable cloud analysis for this workspace
                </label>
                <button className="primary" disabled={busy === "cloud"}>
                  Save cloud settings
                </button>
              </form>
            </Panel>
          </div>
          <Panel
            title="Give your archive its superpowers"
            subtitle="Local models download on first use. Analysis runs in the background."
          >
            <div className="analysis-grid">
              <div>
                <Sparkles />
                <h3>Meaning & topics</h3>
                <p>
                  Local embeddings, semantic search, topic clusters, and
                  suggested eras.
                </p>
                <span className="badge">
                  {d.semantic_ready
                    ? `${num(d.semantic_passages)} passages indexed`
                    : "INDEX NOT BUILT"}
                </span>
                <button className="primary" onClick={() => queue("semantic")}>
                  Build semantic index
                </button>
              </div>
              <div>
                <Image />
                <h3>Pictures & screenshots</h3>
                <p>
                  macOS Vision OCR, image fingerprints, and CLIP similarity
                  search.
                </p>
                <button
                  onClick={() =>
                    queue("media", { ocr: true, images: true, audio: false })
                  }
                >
                  Analyze images
                </button>
              </div>
              <div>
                <MessageCircle />
                <h3>Voice notes</h3>
                <p>
                  Searchable local transcripts from Whisper base.en. Existing
                  text is preserved.
                </p>
                <button
                  onClick={() =>
                    queue("media", { ocr: false, images: false, audio: true })
                  }
                >
                  Transcribe audio
                </button>
              </div>
            </div>
            <p className="footnote">
              {Object.values(d.dependencies).every(Boolean)
                ? "All analysis dependencies are installed."
                : "Install analysis dependencies in the terminal: .venv/bin/pip install -e '.[analysis]'"}{" "}
              · FFmpeg {d.ffmpeg ? "available" : "not installed"}
            </p>
          </Panel>
          <Panel
            title="The archive you have"
            subtitle="Coverage reflects what is present on this Mac"
          >
            <div className="coverage-grid">
              <div>
                <small>AVAILABLE HISTORY</small>
                <strong>
                  {date(d.coverage.start)} — {date(d.coverage.end)}
                </strong>
              </div>
              <div>
                <small>MESSAGES DECODED</small>
                <strong>{num(d.coverage.messages)}</strong>
              </div>
              <div>
                <small>LAST IMPORT</small>
                <strong>
                  {d.coverage.imported_at
                    ? new Date(d.coverage.imported_at).toLocaleString()
                    : "Not imported"}
                </strong>
              </div>
            </div>
            <p className="footnote">
              {num(d.coverage.missing_attachments)} missing attachments ·{" "}
              {num(d.coverage.unsupported_records)} unsupported record variants
              retained.
            </p>
            {d.source && (
              <button onClick={() => queue("refresh")}>
                <RefreshCw size={15} />
                Refresh from Messages
              </button>
            )}
            {d.coverage.diagnostics?.length > 0 && (
              <details>
                <summary>
                  {d.coverage.parse_failures ?? d.coverage.diagnostics.length}{" "}
                  parsing diagnostics (up to 100 shown)
                </summary>
                <pre>{JSON.stringify(d.coverage.diagnostics, null, 2)}</pre>
              </details>
            )}
            <p className="footnote">
              Absent history and undownloaded attachments cannot be
              reconstructed. Reaction history may contain only its latest state.
            </p>
          </Panel>
          <Panel title="Analysis activity">
            <div className="jobs-list">
              {jobs.map((j) => (
                <div className="job" key={j.id}>
                  <div>
                    <span className={`badge ${j.status}`}>{j.status}</span>
                    <strong>{j.kind}</strong>
                    <p>{j.message}</p>
                    {["running", "queued"].includes(j.status) && (
                      <progress value={j.progress} max={1} />
                    )}
                  </div>
                  {["running", "queued"].includes(j.status) ? (
                    <button
                      onClick={async () => {
                        await mutate(`/jobs/${j.id}/cancel`, {});
                        client.invalidateQueries();
                      }}
                    >
                      Cancel
                    </button>
                  ) : (
                    ["failed", "cancelled"].includes(j.status) && (
                      <button
                        onClick={async () => {
                          try {
                            await mutate(`/jobs/${j.id}/retry`, {});
                            client.invalidateQueries();
                          } catch (e: any) {
                            toast(e.message);
                          }
                        }}
                      >
                        Retry
                      </button>
                    )
                  )}
                </div>
              ))}
            </div>
            {!jobs.length && <p className="footnote">No analysis jobs yet.</p>}
          </Panel>
          {d.usage.length > 0 && (
            <Panel title="Cloud usage">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Model</th>
                      <th>Input tokens</th>
                      <th>Output tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.usage.map((u: any) => (
                      <tr key={u.id}>
                        <td>{u.kind}</td>
                        <td>{u.model}</td>
                        <td>{num(u.input_tokens)}</td>
                        <td>{num(u.output_tokens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </>
      )}
    </State>
  );
}

function ImportModal({
  close,
  onImported,
}: {
  close: () => void;
  onImported: (id: string) => void;
}) {
  const { toast } = useApp();
  const [path, setPath] = useState("~/Library/Messages/chat.db");
  const [root, setRoot] = useState("");
  const [discovery, setDiscovery] = useState<any>();
  const [selected, setSelected] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal title="Bring your group chat home" close={close}>
      <div className="form">
        <p>
          Import a group from your Mac’s Messages archive or a database
          snapshot.
        </p>
        <label>
          Messages database path
          <input value={path} onChange={(e) => setPath(e.target.value)} />
        </label>
        <label>
          Attachment folder (optional)
          <input
            value={root}
            onChange={(e) => setRoot(e.target.value)}
            placeholder="~/Library/Messages/Attachments"
          />
        </label>
        {!discovery ? (
          <button
            disabled={busy}
            className="primary"
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                setDiscovery(await mutate("/imports/discover", { path }));
              } catch (e: any) {
                setError(e.message);
              }
              setBusy(false);
            }}
          >
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Search size={16} />
            )}
            Discover group chats
          </button>
        ) : (
          <>
            <label>
              Workspace name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="The name you know it by"
              />
            </label>
            <p>
              Did Messages split your group into a new thread? Select both
              entries below to combine their history into one workspace.
            </p>
            <div className="chat-selection">
              {discovery.chats.map((c: any) => (
                <label key={c.id}>
                  <input
                    type="checkbox"
                    checked={selected.includes(c.id)}
                    onChange={(e) => {
                      setSelected((s) =>
                        e.target.checked
                          ? [...s, c.id]
                          : s.filter((id) => id !== c.id),
                      );
                      if (!name) setName(c.name || "My group chat");
                    }}
                  />
                  <div>
                    <strong>{c.name || c.members.join(", ")}</strong>
                    <small>
                      {num(c.messages)} source records · {c.members.length}{" "}
                      participants
                    </small>
                    <small>
                      {c.start != null && c.end != null
                        ? `${date(c.start, { month: "short", day: "numeric", year: "numeric" })} — ${date(c.end, { month: "short", day: "numeric", year: "numeric" })}`
                        : "No dated history"}{" "}
                      · Thread {c.id}
                    </small>
                  </div>
                </label>
              ))}
            </div>
            <p className="footnote" role="status">
              {selected.length > 1
                ? `${selected.length} threads selected. Their messages, reactions, and media will share one timeline and analytics dashboard. Refresh will update every selected thread.`
                : "Select one thread, or select multiple related threads to combine a split group. Shared messages are counted once."}
            </p>
            <button
              className="primary"
              disabled={busy || !selected.length || !name.trim()}
              onClick={async () => {
                setBusy(true);
                try {
                  const r = await mutate("/imports/select", {
                    import_id: discovery.import_id,
                    name,
                    chat_ids: selected,
                    attachment_root: root || null,
                  });
                  onImported(r.workspace_id);
                  close();
                  toast("Import started; watch its progress in Settings");
                } catch (e: any) {
                  setError(e.message);
                }
                setBusy(false);
              }}
            >
              {selected.length > 1
                ? `Combine ${selected.length} threads & import`
                : "Import selected history"}
              <ArrowRight size={15} />
            </button>
          </>
        )}
        {error && (
          <p className="error-note" role="alert">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}

function App() {
  const wq = useQuery<Workspace[]>({
    queryKey: ["workspaces"],
    queryFn: () => request("/workspaces"),
  });
  const [wid, setWid] = useState(localStorage.getItem("workspace") ?? "");
  const [view, setView] = useState("overview");
  const [filters, setFilters] = useState<Filters>({});
  const [drawer, setDrawer] = useState<DrawerSpec | null>(null);
  const [importing, setImporting] = useState(false);
  const [notification, setNotification] = useState("");
  const [mobile, setMobile] = useState(false);
  const [theme, setTheme] = useState(localStorage.getItem("theme") ?? "light");
  const [jobList, setJobs] = useState<any[]>([]);
  const selected = wq.data?.find((w) => w.id === wid);
  const toast = (s: string) => {
    setNotification(s);
    setTimeout(() => setNotification(""), 6000);
  };
  const qc = useQueryClient();
  useEffect(() => {
    if (wq.data?.length && !wq.data.some((w) => w.id === wid))
      setWid(wq.data[0].id);
  }, [wq.data]);
  useEffect(() => {
    localStorage.setItem("workspace", wid);
    setFilters({});
    setDrawer(null);
    if (!wid) return;
    const event = new EventSource(`${API}/jobs/events?wid=${wid}`);
    event.onmessage = (e) => {
      const list = JSON.parse(e.data);
      setJobs(list);
      qc.invalidateQueries({ queryKey: ["workspaces"] });
      qc.invalidateQueries({ queryKey: [wid] });
    };
    return () => event.close();
  }, [wid]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setView("topics");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  const tl = useQuery({
    queryKey: [wid, "era-selector"],
    queryFn: () => request(`/workspaces/${wid}/timeline`),
    enabled: Boolean(wid),
  });
  const timezoneQuery = useQuery({
    queryKey: [wid, "settings"],
    queryFn: () => request(`/workspaces/${wid}/settings`),
    enabled: Boolean(wid),
  });
  useEffect(() => {
    if (timezoneQuery.data?.timezone) setTimeZone(timezoneQuery.data.timezone);
  }, [timezoneQuery.data?.timezone]);
  const people = selected?.people ?? [];
  const content: Record<string, React.ReactNode> = {
    overview: <Overview />,
    timeline: <Timeline />,
    people: <People />,
    reactions: <Reactions />,
    words: <Words />,
    conversations: <Conversations />,
    topics: <Topics />,
    lore: <Lore />,
    media: <Media />,
    recaps: <Recaps />,
    settings: <Settings />,
  };
  const current = NAV.find((n) => n[0] === view);
  const activeJobs = jobList.filter((j) =>
    ["queued", "running"].includes(j.status),
  );
  const desc: Record<string, string> = {
    overview: "The big picture of your little corner of the internet.",
    timeline: "The chapters, turning points, and everything in between.",
    people: "The characters who make the chat what it is.",
    reactions: "Some messages just hit different.",
    words: "The words you share. The habits you can’t hide.",
    conversations: "Follow the threads that brought everyone together.",
    topics: "Find a thought, a plan, or a half-remembered moment.",
    lore: "An unofficial encyclopedia of your shared universe.",
    media: "Photos, voice notes, memes, and links worth keeping.",
    recaps: "Remember the highlights. Test your memory.",
    settings: "Your archive, your preferences.",
  };
  return (
    <AppContext.Provider
      value={{
        wid,
        workspace: selected,
        filters,
        setFilters,
        people,
        open: setDrawer,
        go: setView,
        toast,
        jobs: jobList,
      }}
    >
      <div className="app-shell">
        <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
          <a
            className="brand"
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setView("overview");
            }}
          >
            <span className="brand-mark">
              <MessageCircle size={21} />
              <i />
            </span>
            <span>
              groupchat<span>explorer</span>
            </span>
          </a>
          <div className="workspace-switch">
            <span className="workspace-symbol">
              <Users size={20} />
            </span>
            <div>
              <small>YOUR GROUP CHAT</small>
              <select
                aria-label="Select workspace"
                value={wid}
                onChange={(e) => setWid(e.target.value)}
              >
                {wq.data?.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
                {!wq.data?.length && (
                  <option value="">Choose your history</option>
                )}
              </select>
            </div>
          </div>
          <small className="nav-label">EXPLORE THE ARCHIVE</small>
          <nav>
            {NAV.map(([id, label, Icon]) => (
              <button
                key={id}
                className={view === id ? "active" : ""}
                onClick={() => {
                  setView(id);
                  setMobile(false);
                }}
              >
                <Icon size={18} />
                <span>{label}</span>
                {view === id && <i />}
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="local-note">
              <span className="status-dot" />
              <strong>At home, on your Mac.</strong>
              <p>Your history stays yours.</p>
            </div>
            <button
              className={view === "settings" ? "active" : ""}
              onClick={() => setView("settings")}
            >
              <Settings2 size={17} />
              Settings & analysis
              {activeJobs.length > 0 && <span className="job-dot" />}
            </button>
            <button onClick={() => setImporting(true)}>
              <Plus size={17} />
              Import a group chat
            </button>
            <div className="sidebar-footer">
              <small>OPEN SOURCE · GPL-3.0</small>
              <button
                className="icon-button"
                aria-label="Toggle theme"
                onClick={() =>
                  setTheme((t) => (t === "light" ? "dark" : "light"))
                }
              >
                {theme === "light" ? <Moon size={15} /> : <Sun size={15} />}
              </button>
            </div>
          </div>
        </aside>
        <main>
          <div className="topbar">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile((m) => !m)}
            >
              <Menu />
            </button>
            <div className="breadcrumb">
              <span>Your archive</span>
              <ChevronRight size={12} />
              <strong>{current?.[1] ?? "Settings"}</strong>
            </div>
            <button className="global-search" onClick={() => setView("topics")}>
              <Search size={15} />
              <span>Find something in the chat</span>
              <kbd>⌘ K</kbd>
            </button>
            <span className="local-badge">
              <span className="status-dot" />
              LOCAL
            </span>
          </div>
          <div className="page">
            <header className="page-title">
              <div>
                <div className="eyebrow">
                  {selected?.demo
                    ? "A FICTIONAL DEMO ARCHIVE"
                    : (selected?.name ?? "YOUR HISTORY, REVISITED")}
                </div>
                <h1>
                  {current?.[1] ?? "Settings & analysis"}
                  <span className="title-dot">.</span>
                </h1>
                <p>{desc[view]}</p>
              </div>
              <div className="header-actions">
                {selected?.demo && (
                  <span className="badge demo-badge">DEMO DATA</span>
                )}
                <button onClick={() => setImporting(true)}>
                  <Plus size={15} />
                  Import chat
                </button>
              </div>
            </header>
            {wid && (
              <>
                <div className="filters">
                  <span>
                    <SlidersHorizontal size={15} />
                    Your view
                  </span>
                  <select
                    aria-label="Filter by member"
                    value={filters.person ?? ""}
                    onChange={(e) =>
                      setFilters((f) => ({
                        ...f,
                        person: e.target.value || undefined,
                      }))
                    }
                  >
                    <option value="">All members</option>
                    {people.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label="Filter by era"
                    value={filters.era ?? ""}
                    onChange={(e) =>
                      setFilters((f) => ({
                        ...f,
                        era: e.target.value || undefined,
                      }))
                    }
                  >
                    <option value="">All eras</option>
                    {tl.data?.eras.map((e: Era) => (
                      <option key={e.id} value={e.id}>
                        {e.name}
                      </option>
                    ))}
                  </select>
                  <label className="date-filter">
                    <CalendarDays size={14} />
                    <input
                      aria-label="Start date"
                      type="date"
                      value={filters.start ? isoDay(filters.start) : ""}
                      onChange={(e) =>
                        setFilters((f) => ({
                          ...f,
                          start: e.target.value
                            ? dayStart(e.target.value)
                            : undefined,
                        }))
                      }
                    />
                    <span>—</span>
                    <input
                      aria-label="End date"
                      type="date"
                      value={filters.end ? isoDay(filters.end) : ""}
                      onChange={(e) =>
                        setFilters((f) => ({
                          ...f,
                          end: e.target.value
                            ? dayEnd(e.target.value)
                            : undefined,
                        }))
                      }
                    />
                  </label>
                  {Object.values(filters).some((v) => v !== undefined) && (
                    <button
                      className="text-button"
                      onClick={() => setFilters({})}
                    >
                      Reset
                      <X size={12} />
                    </button>
                  )}
                  <a
                    className="export-button"
                    href={`${API}/workspaces/${wid}/export.csv?${params(filters)}`}
                  >
                    <ArrowDownToLine size={14} />
                    Export
                  </a>
                </div>
                {activeJobs.length > 0 && (
                  <button
                    className="job-banner"
                    onClick={() => setView("settings")}
                  >
                    <LoaderCircle size={15} className="spin" />
                    <span>
                      {activeJobs[0].message || "Analysis queued"}
                      {activeJobs.length > 1
                        ? ` · ${activeJobs.length} jobs`
                        : ""}
                    </span>
                    <progress value={activeJobs[0].progress} max={1} />
                    <ChevronRight size={15} />
                  </button>
                )}
              </>
            )}
            {wq.error ? (
              <Empty title="The local server is unavailable">
                <p>Start the app with npm start, then refresh this page.</p>
              </Empty>
            ) : wq.isPending ? (
              <div className="loading">
                <LoaderCircle className="spin" />
                Opening your archive…
              </div>
            ) : wid && selected ? (
              content[view]
            ) : (
              <div className="welcome">
                <div className="welcome-icon">
                  <MessageCircle />
                  <Sparkles />
                </div>
                <h2>
                  Your group chat has
                  <br />a whole history to tell.
                </h2>
                <p>
                  Explore the eras, inside jokes, and everyday moments that made
                  it yours. Everything begins with an archive.
                </p>
                <div>
                  <button
                    className="primary"
                    onClick={() => setImporting(true)}
                  >
                    <Plus size={16} />
                    Import your group chat
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        const d = await mutate("/demo", {});
                        setWid(d.id);
                        qc.invalidateQueries();
                        toast("Welcome to a fictional group chat");
                      } catch (e: any) {
                        toast(e.message);
                      }
                    }}
                  >
                    Explore a demo
                    <ArrowRight size={15} />
                  </button>
                </div>
                <small>
                  LOCAL FIRST · OPEN SOURCE · MADE FOR YOUR MEMORIES
                </small>
              </div>
            )}
            <footer className="page-footer">
              <span>
                <MessageCircle size={13} />
                Little messages. A whole history.
              </span>
              <small>GROUP CHAT EXPLORER</small>
            </footer>
          </div>
        </main>
      </div>
      {drawer && (
        <Drawer
          key={JSON.stringify(drawer)}
          spec={drawer}
          close={() => setDrawer(null)}
        />
      )}
      {importing && (
        <ImportModal
          close={() => setImporting(false)}
          onImported={(id) => {
            setWid(id);
            setView("settings");
            qc.invalidateQueries();
          }}
        />
      )}
      {notification && (
        <div className="toast" role="status">
          <Check size={16} />
          {notification}
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setNotification("")}
          >
            <X size={14} />
          </button>
        </div>
      )}
    </AppContext.Provider>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
