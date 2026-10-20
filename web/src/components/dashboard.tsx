"use client";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Player } from "@/components/player";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardLabel } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { currentTask, lampState, loadState, nextEvent, nowMin, type HicState } from "@/lib/state";

const Lamp = dynamic(() => import("@/components/lamp").then((m) => m.Lamp), { ssr: false, loading: () => <div className="aspect-[3/4] w-full max-w-[300px]" /> });

const CL: Record<string, string> = { WORK: "W", DIST: "D", UNKNOWN: "U", IDLE: "I" };
const TAPE: Record<string, string> = { W: "bg-[var(--ink)]", D: "bg-[var(--dist)]", U: "bg-[var(--unk)]", I: "bg-[var(--idle)]", "": "bg-[color-mix(in_srgb,var(--ink)_18%,transparent)]" };

function Tape({ s, dark }: { s: HicState; dark?: boolean }) {
  const slots = useMemo(() => {
    const a = new Array<string>(144).fill("");
    for (const { m, k } of s.timeline) { const i = Math.floor(m / 10), c = CL[k]; if (c && (!a[i] || c === "D")) a[i] = c; }
    return a;
  }, [s.timeline]);
  const cur = Math.floor(nowMin() / 10);
  return (
    <div>
      <div className="grid h-[72px] grid-cols-[repeat(144,1fr)] gap-px" aria-label="linha do tempo do dia">
        {slots.map((c, i) => (
          <i key={i} className={cn("block rounded-[1px]", dark && !c ? "bg-[var(--frame)]" : dark && c === "W" ? "bg-[var(--work)]" : TAPE[c], i === cur && "outline-2 outline-offset-1 outline-[var(--work)]")} />
        ))}
      </div>
      <div className={cn("mt-1 flex justify-between font-mono text-[10px]", dark ? "text-[var(--mute)]" : "text-[var(--ink-mute)]")}>
        {["00", "06", "12", "18", "24"].map((h) => <span key={h}>{h}</span>)}
      </div>
    </div>
  );
}

const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } };
const rise = { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 170, damping: 22 } } };

