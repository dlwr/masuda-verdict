export type Verdict = { fiction: number; fact: number };
export type CommentLabel = "fiction" | "fact" | "none";

const VERDICTS = ["fiction", "fact"] as const;
const COMMENT_LABELS: CommentLabel[] = ["fiction", "fact", "none"];

export function commentLabel(probs: Record<string, number>): CommentLabel {
  return COMMENT_LABELS.reduce((best, label) => ((probs[label] ?? 0) > (probs[best] ?? 0) ? label : best));
}

export function summarize(model: Verdict | null, comments: Record<string, number>[], minMentions = 3) {
  const votes = { fiction: 0, fact: 0, none: 0 };
  for (const c of comments) votes[commentLabel(c)]++;
  const mentions = votes.fiction + votes.fact;
  const crowd: Verdict | null =
    mentions >= minMentions ? { fiction: votes.fiction / mentions, fact: votes.fact / mentions } : null;
  const gap =
    crowd && model ? VERDICTS.reduce((acc, v) => acc + Math.abs(model[v] - crowd[v]), 0) / 2 : null;
  const suspicion = comments.length ? votes.fiction / comments.length : null;
  return { crowd, mentions, gap, suspicion };
}
