from collections import defaultdict

from .store import Store

VERDICTS = ("fiction", "fact")
COMMENT_LABELS = ("fiction", "fact", "none")


def comment_label(probs: dict) -> str:
    return max(COMMENT_LABELS, key=lambda label: probs.get(label, 0.0))


def summarize(store: Store, primary_model: str, min_mentions: float = 3.0) -> dict:
    judged = {r["url"] for r in store.read("judged")}

    models = defaultdict(dict)
    for r in store.read("body_verdicts"):
        models[r["url"]][r["model"]] = r["probs"]

    narratives = {}
    for r in store.read("narrative_verdicts"):
        narratives[r["url"]] = r["probs"]["experience"] if r["probs"] else None

    votes = defaultdict(lambda: dict.fromkeys(COMMENT_LABELS, 0))
    comment_counts = defaultdict(int)
    comments = defaultdict(list)
    for r in store.read("comment_verdicts"):
        label = comment_label(r["probs"])
        comment_counts[r["url"]] += 1
        votes[r["url"]][label] += 1
        comments[r["url"]].append({"user": r["user"], "label": label, "score": r["probs"].get(label, 0.0)})

    entries = []
    for seen in store.read("seen"):
        url = seen["url"]
        if url not in judged:
            continue
        sums = votes[url]
        mentions = sums["fiction"] + sums["fact"]
        crowd = {v: sums[v] / mentions for v in VERDICTS} if mentions >= min_mentions else None
        primary = models[url].get(primary_model)
        gap = (
            sum(abs(primary[v] - crowd[v]) for v in VERDICTS) / 2 if crowd is not None and primary is not None else None
        )
        entries.append(
            {
                **seen,
                "models": models[url],
                "crowd": crowd,
                "mentions": mentions,
                "comment_count": comment_counts[url],
                "gap": gap,
                "narrative": narratives.get(url),
                "comments": comments[url],
                "suspicion": sums["fiction"] / comment_counts[url] if comment_counts[url] else None,
            }
        )

    entries.sort(key=lambda e: e["bookmarked_at"], reverse=True)
    return {"primary_model": primary_model, "entries": entries}
