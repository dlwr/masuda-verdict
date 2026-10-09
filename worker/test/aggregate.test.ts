import { describe, expect, it } from "vitest";
import { commentLabel, summarize } from "../src/aggregate";

const c = (p: Partial<Record<"fiction" | "fact" | "none", number>>) => ({ fiction: 0, fact: 0, none: 0, ...p });

describe("commentLabel", () => {
  it("picks the most probable label", () => {
    expect(commentLabel(c({ fiction: 0.4, fact: 0.3, none: 0.3 }))).toBe("fiction");
  });
});

describe("summarize", () => {
  it("counts votes by top label", () => {
    expect(summarize(null, [c({ fiction: 1 }), c({ fact: 0.6, none: 0.4 }), c({ none: 1 })], 1).crowd).toEqual({
      fiction: 0.5,
      fact: 0.5,
    });
  });

  it("ignores minority probability", () => {
    expect(summarize(null, [c({ fact: 0.7, fiction: 0.3 }), c({ fact: 0.6, fiction: 0.4 })], 1).crowd).toEqual({
      fiction: 0,
      fact: 1,
    });
  });

  it("counts fiction and fact votes as mentions", () => {
    expect(summarize(null, [c({ fiction: 1 }), c({ fact: 0.6, none: 0.4 }), c({ none: 0.6, fact: 0.4 })], 1).mentions).toBe(2);
  });

  it("measures suspicion as the fiction vote share over all comments", () => {
    expect(summarize(null, [c({ fiction: 0.4, fact: 0.3, none: 0.3 }), c({ none: 1 })], 1).suspicion).toBe(0.5);
  });

  it("has no suspicion without comments", () => {
    expect(summarize(null, [], 1).suspicion).toBeNull();
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
