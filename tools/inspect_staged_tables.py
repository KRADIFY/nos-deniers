"""Print a compact structural inventory of one staged table JSONL.GZ file."""

from __future__ import annotations

import argparse
import collections
import gzip
import json
from pathlib import Path


def summarize(value):
    if isinstance(value, list):
        return f"list[{len(value)}]"
    if isinstance(value, dict):
        return f"dict[{len(value)}]:{','.join(list(value)[:12])}"
    text = str(value).replace("\n", " ")
    return text[:160] + ("…" if len(text) > 160 else "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--examples", type=int, default=8)
    args = parser.parse_args()

    records = []
    key_counts: collections.Counter[str] = collections.Counter()
    with gzip.open(args.path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            records.append(row)
            key_counts.update(row.keys())

    print(json.dumps({
        "path": str(args.path),
        "records": len(records),
        "keys": dict(key_counts),
    }, ensure_ascii=False, indent=2))

    shown = 0
    for index, row in enumerate(records, 1):
        tables = row.get("tables")
        if not tables:
            continue
        print(f"RECORD {index} page={row.get('page')} kind={row.get('kind')} tables={len(tables)}")
        for table_index, table in enumerate(tables[:3], 1):
            print(f"  TABLE {table_index} keys={list(table)}")
            for key, value in table.items():
                print(f"    {key}={summarize(value)}")
        shown += 1
        if shown >= args.examples:
            break


if __name__ == "__main__":
    main()