function Triage({ s, live, onDone }: { s: HicState; live: boolean; onDone: (h: string) => void }) {
  const act = async (a: "allow" | "block", host: string, kind: string) => {
    if (live) await fetch(`/api/domain/${a}`, { method: "POST", headers: { "Content-Type": "application/json", "X-HIC": "1" }, body: JSON.stringify({ host, kind }) });
    onDone(host);
  };
  const q = s.triage;
  return (
    <aside className="grid h-full min-w-0 grid-rows-[auto_1fr] gap-3.5 overflow-hidden rounded-[var(--r)] bg-[var(--dark)] p-4 max-[900px]:min-h-[290px] " id="triagem">
      <div className="flex items-start justify-between gap-2.5">
        <div><CardLabel className="mb-1.5 text-[var(--mute)]">domínios para triar</CardLabel><b className="break-all text-sm font-semibold">{q[0]?.host ?? "fila vazia"}</b></div>
        <span className="grid size-7 flex-none place-items-center rounded-full bg-[var(--card)] font-mono text-xs font-bold text-[var(--ink)]">{q.length}</span>
      </div>
      <div className="relative min-h-[200px]">
        {q.length === 0 && <p className="absolute inset-0 grid place-items-center text-center text-[13px] text-[var(--mute)]">Nada para triar.</p>}
        <AnimatePresence initial={false}>
          {q.slice(0, 3).map((d, i) => (
            <motion.div
              key={d.host} layout
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: -i * 10, rotate: -i * 7, x: -i * 6 }} exit={{ opacity: 0, x: 120, rotate: 8 }}
              style={{ zIndex: 3 - i, transformOrigin: "bottom right" }}
              className={cn("absolute inset-x-0 bottom-0 grid gap-2.5 rounded-2xl p-3.5 text-[var(--ink)] shadow-[0_-6px_20px_-10px_rgba(0,0,0,.8)]", i === 0 ? "bg-[var(--card)]" : i === 1 ? "bg-[var(--card-2)]" : "bg-[#a9a39b]")}
            >
              <div className="truncate font-mono text-[13px] font-medium">{d.host}</div>
              <div className="text-xs text-[var(--ink-mute)]">{d.min} min sem classificar</div>
              {i === 0 && (
                <div className="grid grid-cols-2 gap-1.5">
                  <Button className="col-span-2" onClick={() => act("allow", d.host, d.kind)}>trabalho</Button>
                  <Button variant="outline" disabled title="em breve: neutral_domains">neutro</Button>
                  <Button variant="outline" onClick={() => act("block", d.host, d.kind)}>bloquear</Button>
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </aside>
  );
}

export function Dashboard() {
  const [data, setData] = useState<{ s: HicState; live: boolean } | null>(null);
  const [layout, setLayout] = useState<"panel" | "lamp">("panel");
  const [theme, setTheme] = useState("ember");
  useEffect(() => { const run = () => loadState().then(setData); run(); const id = setInterval(run, 15_000); return () => clearInterval(id); }, []);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

  if (!data) return <Player />;
  const { s, live } = data;
  const L = lampState(s), ev = nextEvent(s), task = currentTask(s);
  const dropTriage = (h: string) => setData((d) => d && ({ ...d, s: { ...d.s, triage: d.s.triage.filter((x) => x.host !== h) } }));
  const top = s.today.top_apps.slice(0, 4).map(([n, m]) => `${n} ${m}`).join(" · ");

  return (
    <>
      <Player />
      <main className="mx-auto max-w-[1100px] pt-4">
        {layout === "panel" ? (
          <motion.div variants={stagger} initial="hidden" animate="show" className="grid grid-cols-[56px_1fr_250px] grid-rows-[auto_auto_1fr] gap-3 rounded-[28px] border border-[var(--frame-line)] bg-[var(--frame)] p-3.5 shadow-[0_40px_90px_-40px_rgba(0,0,0,.9),inset_0_1px_0_rgba(255,255,255,.05)] max-[900px]:grid-cols-[56px_1fr] max-[620px]:grid-cols-1">
            <motion.div variants={rise} className="col-span-2 flex items-center max-[620px]:col-span-1"><span className="rounded-full bg-[var(--card)] px-4 py-1.5 text-[13px] font-extrabold tracking-[.14em] text-[var(--ink)]">HIC OS</span></motion.div>
            <motion.div variants={rise} className="flex min-w-0 items-center gap-2.5 rounded-full bg-[var(--card)] py-1.5 pr-2 pl-4 text-[var(--ink)] max-[900px]:col-span-full"><span className="min-w-0 flex-1 truncate font-mono text-[11px]">{s.window} · {s.current.app}</span><span className="relative size-[22px] flex-none rounded-full bg-[var(--ink)]"><i className="absolute inset-[7px] rounded-full" style={{ background: L.color }} /></span></motion.div>
            <motion.aside variants={rise} className="row-span-2 flex flex-col items-center justify-between rounded-full bg-[var(--card)] py-3.5 max-[620px]:row-span-1 max-[620px]:h-[52px] max-[620px]:flex-row max-[620px]:px-3.5">
              <nav className="flex flex-col gap-3.5 max-[620px]:flex-row">{["ES", "PL", "SE", "TR"].map((x, i) => <a key={x} href="#" aria-current={i === 0 ? "page" : undefined} className={cn("grid size-7 place-items-center rounded-lg font-mono text-[10px]", i === 0 ? "bg-[var(--ink)] text-[var(--card)]" : "text-[var(--ink-mute)]")}>{x}</a>)}</nav>
              <div className="grid size-8 place-items-center rounded-full bg-[var(--ink)] text-[11px] font-bold text-[var(--card)]">H</div>
            </motion.aside>
            <motion.section variants={rise} className="col-start-2 grid grid-cols-3 items-start gap-3 max-[620px]:col-start-1 max-[620px]:grid-cols-1">
              <div className="grid gap-1.5"><Card className="flex min-h-[118px] flex-col justify-between"><CardLabel>ativo hoje</CardLabel><div className="text-[clamp(34px,4vw,46px)] leading-[.95] font-extrabold tabular-nums">{s.today.work_min}<small className="ml-1 text-[.3em] font-medium text-[var(--ink-mute)]">min</small></div></Card><Badge className="justify-self-end">banda {s.band_min}–{s.band_max}</Badge></div>
              <div className="grid gap-1.5"><Card className="flex min-h-[118px] flex-col justify-between gap-2"><CardLabel>tarefa atual</CardLabel>{task ? <div><div className="text-base leading-tight font-semibold">{task.title}</div><div className="mt-1 font-mono text-[10px] text-[var(--ink-mute)]">{task.actual_min}/{task.estimate_min} min</div></div> : <div className="text-base text-[var(--ink-mute)]">Sem plano hoje.</div>}</Card><Badge hot className="justify-self-end">{task ? "em andamento" : "hic plan"}</Badge></div>
              <div className="grid gap-1.5"><Card className="flex min-h-[118px] flex-col justify-between"><CardLabel>próximo</CardLabel><div className="text-base leading-tight font-semibold">{ev.title}</div></Card><Badge className="justify-self-end">{ev.chip}</Badge></div>
            </motion.section>
            <motion.section variants={rise} className="col-start-2 grid min-w-0 grid-cols-[1fr_28px] gap-2.5 max-[620px]:col-start-1">
              <Card className="grid min-w-0 grid-rows-[auto_1fr_auto] gap-3"><CardLabel>hoje, minuto a minuto</CardLabel><Tape s={s} /><div className="max-w-[460px] rounded-xl bg-[var(--card-2)] p-3 text-[13px]"><b>{top || "sem dados"}</b> <span className="text-[var(--ink-mute)]">· onde o tempo foi</span></div></Card>
              <div className="rounded-full transition-all duration-700" style={{ background: `linear-gradient(180deg,#3a332e,${L.color})`, boxShadow: `0 0 28px -4px ${L.color}` }} title={L.name} />
            </motion.section>
            <motion.div variants={rise} className="col-start-3 row-span-2 row-start-2 max-[900px]:col-start-2 max-[900px]:row-span-1 max-[900px]:row-start-auto max-[620px]:col-start-1"><Triage s={s} live={live} onDone={dropTriage} /></motion.div>
          </motion.div>
        ) : (
          <motion.div variants={stagger} initial="hidden" animate="show" className="grid grid-cols-[minmax(240px,360px)_1fr] gap-7 pt-2 max-[760px]:grid-cols-1">
            <motion.section variants={rise} className="flex flex-col items-center gap-5">
              <Lamp color={L.color} level={L.level} label={`estado: ${L.name}`} />
              <div className="font-mono text-xs tracking-widest text-[var(--mute)] uppercase">{L.word || "—"} · {L.name}</div>
              <div className="flex gap-1.5">{[0, 1, 2].map((i) => <i key={i} className={cn("h-1 w-[26px] rounded-sm", i < L.level ? "bg-[var(--dist)]" : "bg-[var(--frame-line)]")} />)}</div>
            </motion.section>
            <motion.section variants={rise} className="flex min-w-0 flex-col gap-5">
              <div className="grid grid-cols-3 border-y border-[var(--frame-line)] max-[980px]:grid-cols-1">
                {[["ativo hoje", <>{s.today.work_min}<small className="ml-1.5 text-[.32em] text-[var(--mute)]">min</small></>, `banda ${s.band_min}–${s.band_max}`], ["tarefa atual", task?.title ?? "Sem plano hoje.", task ? `${task.actual_min} de ${task.estimate_min} min` : "hic plan"], ["próximo", ev.title, ev.chip]].map(([l, v, sub], i) => (
                  <div key={i} className={cn("min-w-0 py-4 pr-4", i > 0 && "border-l border-[var(--frame-line)] pl-4 max-[980px]:border-t max-[980px]:border-l-0 max-[980px]:pl-0")}>
                    <CardLabel className="mb-2.5 text-[var(--mute)]">{l as string}</CardLabel>
                    <div className={i === 0 ? "text-[clamp(40px,5vw,60px)] leading-[.95] font-extrabold tabular-nums" : "text-xl leading-tight font-semibold"}>{v as React.ReactNode}</div>
                    <div className="mt-2.5 text-[13px] text-[var(--mute)]">{sub as string}</div>
                  </div>
                ))}
              </div>
              <Tape s={s} dark />
            </motion.section>
          </motion.div>
        )}
      </main>
      <footer className="mx-auto mt-3.5 flex max-w-[1100px] flex-wrap justify-between gap-2 pb-5 font-mono text-[11px] text-[var(--mute)]">
        <span>{live ? "ao vivo · daemon local" : "demo · dados fictícios"}</span>
        <span className="flex gap-3">
          <label>layout <select className="rounded border border-[var(--frame-line)] bg-[var(--frame)] px-1.5 py-0.5" value={layout} onChange={(e) => setLayout(e.target.value as "panel" | "lamp")}><option value="panel">painel</option><option value="lamp">lâmpada</option></select></label>
          <label>tema <select className="rounded border border-[var(--frame-line)] bg-[var(--frame)] px-1.5 py-0.5" value={theme} onChange={(e) => setTheme(e.target.value)}><option value="ember">ember</option><option value="mono">mono</option></select></label>
        </span>
      </footer>
    </>
  );
}
