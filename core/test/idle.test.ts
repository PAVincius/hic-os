import { describe, expect, it } from "vitest";
import { classify, DEFAULT_CONFIG as D, type ClassifierConfig } from "../src";

const cfg: ClassifierConfig = { ...D, browser_app: "Google Chrome", idle_work_max_min: 10, away_after_min: 45 };
const min = (m: number) => m * 60;

describe("IDLE: tela aberta e parada não é trabalho", () => {
  it("app de trabalho com 9 min parado ainda é WORK; com 10 vira IDLE", () => {
    expect(classify({ app: "Cursor", idleSec: min(9) + 59 }, cfg).klass).toBe("WORK");
    expect(classify({ app: "Cursor", idleSec: min(10) }, cfg).klass).toBe("IDLE");
  });
  it("com 45 min vira AWAY, não IDLE", () => {
    expect(classify({ app: "Cursor", idleSec: min(44) + 59 }, cfg).klass).toBe("IDLE");
    expect(classify({ app: "Cursor", idleSec: min(45) }, cfg).klass).toBe("AWAY");
  });
  it("domínio bloqueado parado não cobra: é IDLE, não DIST", () => {
    expect(classify({ app: "Google Chrome", host: "youtube.com", idleSec: min(15) }, cfg).klass).toBe("IDLE");
  });
  it("IDLE não guarda o host nem entra na triagem", () => {
    const r = classify({ app: "Google Chrome", host: "algo-novo.io", idleSec: min(20) }, cfg);
    expect(r).toEqual({ klass: "IDLE", app: "Google Chrome", host: "" });
  });
  it("privacidade vem antes: host privado parado continua PRIVATE e some do log", () => {
    const c = { ...cfg, private_domains: ["secret.example"] };
    expect(classify({ app: "Google Chrome", host: "secret.example", idleSec: min(20) }, c)).toEqual({ klass: "PRIVATE", app: "Google Chrome", host: "" });
  });
  it("tela travada continua LOCKED mesmo com pouco idle", () => {
    expect(classify({ app: "loginwindow", idleSec: 5 }, cfg).klass).toBe("LOCKED");
    expect(classify({ app: "Cursor", idleSec: 5, locked: true }, cfg).klass).toBe("LOCKED");
  });
  it("app neutro parado segue NEUTRAL (não conta de qualquer jeito)", () => {
    expect(classify({ app: "Spotify", idleSec: min(20) }, cfg).klass).toBe("NEUTRAL");
  });
  it("fora da janela guarda OFFHOURS sem julgar", () => {
    expect(classify({ app: "Cursor", idleSec: min(20), outsideWindow: true }, cfg).klass).toBe("OFFHOURS");
  });
  it("sem app (sonda cega) é BLIND", () => {
    expect(classify({ app: "", idleSec: 0 }, cfg).klass).toBe("BLIND");
  });
});
