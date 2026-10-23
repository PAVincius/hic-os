import { z } from "zod";

/** Contrato de GET /api/state. O daemon (hoje hic.py, depois TS) é a fonte; a UI só consome. */
export const StateSchema = z.object({
  demo: z.boolean().optional(),
  mode: z.string(),
  window: z.string(),
  work_start: z.string(),
  work_end: z.string(),
  band_min: z.number(),
  band_max: z.number(),
  current: z.object({
    class: z.string(),
    app: z.string(),
    host: z.string().optional(),
    idle: z.number(),
    nag_level: z.number(),
  }),
  today: z.object({
    work_min: z.number(),
    dist_min: z.number(),
    nags: z.number(),
    top_apps: z.array(z.tuple([z.string(), z.number()])),
  }),
  timeline: z.array(z.object({ m: z.number(), k: z.string() })),
  plan: z.object({
    tasks: z.array(
      z.object({
        id: z.number(),
        title: z.string(),
        bucket: z.string(),
        estimate_min: z.number(),
        actual_min: z.number(),
        status: z.string(),
      }),
    ),
  }),
  triage: z.array(z.object({ kind: z.string(), host: z.string(), min: z.number() })),
  streak: z.number(),
});
export type HicState = z.infer<typeof StateSchema>;
export type Task = HicState["plan"]["tasks"][number];

export const nowMin = (d = new Date()) => d.getHours() * 60 + d.getMinutes();
export const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const toMin = (s: string) => { const [h, m] = s.split(":").map(Number); return h * 60 + (m || 0); };

export function lampState(s: HicState, m = nowMin()) {
  const n = s.current.nag_level;
  if (m >= 22 * 60) return { word: "FECHA", name: "empurrão para fora", color: "#3d6bff", level: 0 };
  if (s.current.class === "AWAY") return { word: "", name: "ausente", color: "#1f1c19", level: 0 };
  if (s.current.class === "IDLE") return { word: "IDLE", name: "tela parada, não conta", color: "#7a7268", level: 0 };
  if (s.current.class === "DIST" || n > 0) return { word: n >= 3 ? "FOCUS" : "VOLTA", name: `distração, nível ${n}`, color: "#ff4d2e", level: n };
  return { word: "WORK", name: "trabalho", color: "#ffb257", level: 0 };
}

export function nextEvent(s: HicState, m = nowMin()) {
  const start = toMin(s.work_start), end = toMin(s.work_end);
  if (m < start) return { title: `Cobrança começa às ${hhmm(start)}`, chip: `em ${start - m} min` };
  if (m < end) return { title: `Cobrança termina às ${hhmm(end)}`, chip: `em ${end - m} min` };
  if (m < 22 * 60) return { title: "Empurrão para fora às 22:00", chip: `em ${22 * 60 - m} min` };
  return { title: "Hora de fechar", chip: "agora" };
}

export const currentTask = (s: HicState): Task | null =>
  s.plan.tasks.find((t) => t.status === "doing") ?? s.plan.tasks.find((t) => t.status === "todo" || t.status === "paused") ?? null;

/** Dados fictícios, mesmo formato do daemon. Nada aqui vem de um usuário real. */
export function demoState(): HicState {
  const timeline: { m: number; k: string }[] = [];
  const span = (a: number, b: number, k: string) => { for (let m = a; m < b; m++) timeline.push({ m, k }); };
  span(8 * 60 + 5, 11 * 60 + 40, "WORK"); span(9 * 60 + 20, 9 * 60 + 23, "DIST");
  span(11 * 60 + 40, 12 * 60 + 5, "IDLE"); span(12 * 60 + 5, 13 * 60 + 30, "WORK");
  const now = nowMin();
  const t = timeline.filter((x) => x.m <= now);
  return {
    demo: true, mode: "weekday", window: "expediente", work_start: "07:30", work_end: "20:00",
    band_min: 300, band_max: 480,
    current: { class: "WORK", app: "Cursor", host: "", idle: 0, nag_level: 0 },
    today: { work_min: t.filter((x) => x.k === "WORK").length, dist_min: 3, nags: 1,
      top_apps: [["Cursor", 96], ["Terminal", 41], ["Slack", 22], ["Chrome", 18]] },
    timeline: t,
    plan: { tasks: [
      { id: 1, title: "Revisar PR da API", bucket: "frog", estimate_min: 90, actual_min: 54, status: "doing" },
      { id: 2, title: "Responder o time", bucket: "urgent", estimate_min: 20, actual_min: 0, status: "todo" },
    ] },
    triage: [
      { kind: "host", host: "docs.example.dev", min: 8 },
      { kind: "host", host: "news.example.org", min: 3 },
      { kind: "app", host: "Notes", min: 2 },
    ],
    streak: 4,
  };
}

/** Ao vivo quando servido junto do daemon; senão demo (é o caso da Vercel). */
export async function loadState(): Promise<{ s: HicState; live: boolean }> {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (r.ok && (r.headers.get("content-type") ?? "").includes("json")) {
      const p = StateSchema.safeParse(await r.json());
      if (p.success) return { s: p.data, live: true };
    }
  } catch { /* sem daemon */ }
  return { s: demoState(), live: false };
}
