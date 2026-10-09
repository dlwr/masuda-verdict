import { describe, expect, it } from "vitest";
import { summarize } from "../src/aggregate";

const c = (p: Partial<Record<"fiction" | "fact" | "none", number>>) => ({ fiction: 0, fact: 0, none: 0, ...p });

describe("summarize", () => {
  it("ignores none mass in the crowd", () => {
    expect(summarize(null, [c({ fiction: 1 }), c({ none: 1 })], 1).crowd).toEqual({ fiction: 1, fact: 0 });
  });

  it("averages mentions", () => {
    const crowd = summarize(null, [c({ fiction: 1 }), c({ fact: 0.5, none: 0.5 })], 1).crowd!;
    expect(crowd.fiction).toBeCloseTo(2 / 3);
  });

  it("counts non-none mass as mentions", () => {
    expect(summarize(null, [c({ fiction: 1 }), c({ fact: 0.5, none: 0.5 })], 1).mentions).toBeCloseTo(1.5);
  });

  it("has no crowd below the minimum mentions", () => {
    expect(summarize(null, [c({ none: 1 })], 1).crowd).toBeNull();
  });

  it("measures the gap as total variation distance", () => {
    expect(summarize({ fiction: 0, fact: 1 }, [c({ fiction: 1 })], 1).gap).toBeCloseTo(1);
  });

  it("has no gap without a model verdict", () => {
    expect(summarize(null, [c({ fiction: 1 })], 1).gap).toBeNull();
  });
});
