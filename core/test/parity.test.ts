import { describe, expect, it } from "vitest";
import { classify, type ClassifierConfig } from "../src";
import fx from "./fixtures/parity.json";

// idle_work_max_min enorme desliga o IDLE: aqui só importa a paridade com o hic.py.
describe("paridade com o classify_from do hic.py", () => {
  it(`${fx.cases.length} sondas dão exatamente o mesmo resultado`, () => {
    const diffs: string[] = [];
    for (const c of fx.cases as any[]) {
      const cfg = { ...fx.cfg, ...c.cfg, idle_work_max_min: 1_000_000 } as ClassifierConfig;
      const r = classify(c.in, cfg);
      const got = { klass: r.klass, app: r.app, host: r.host };
      if (JSON.stringify(got) !== JSON.stringify(c.out)) diffs.push(`${JSON.stringify(c.in)} cfg=${JSON.stringify(c.cfg)}\n  py=${JSON.stringify(c.out)}\n  ts=${JSON.stringify(got)}`);
    }
    expect(diffs.slice(0, 5).join("\n")).toBe("");
    expect(diffs.length).toBe(0);
  });
});
