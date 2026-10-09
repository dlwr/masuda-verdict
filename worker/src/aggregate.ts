export type Verdict = { fiction: number; fact: number };

const VERDICTS = ["fiction", "fact"] as const;

export function summarize(model: Verdict | null, comments: Record<string, number>[], minMentions = 3) {
  const sums = { fiction: 0, fact: 0 };
  for (const c of comments) for (const v of VERDICTS) sums[v] += c[v] ?? 0;
  const mentions = sums.fiction + sums.fact;
  const crowd: Verdict | null =
    mentions >= minMentions ? { fiction: sums.fiction / mentions, fact: sums.fact / mentions } : null;
  const gap =
    crowd && model ? VERDICTS.reduce((acc, v) => acc + Math.abs(model[v] - crowd[v]), 0) / 2 : null;
  return { crowd, mentions, gap };
}
