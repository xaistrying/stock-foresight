"""The read-only accuracy-check script for the keyword classes (`add-announcement-tags-and-insider-sizing`, task 2.3):
counts by default, titles only on request, nothing written, and the labels arithmetic."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from app.db import company_feed_log

from .brief_announcement_rows import event_row, insider_row, news_item, press_item, store_rows
from .test_brief_support import brief_isolation  # noqa: F401

BACKEND = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("verify_announcement_classes", BACKEND / "scripts" / "verify_announcement_classes.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def _load():
    store_rows("AAA", "news", [
        news_item("AAA", "cổ tức bằng tiền", n=1), news_item("AAA", "báo cáo tài chính quý", n=2), news_item("AAA", "tăng vốn điều lệ", n=3),
        news_item("AAA", "mua lại trái phiếu", n=4), news_item("AAA", "nghị quyết cổ phiếu quỹ", n=5), press_item("press line", n=6),
    ])
    store_rows("AAA", "events", [
        insider_row("AAA", 1), event_row("AAA", "DIV", "cổ tức bằng tiền 1", published="2026-09-01"),
        event_row("AAA", "AIS", "niêm yết bổ sung 1", published="2026-09-02"),
    ])
    return company_feed_log.COMPANY_FEED_LOG_DB_PATH


def test_the_default_report_is_counts_only_and_prints_no_title():
    db = _load()

    text = "\n".join(script.report(db, titles=False, labels=None))

    assert "company filings read: 5" in text and "claimed by dividend: 1" in text and "claimed by capital: 1" in text
    assert "claimed by no class: 2" in text  # the bond notice and the unrelated one
    assert "unclassified filings containing a share or capital word: 1" in text
    assert "DDIND: insider shape 1" in text and "DIV: cash dividend keyword 1" in text and "AIS: additional listing keyword 1" in text
    for fragment in ("cổ tức bằng tiền", "AAA:", "Fictional"):
        assert fragment not in text.replace("cash dividend keyword", "").replace("claimed by dividend", "")


def test_titles_are_printed_only_when_asked():
    db = _load()

    text = "\n".join(script.report(db, titles=True, labels=None))

    assert "AAA: cổ tức bằng tiền" in text and "titles (for you only" in text


def test_the_log_is_opened_read_only_and_a_missing_log_reads_as_no_rows(tmp_path):
    db = _load()
    before = db.read_bytes()

    script.report(db, titles=True, labels=None)

    assert db.read_bytes() == before
    assert script.report(tmp_path / "absent.db", titles=False, labels=None)[0] == "company filings read: 0"
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        try:
            connection.execute("DELETE FROM company_feed_item")
        except sqlite3.OperationalError:
            return
        raise AssertionError("the read-only connection accepted a write")
    finally:
        connection.close()


def test_the_label_counts_claimed_correct_wrong_and_missed(tmp_path):
    db = _load()
    filings = script.classify_news(script.read_rows(db, "news"))
    claimed = {f["title"]: n for n, f in enumerate(filings, start=1)}
    labels = tmp_path / "labels.tsv"
    labels.write_text(
        f"{claimed['AAA: cổ tức bằng tiền']}\tdividend\n{claimed['AAA: báo cáo tài chính quý']}\tdividend\n"
        f"{claimed['AAA: nghị quyết cổ phiếu quỹ']}\tcapital\n", encoding="utf-8",
    )

    counts = script.label_counts(filings, script.read_labels(labels))

    assert counts["dividend"] == {"claimed": 1, "correct": 1, "wrong": 0, "missed": 1, "unlabelled": 0}
    assert counts["results"] == {"claimed": 1, "correct": 0, "wrong": 1, "missed": 0, "unlabelled": 0}
    assert counts["capital"]["missed"] == 1 and counts["capital"]["unlabelled"] == 1  # a claim nobody labelled is not "correct"


def test_a_class_needs_three_claims_and_no_wrong_one_to_be_enabled(tmp_path):
    db = _load()
    labels = tmp_path / "l.tsv"
    labels.write_text("1\tdividend\n", encoding="utf-8")

    text = "\n".join(script.report(db, titles=False, labels=labels))

    assert "label check dividend: claimed 1" in text and "stays disabled" in text and script.MIN_CLAIMED == 3


def test_a_class_with_a_claim_nobody_labelled_stays_disabled_even_with_enough_correct_ones(tmp_path):
    store_rows("BBB", "news", [news_item("BBB", f"cổ tức bằng tiền {i}", n=100 + i) for i in range(4)])
    filings = [f for f in script.classify_news(script.read_rows(company_feed_log.COMPANY_FEED_LOG_DB_PATH, "news")) if f["ticker"] == "BBB"]
    assert len(filings) == 4 and {f["claimed"] for f in filings} == {"dividend"}
    all_filings = script.classify_news(script.read_rows(company_feed_log.COMPANY_FEED_LOG_DB_PATH, "news"))
    numbers = [n for n, f in enumerate(all_filings, start=1) if f["ticker"] == "BBB"]
    labels = tmp_path / "labels.tsv"
    labels.write_text("".join(f"{n}\tdividend\n" for n in numbers[:3]), encoding="utf-8")  # the fourth claim is unlabelled

    counts = script.label_counts(all_filings, script.read_labels(labels))

    assert counts["dividend"]["claimed"] == 4 and counts["dividend"]["correct"] == 3 and counts["dividend"]["unlabelled"] == 1


def test_a_labels_file_inside_the_repository_is_refused(capsys):
    inside = script.REPO_ROOT / "backend" / "tests" / "labels_should_not_be_here.tsv"

    with __import__("pytest").raises(SystemExit) as caught:
        script.main(["--labels", str(inside)])

    assert caught.value.code == 2 and "outside the repository" in capsys.readouterr().err


def test_a_database_path_with_url_characters_is_opened_read_only(tmp_path):
    import shutil

    odd = tmp_path / "a?b#c%d"
    odd.mkdir()
    copy = odd / "log.db"
    store_rows("AAA", "news", [news_item("AAA", "cổ tức bằng tiền", n=1)])
    shutil.copy(company_feed_log.COMPANY_FEED_LOG_DB_PATH, copy)

    assert script.report(copy, titles=False, labels=None)[0] == "company filings read: 1"
