import { describe, expect, it } from "vitest";
import { decide } from "../src/clef";

const question = {
  name: "verdict",
  instructions: "真偽は",
  choices: { fiction: "創作", fact: "事実" },
};

const fakeAi = (output: unknown) => {
  const calls: unknown[][] = [];
  return {
    calls,
    run: async (...args: unknown[]) => {
      calls.push(args);
      return output;
    },
  };
};

const answer = (probabilities: Record<string, number>) => ({
  model: "clef",
  answers: { verdict: { type: "choice", choice: "fact", probabilities, confidence: 0.5 } },
});

describe("decide", () => {
  it("runs the clef model", async () => {
    const ai = fakeAi(answer({ fiction: 0.2, fact: 0.8 }));
    await decide(ai, "本文", question);
    expect(ai.calls[0][0]).toBe("@cf/cloudflare/clef");
  });

  it("sends the question as criteria", async () => {
    const ai = fakeAi(answer({ fiction: 0.2, fact: 0.8 }));
    await decide(ai, "本文", question);
    expect(ai.calls[0][1]).toEqual({
      model: "clef",
      state: "本文",
      questions: { verdict: { type: "choice", instructions: "真偽は", criteria: { fiction: "創作", fact: "事実" } } },
    });
  });

  it("returns probabilities for every choice", async () => {
    const ai = fakeAi(answer({ fact: 1 }));
    expect(await decide(ai, "本文", question)).toEqual({ fiction: 0, fact: 1 });
  });

  it("reports an unexpected output shape with its payload", async () => {
    const ai = fakeAi({ response: "fact" });
    await expect(decide(ai, "本文", question)).rejects.toThrow('{"response":"fact"}');
  });
});
