"""
Weekly holdings brief (`add-weekly-holdings-brief`, N1): a plain-text check-in on the stocks you hold.

Run by hand, from the project root, after the market close (a run during the session works but its
last bar is provisional and the brief says so). Nothing else starts it: no route, startup hook, debate
hook or scheduler, and no language model is called.

    python backend/scripts/weekly_brief.py [--holdings PATH] [--redact] [--out PATH] [--no-refresh] [--no-sizing]

It refreshes each held ticker from the vendor (one call each, paced), then prints the close, the
usual 5-session range, last week's range against what happened, your own price levels checked
against the last close, and the weights of your holdings. It also lists cash dividends and share issues
from the stored company-announcement events, per share and not added up, and says when those events were last
fetched; it reads them and never fetches them (for a ticker with no stored events it prints the command for you
to run by hand). A COMPANY block per holding lists the stored announcements since the last brief (registered trades
by a major shareholder or insider, share issues and capital changes first), says when the source last answered, and
shows third-party titles in quotes, labelled as such. A registered trade with a stated quantity is sized against the
vendor's share count: that is the one extra vendor call (two requests) per such ticker, made only when the cached
count (`holdings_share_counts.json` beside the holdings file) is older than 7 days; `--no-sizing` makes no such call.
It never says what to do: it is technical
observation, not investment advice. Personal, non-commercial use only: the vendor licence says so.
If anyone else will use or receive the output, check the domain rules and the licence first.

Your holdings file is TOML and lives OUTSIDE the repository, by default at
`$XDG_CONFIG_HOME/stock-foresight/holdings.toml`, else `~/.config/stock-foresight/holdings.toml`.
Make it private before the first run:

    mkdir -p ~/.config/stock-foresight && chmod 700 ~/.config/stock-foresight
    chmod 600 ~/.config/stock-foresight/holdings.toml

The script refuses a file that is missing, not a regular file, owned by another user, readable by
group or others, larger than 256 KiB, in a directory others can write to, or inside the repository, and
says why before it calls the vendor. It also refuses a field it does not know (a typo would silently drop
a value). On WSL keep the file on the Linux filesystem: a file on a Windows drive (`/mnt/c`) reports mode 777 and is refused.
A hypothetical example (prices are thousand VND per share, as on the board):

    [[holdings]]
    ticker = "AAA"
    shares = 1000
    shares_as_of = 2025-06-10      # optional; defaults to purchase_date
    cost = 41.80                   # per share
    purchase_date = 2025-06-10     # optional ("not entered" in the brief)

      [[holdings.levels]]          # optional, any number
      comparator = "below"         # or "above"
      price = 41.60
      entered = 2026-10-02
      text = "Re-read the note if the close is below 41.60"

Levels are your words: the brief prints each text verbatim, labelled as yours with its entry date, and
only says reached or not reached and the distance.

`--redact` prints a copy with only market figures (no shares, cost, levels, weights or values) for
handing to a helper agent; the redacted copy still appends to the log, and it shows no announcement title and no
counterparty name. `--no-refresh` skips the price refresh only, for example to make the redacted copy after the real
run: the share-count call (two requests per ticker with a trade that states a quantity) can still happen unless the cached
count is under 7 days old or `--no-sizing` is given. `--out PATH` writes the brief
to a file with mode 600 instead of stdout; it refuses any path inside the repository (reports/ is for
uploads), the holdings file and the log, and never writes through a symlink. When stdout is a file that
others can read or that sits inside the repository, a warning goes to stderr.

After the brief has been written (to stdout or --out), one line per holding is appended to
`holdings_issued.jsonl` beside the holdings file (mode 600). It holds market figures only (close, range,
model version, provisional flag) and no shares, cost, levels or text, so next week's brief can compare
the week with the range that was issued. The set of tickers still shows what you hold: keep it private.
A run that fails to write the brief, or whose output pipe closes, appends nothing.

Run one vendor script at a time: vnai's request counter lives in the process.

Exit code: 0 a brief was produced (holdings that could not be computed are described in the text);
1 a refusal, a failed write, or a log line that could not be appended; 2 a usage error.
"""

import argparse
import contextlib
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.brief.run import REPO_ROOT, RunOptions, run_weekly_brief, stdout_warnings  # noqa: E402
from app.services.share_count.fetch import read_share_count  # noqa: E402  the only vendor call for a share count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--holdings", type=Path, help="the holdings TOML file (default: under XDG_CONFIG_HOME or ~/.config)")
    parser.add_argument("--redact", action="store_true", help="print market figures only: no shares, cost, levels or weights")
    parser.add_argument("--out", type=Path, help="write the brief to this file (mode 600) instead of stdout")
    parser.add_argument("--no-refresh", action="store_true", help="do not call the vendor for prices; use stored prices (the share count may still be fetched for a trade line unless --no-sizing is given or the cached count is under 7 days old)")
    parser.add_argument("--no-sizing", action="store_true", help="make no vendor call for a share count; trade lines show no size")
    return parser


def _emit_stdout(lines: tuple[str, ...]) -> None:
    """Write the brief to stdout and flush; a closed pipe is an error, and no log line may follow it."""
    try:
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        with contextlib.suppress(OSError, ValueError):  # keep the interpreter's own exit flush quiet
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        raise


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:  # argparse's own exit: 0 for --help, 2 for a usage error
        return int(exit_request.code or 0)

    # INFO from this app's own loggers; third-party libraries (vnai, matplotlib) stay at WARNING.
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("app").setLevel(logging.INFO)

    if args.out is None:
        with contextlib.suppress(OSError, ValueError, AttributeError):  # no usable descriptor (a test, a closed stdout)
            for warning in stdout_warnings(sys.stdout.fileno(), REPO_ROOT, redact=args.redact):
                print(warning, file=sys.stderr)
    options = RunOptions(
        holdings_path=args.holdings, redact=args.redact, out=args.out, refresh=not args.no_refresh, sizing=not args.no_sizing,
    )
    try:
        result = run_weekly_brief(options, emit=_emit_stdout, share_count_fn=read_share_count)
    except KeyboardInterrupt:
        print("error: interrupted; no log line was added for an unseen brief", file=sys.stderr)
        return 130
    if result.written_to is not None:
        print(f"The brief was written to {result.written_to}", file=sys.stderr)
    for message in result.messages:
        print(message, file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
