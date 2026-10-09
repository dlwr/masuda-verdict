import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)

    def append(self, kind: str, record: dict, at: datetime) -> None:
        path = self.root / kind / f"{at:%Y-%m}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read(self, kind: str) -> Iterator[dict]:
        for path in sorted((self.root / kind).glob("*.jsonl")):
            with path.open() as f:
                for line in f:
                    yield json.loads(line)
