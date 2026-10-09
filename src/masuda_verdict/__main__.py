import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import hatena
from .aggregate import summarize
from .deciders import Budgeted, ClefDecider, JevDecider, OpenAIDecider
from .pipeline import collect, judge_due
from .store import Store

log = logging.getLogger("masuda_verdict")

DATA_DIR = Path("data")
SUMMARY_PATH = Path("site/src/data/summary.json")
MAX_CLEF_CALLS_PER_RUN = 700


def build_deciders():
    clef = ClefDecider(account_id=os.environ["CLOUDFLARE_ACCOUNT_ID"], token=os.environ["CLOUDFLARE_API_TOKEN"])
    optional = []
    if key := os.environ.get("TYPESAFE_API_KEY"):
        optional.append(JevDecider(api_key=key))
    if key := os.environ.get("OPENAI_API_KEY"):
        optional.append(OpenAIDecider(api_key=key))
    return Budgeted(clef, limit=MAX_CLEF_CALLS_PER_RUN), optional


def cmd_collect(store):
    collect(store, hatena.fetch_hot_entries(), datetime.now(UTC))


def cmd_judge(store):
    primary, optional = build_deciders()
    judge_due(
        store,
        fetch_body=hatena.fetch_body,
        fetch_comments=hatena.fetch_comments,
        primary=primary,
        optional_body_deciders=optional,
        now=datetime.now(UTC),
    )


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
