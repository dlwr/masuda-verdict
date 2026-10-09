import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import hatena
from .aggregate import summarize
from .deciders import ClefDecider, JevDecider, OpenAIDecider
from .pipeline import collect, due_entries, judge_entry
from .store import Store

log = logging.getLogger("masuda_verdict")

DATA_DIR = Path("data")
SUMMARY_PATH = Path("site/src/data/summary.json")


def build_deciders():
    clef = ClefDecider(account_id=os.environ["CLOUDFLARE_ACCOUNT_ID"], token=os.environ["CLOUDFLARE_API_TOKEN"])
    body = [clef]
    if key := os.environ.get("TYPESAFE_API_KEY"):
        body.append(JevDecider(api_key=key))
    if key := os.environ.get("OPENAI_API_KEY"):
        body.append(OpenAIDecider(api_key=key))
    return clef, body


def cmd_collect(store):
    collect(store, hatena.fetch_hot_entries(), datetime.now(UTC))


def cmd_judge(store):
    clef, body_deciders = build_deciders()
    for entry in due_entries(store, datetime.now(UTC)):
        try:
            judge_entry(
                store,
                entry,
                fetch_body=hatena.fetch_body,
                fetch_comments=hatena.fetch_comments,
                body_deciders=body_deciders,
                comment_decider=clef,
                now=datetime.now(UTC),
            )
        except Exception:
            log.exception("stopped at %s; the rest carries over to the next run", entry["url"])
            return


def cmd_aggregate(store):
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize(store, primary_model="clef")
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")


def main(argv=None):
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="masuda_verdict")
    parser.add_argument("command", choices=["collect", "judge", "aggregate"])
    args = parser.parse_args(argv)
    store = Store(DATA_DIR)
    {"collect": cmd_collect, "judge": cmd_judge, "aggregate": cmd_aggregate}[args.command](store)


if __name__ == "__main__":
    sys.exit(main())
