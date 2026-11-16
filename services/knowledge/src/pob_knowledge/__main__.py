from __future__ import annotations

import argparse
import json
from pathlib import Path

from pob_knowledge.paths import knowledge_db_path
from pob_knowledge.store import KnowledgeStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Path of Building game data.")
    parser.add_argument("command", choices=("import", "show"))
    parser.add_argument("--db", default=None)
    parser.add_argument("--name", default=None, help="Item base, unique, or gem name for show.")
    args = parser.parse_args()
    store = KnowledgeStore(knowledge_db_path() if args.db is None else Path(args.db))
    try:
        if args.command == "import":
            print(json.dumps(store.import_checkout(), indent=2))
            return
        if not args.name:
            parser.error("show requires --name")
        try:
            payload = store.item_base(args.name)
        except KeyError:
            uniques = store.unique_items(args.name)
            payload = uniques or store.gem(args.name)
        print(json.dumps(payload, indent=2)[:4000])
    finally:
        store.close()


if __name__ == "__main__":
    main()
