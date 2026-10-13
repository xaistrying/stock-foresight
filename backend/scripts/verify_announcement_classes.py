"""
Accuracy check for the announcement keyword classes (`add-announcement-tags-and-insider-sizing`, tasks 2.3 and 2.4).

Read-only: the stored feed log is opened with sqlite3 `mode=ro` and nothing is written, fetched or sent anywhere. No
network, no vendor call, no language model.

    python backend/scripts/verify_announcement_classes.py [--titles] [--labels PATH] [--db PATH]

By default it prints COUNTS ONLY: how many stored news titles each keyword class claims, how many company filings
match no class, how many of those contain a share or capital word, and a cross-tab of event code by title pattern
for every stored event row (to confirm ISS, AIS, DIV, AGME, EGME, DDIND, DDINS and DDRP against their titles).
The feed log is marked not to be shared, so no title is printed unless you ask.

`--titles` also prints, for you to read in your own terminal, a numbered list of company-filing titles with the class
each would get, and the unclassified titles that contain a share or capital word. Do not paste that output into a
chat, an issue or a file in the repository.

`--labels PATH` reads your own labels from a file kept OUTSIDE the repository: one line per title, `<number><TAB><class>`,
where the number is the one `--titles` prints and the class is one of capital, dividend, meeting, results, personnel or
none. It prints, per class, titles claimed, correct, wrong, unlabelled (claimed but not in your file) and missed (labelled
with the class but not claimed). A class may be enabled in `announcement_keywords.ENABLED_KEYWORD_CLASSES` only if it claimed
at least 3 titles, none wrongly and none unlabelled.
"""

import argparse
import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.brief.announcement_keywords import KEYWORDS, fold, matching_classes  # noqa: E402
from app.services.brief.insider import TRADE_TITLE  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "company_feed_log.db"
MIN_CLAIMED = 3  # a class is enabled only if it claims at least this many titles, none wrongly
SHARE_OR_CAPITAL_WORDS = ("cổ phiếu", "vốn", "phát hành", "chào bán", "cổ phần", "quyền mua", "niêm yết")
EVENT_PATTERNS = (
    ("insider shape", lambda t: TRADE_TITLE.match(t) is not None),
    ("share keyword", lambda t: any(w in fold(t) for w in ("cổ phiếu", "quyền mua", "riêng lẻ", "cbcnv"))),
    ("cash dividend keyword", lambda t: "cổ tức" in fold(t)),
    ("additional listing keyword", lambda t: "niêm yết bổ sung" in fold(t)),
    ("meeting keyword", lambda t: any(w in fold(t) for w in ("đại hội", "đhđcđ"))),
)
_LATEST = (
    "SELECT i.ticker, i.title, i.fields, i.published_at, i.item_id FROM company_feed_item i WHERE i.kind = ? AND i.id = "
    "(SELECT MAX(v.id) FROM company_feed_item v WHERE v.ticker = i.ticker AND v.source = i.source AND v.kind = i.kind "
    "AND v.item_id = i.item_id) ORDER BY i.published_at, i.item_id"
)


def read_rows(db: Path, kind: str) -> list[tuple]:
    """The latest stored version of every item of `kind`, read-only (a missing log or table reads as no rows)."""
    if not db.exists():
        return []
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return conn.execute(_LATEST, (kind,)).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def classify_news(rows: list[tuple]) -> list[dict]:
    """Company filings (the title starts with `<TICKER>:`) with the classes the keyword lists give them."""
    filings = []
    for ticker, title, _fields, _published, _item in rows:
        title = title or ""
        if not title.strip().startswith(f"{ticker}:"):
            continue
        matches = matching_classes(title, frozenset(KEYWORDS))
        claimed = "capital" if "capital" in matches else (matches[0] if len(matches) == 1 else "none")
        filings.append({"ticker": ticker, "title": title, "claimed": claimed})
    return filings


def has_share_word(title: str) -> bool:
    return any(word in fold(title) for word in SHARE_OR_CAPITAL_WORDS)


def event_cross_tab(rows: list[tuple]) -> dict[str, collections.Counter]:
    table: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for _ticker, title, fields, _published, _item in rows:
        code = (json.loads(fields) if fields else {}).get("event_code") or "(none)"
        patterns = [name for name, test in EVENT_PATTERNS if test(title or "")] or ["no pattern"]
        for name in patterns:
            table[code][name] += 1
    return table


def read_labels(path: Path) -> dict[int, str]:
    labels = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"(\d+)\t(\w+)", line.strip())
        if match:
            labels[int(match[1])] = match[2]
    return labels


def label_counts(filings: list[dict], labels: dict[int, str]) -> dict[str, dict[str, int]]:
    counts = {name: {"claimed": 0, "correct": 0, "wrong": 0, "missed": 0, "unlabelled": 0} for name in KEYWORDS}
    for number, filing in enumerate(filings, start=1):
        label, claimed = labels.get(number), filing["claimed"]
        if claimed != "none":
            counts[claimed]["claimed"] += 1
            if label is None:
                counts[claimed]["unlabelled"] += 1  # a claim nobody checked cannot count as correct
            else:
                counts[claimed]["correct" if label == claimed else "wrong"] += 1
        if label in counts and claimed != label:
            counts[label]["missed"] += 1
    return counts


def report(db: Path, *, titles: bool, labels: Path | None) -> list[str]:
    filings = classify_news(read_rows(db, "news"))
    out = [f"company filings read: {len(filings)}"]
    per_class = collections.Counter(f["claimed"] for f in filings)
    out += [f"  claimed by {name}: {per_class[name]}" for name in KEYWORDS] + [f"  claimed by no class: {per_class['none']}"]
    unclassified = [f for f in filings if f["claimed"] == "none"]
    out.append(f"unclassified filings containing a share or capital word: {sum(has_share_word(f['title']) for f in unclassified)}")
    out.append("event rows, code by title pattern (a row can match more than one pattern):")
    for code, row in sorted(event_cross_tab(read_rows(db, "events")).items()):
        out.append(f"  {code}: " + ", ".join(f"{name} {n}" for name, n in sorted(row.items())))
    if labels is not None:
        for name, c in label_counts(filings, read_labels(labels)).items():
            ready = c["claimed"] >= MIN_CLAIMED and c["wrong"] == 0 and c["unlabelled"] == 0
            out.append(
                f"label check {name}: claimed {c['claimed']}, correct {c['correct']}, wrong {c['wrong']}, "
                f"unlabelled {c['unlabelled']}, missed {c['missed']}; {'may be enabled' if ready else 'stays disabled'}"
            )
    if titles:
        out.append("--- titles (for you only; do not share) ---")
        out += [f"{n}\t{f['ticker']}\t{f['claimed']}\t{f['title']}" for n, f in enumerate(filings, start=1)]
        out.append("--- unclassified with a share or capital word ---")
        out += [f"{f['ticker']}\t{f['title']}" for f in unclassified if has_share_word(f["title"])]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="the feed log (opened read-only)")
    parser.add_argument("--titles", action="store_true", help="also print titles, for your own terminal only")
    parser.add_argument("--labels", type=Path, help="your labels file, kept outside the repository")
    args = parser.parse_args(argv)
    if args.labels is not None and args.labels.resolve().is_relative_to(REPO_ROOT):
        parser.error("keep the labels file outside the repository: the feed log is marked not to be shared")
    sys.stdout.write("\n".join(report(args.db, titles=args.titles, labels=args.labels)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
