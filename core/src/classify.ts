import type { ClassifierConfig } from "./config";

/** WORK, DIST, OFF, AWAY, LOCKED, NEUTRAL, BLIND, UNKNOWN, OFFHOURS vêm do hic.py. IDLE é nova. */
export type Klass = "WORK" | "DIST" | "OFF" | "AWAY" | "LOCKED" | "NEUTRAL" | "BLIND" | "UNKNOWN" | "OFFHOURS" | "PRIVATE" | "IDLE";

export interface Classification { klass: Klass; app: string; host: string }
export interface Probe { app: string | null | undefined; host?: string | null; idleSec: number; locked?: boolean; outsideWindow?: boolean }

export const LOCK_APPS = new Set(["loginwindow", "ScreenSaverEngine", "LockScreen", "SecurityAgent"]);

// Caracteres invisíveis que o macOS às vezes anexa ao nome do app (marcas de direção, zero-width, BOM).
const INVISIBLE = /[​-‏‪-‮﻿]/g;
export const normApp = (name: string | null | undefined): string => (name ?? "").replace(INVISIBLE, "").trim();

/** Casa por sufixo de domínio: "google.com" NÃO casa "notgoogle.com". */
export function hostMatches(host: string | null | undefined, patterns: readonly string[]): boolean {
  const h = (host ?? "").toLowerCase().replace(/^\.+/, "");
  for (const raw of patterns) {
    const p = String(raw).toLowerCase().trim().replace(/^\.+/, "");
    if (!p) continue;
    if (h === p || h.endsWith("." + p)) return true;
  }
  return false;
}

export function appMatches(app: string | null | undefined, list: readonly string[] | undefined): boolean {
  const target = normApp(app).toLowerCase();
  if (!target) return false;
  return (list ?? []).some((x) => normApp(x).toLowerCase() === target);
}

export function hostIsPrivate(host: string | null | undefined, cfg: ClassifierConfig): boolean {
  const h = (host ?? "").toLowerCase().replace(/^\.+/, "");
  if (!h) return false;
  if (hostMatches(h, cfg.private_domains)) return true;
  for (const pat of cfg.private_patterns) {
    try { if (new RegExp(pat).test(h)) return true; } catch { /* padrão inválido é ignorado, como no hic.py */ }
  }
  return false;
}

/** App que ninguém classificou não é "fora do trabalho", é "não sei". */
export function appClass(app: string, cfg: ClassifierConfig): Klass {
  if (appMatches(app, cfg.work_apps)) return "WORK";
  if (appMatches(app, cfg.blocked_apps)) return "DIST";
  if (appMatches(app, cfg.neutral_apps)) return "NEUTRAL";
  if (cfg.unknown_app_policy === "block") return "OFF";
  if (cfg.unknown_app_policy === "allow") return "WORK";
  return "UNKNOWN";
}

function base(p: Probe, cfg: ClassifierConfig): Classification {
  const app = normApp(p.app);
  const host = (p.host ?? "").trim();

  // Guarda sem julgar; se a janela mudar, o reclassify converte retroativamente.
  if (p.outsideWindow) return { klass: "OFFHOURS", app, host };
  // Tela travada é sinal inequívoco de ausência. Cobrar uma tela de bloqueio é o falso positivo mais caro.
  if (LOCK_APPS.has(app) || p.locked) return { klass: "LOCKED", app, host: "" };
  if (p.idleSec >= cfg.away_after_min * 60) return { klass: "AWAY", app, host: "" };
  // Sem permissão de Acessibilidade o app vem vazio. Isso significa "não sei", não "fora do trabalho".
  if (!app) return { klass: "BLIND", app: "", host: "" };

  if (app === normApp(cfg.browser_app)) {
    if (!host) return { klass: "WORK", app, host: "" }; // sem URL: não penaliza
    if (hostIsPrivate(host, cfg)) return { klass: "PRIVATE", app, host: "" }; // nunca chega ao log
    if (hostMatches(host, cfg.blocked_domains)) return { klass: "DIST", app, host };
    if (hostMatches(host, cfg.work_domains)) return { klass: "WORK", app, host };
    if (cfg.unknown_domain_policy === "block") return { klass: "DIST", app, host };
    if (cfg.unknown_domain_policy === "allow") return { klass: "WORK", app, host };
    return { klass: "UNKNOWN", app, host };
  }
  return { klass: appClass(app, cfg), app, host: "" };
}

/**
 * Função pura: decide a classe a partir da sonda. Ao vivo e no reclassify usam esta mesma função,
 * para os dois nunca divergirem.
 *
 * Diferença deliberada em relação ao hic.py: entre `idle_work_max_min` e `away_after_min` o minuto vira IDLE
 * em vez de WORK/DIST/UNKNOWN. Sem isso, tela aberta e parada contava como trabalho (22% dos minutos WORK de outubro).
 * IDLE não credita trabalho, não conta distração, não entra na triagem e não guarda o host.
 */
export function classify(p: Probe, cfg: ClassifierConfig): Classification {
  const r = base(p, cfg);
  const counts = r.klass === "WORK" || r.klass === "DIST" || r.klass === "UNKNOWN";
  if (counts && p.idleSec >= cfg.idle_work_max_min * 60) return { klass: "IDLE", app: r.app, host: "" };
  return r;
}
