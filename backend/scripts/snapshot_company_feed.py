"""
Snapshot VCI company news and events, and the News agent's RSS feeds, into
`backend/data/company_feed_log.db` (`add-company-feed-news-and-events`, step P2a).

Run by hand, from the project root. It is the only thing that starts a snapshot: no debate
hook, no Refresh or load path, no startup hook and no scheduler calls it (a vnai rate-limit
`SystemExit` raised inside the server process would end the server):

    python backend/scripts/snapshot_company_feed.py --tickers SAB,VPB [--from-debate-log]
        [--tickers-per-minute N] [--no-rss] [--dry-run]

With neither `--tickers` nor `--from-debate-log` it exits with a usage error and makes no
request. `--from-debate-log` adds the distinct tickers in `debate_log.db`, opened read-only.
`--dry-run` fetches and prints what would be stored and writes nothing.

The clock ticks only when this runs. A daily run after the market close is recommended,
because the RSS feeds hold about four days and cannot be backfilled (the VCI items tolerate a
longer gap: each call returns at most 50). The summary prints how long ago the previous
successful fetch of each ticker and kind was, and warns on a `possible gap`. An example cron
line, which this change does NOT install (the project has no scheduler):

    30 15 * * 1-5  cd <project root> && backend/.venv/bin/python backend/scripts/snapshot_company_feed.py --from-debate-log >> <log file> 2>&1

Personal use only: the installed licence metadata says `vnstock` 4.0.5 is "Custom: Personal,
research, non-commercial" and `vnai` is "proprietary"; VCI's own terms for the endpoints were not
found. Work, paid or shared use needs whoever owns licensing first. The log is gitignored and is
not to be shared.

Guest tier, no API key: nothing here sets, reads, stores or logs a key. If `VNSTOCK_API_KEY` is
set or `~/.vnstock/api_key.json` exists, a warning is printed (existence only; the file is never
opened) and the run still goes ahead. Run one vendor script at a time: vnai's request counter
lives in the process, so two scripts do not share it. Titles are stored as fetched (cleaned,
never translated), and no language model is called.

Exit code: 0 only when every fetch ended `ok` or `empty` and every write succeeded; 1 otherwise
(an error, a rate limit that stopped the run, a failed write); 2 for a usage error.

The log is irreplaceable: the vendor returns 50 items per call and the RSS feeds hold about four
days, so lost history cannot be re-fetched, and it has no automatic backup. Back it up with
`sqlite3 backend/data/company_feed_log.db ".backup <copy outside the repo>"`; the recipe and the
standing caution (never `rm data/*.db` or `git clean -x` blindly) are in `docs/KNOWN_ISSUES.md`.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.company_feed import inputs, snapshot, store  # noqa: E402
from app.services.company_feed.summary import format_summary  # noqa: E402

logger = logging.getLogger("snapshot_company_feed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tickers", help="comma-separated tickers, e.g. SAB,VPB")
    parser.add_argument(
        "--from-debate-log", action="store_true",
        help="also take the distinct tickers in debate_log.db (opened read-only)",
    )
    parser.add_argument(
        "--tickers-per-minute", type=float, default=snapshot.Options().tickers_per_minute,
        help="start at most this many tickers a minute (default %(default)g): two vendor requests a "
             "ticker against vnai's guest limit of 20 a minute",
    )
    parser.add_argument("--no-rss", action="store_true", help="skip the three RSS feeds")
    parser.add_argument("--dry-run", action="store_true", help="fetch and print what would be stored; write nothing")
    return parser


def _tickers(parser: argparse.ArgumentParser, args: argparse.Namespace) -> tuple[str, ...]:
    if args.tickers is None and not args.from_debate_log:
        parser.error("give --tickers and/or --from-debate-log")
    try:
        explicit = inputs.parse_ticker_list(args.tickers or "")
    except ValueError as error:
        parser.error(str(error))
    from_log = inputs.tickers_from_debate_log() if args.from_debate_log else ()
    return inputs.merge_tickers(explicit, from_log)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if not args.tickers_per_minute > 0:
            parser.error("--tickers-per-minute must be positive")
        tickers = _tickers(parser, args)
    except SystemExit as exit_request:  # argparse's own exit: 0 for --help, 2 for a usage error
        return int(exit_request.code or 0)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for warning in inputs.api_key_warnings():
        print(f"WARNING: {warning}")
        logger.warning("%s", warning)
    if not tickers:
        print("No tickers to fetch" + ("; RSS only." if not args.no_rss else "."))

    options = snapshot.Options(
        tickers_per_minute=args.tickers_per_minute, include_rss=not args.no_rss, dry_run=args.dry_run,
    )
    summary = snapshot.run_snapshot(tickers, options)
    print(format_summary(summary, store.utc_now()))
    return summary.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
