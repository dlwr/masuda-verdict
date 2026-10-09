import type { Question } from "./questions";

export type Ai = { run(model: string, input: unknown): Promise<unknown> };

type Output = { answers?: Record<string, { probabilities?: Record<string, number> }> };

export async function decide(ai: Ai, text: string, question: Question): Promise<Record<string, number>> {
  const output = (await ai.run("@cf/cloudflare/clef", {
    model: "clef",
    state: text,
    questions: {
      [question.name]: { type: "choice", instructions: question.instructions, criteria: question.choices },
    },
  })) as Output;
  const probabilities = output?.answers?.[question.name]?.probabilities;
  if (!probabilities || typeof probabilities !== "object") {
    throw new Error(`unexpected clef output: ${JSON.stringify(output)}`);
  }
  return Object.fromEntries(Object.keys(question.choices).map((k) => [k, probabilities[k] ?? 0]));
}
