"""run.py: the run order, the refusals, the outputs and the log (tasks 9.1; spec: run order, output location)."""

from __future__ import annotations

import json
import stat
from dataclasses import replace

import pytest

from app.services.brief import run as run_mod
from app.services.brief import wording
from app.services.brief.issued_log import IssuedLogError, read_log
from app.services.brief.run import RunOptions, Steps, run_weekly_brief

from .test_brief_support import (  # noqa: F401
    brief_env, brief_isolation, fake_loader_factory, ict, make_closes, sessions_ending, write_artifact, write_holdings_toml,
)

AFTER_CLOSE = ict("2026-10-09 16:30").astimezone()  # any aware time; the run converts it
RATE_LIMIT = "Rate limit exceeded. Process terminated."


def _toml(*tickers, levels=()):
    body = ""
    for number, ticker in enumerate(tickers):
        body += f'[[holdings]]\nticker = "{ticker}"\nshares = {4321 + number}\ncost = {40.5 + number}\npurchase_date = 2025-06-1{number}\n'
        for comparator, price in levels:
            body += f'\n  [[holdings.levels]]\n  comparator = "{comparator}"\n  price = {price}\n  entered = 2026-10-02\n  text = "own words, sell or buy"\n'
    return body


@pytest.fixture
def world(tmp_path, brief_env):
    """A repo root, a private config directory, and three priced tickers."""
    repo = tmp_path / "repo"
    (repo / "reports").mkdir(parents=True)
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    for seed, ticker in enumerate(("AAA", "BBB", "CCC"), start=1):
        brief_env.add_ticker(ticker, make_closes(400, seed=seed))
    holdings = write_holdings_toml(config / "holdings.toml", _toml("AAA", "BBB", "CCC"))
    return type("World", (), {"repo": repo, "config": config, "holdings": holdings, "env": brief_env, "tmp": tmp_path})


def _run(world, *, redact=False, refresh=False, out=None, loader=None, now=AFTER_CLOSE, steps=None, holdings=None):
    options = RunOptions(holdings_path=holdings or world.holdings, redact=redact, out=out, refresh=refresh)
    kwargs = {"steps": steps} if steps else {}
    return run_weekly_brief(options, repo_root=world.repo, now=now, loader=loader, sleep=lambda s: None, **kwargs)


def _log(world):
    return read_log(world.config / "holdings_issued.jsonl")


# --- refusals come first -------------------------------------------------------------------------------

def test_a_world_readable_file_exits_1_before_any_loader_call(world):
    world.holdings.chmod(0o644)
    loader = fake_loader_factory()

    result = _run(world, refresh=True, loader=loader)

    assert result.exit_code == 1 and loader.calls == [] and result.brief == ()
    assert "chmod 600" in " ".join(result.messages)


def test_a_missing_file_names_the_path_and_calls_nothing(world):
    missing = world.config / "nope.toml"
    loader = fake_loader_factory()

    result = _run(world, refresh=True, loader=loader, holdings=missing)

    assert result.exit_code == 1 and str(missing) in " ".join(result.messages) and loader.calls == []


def test_a_holdings_file_inside_the_repository_exits_1(world):
    inside = write_holdings_toml(world.repo / "holdings.toml", _toml("AAA"))

    result = _run(world, refresh=True, loader=fake_loader_factory(), holdings=inside)

    assert result.exit_code == 1 and "inside the repository" in " ".join(result.messages)


def test_an_invalid_entry_exits_1_without_echoing_shares_or_cost(world):
    bad = write_holdings_toml(world.config / "bad.toml", '[[holdings]]\nticker = "sab"\nshares = 7654321\ncost = 98765.4\n')

    result = _run(world, holdings=bad)

    assert result.exit_code == 1
    assert "7654321" not in " ".join(result.messages) and "98765.4" not in " ".join(result.messages)


def test_the_disclaimer_guard_aborts_before_any_vendor_call_and_logs_nothing(world):
    write_artifact(world.env.model_path, range_coverage=0.80)
    loader = fake_loader_factory()
    out = world.tmp / "brief.txt"

    result = _run(world, refresh=True, loader=loader, out=out)

    assert result.exit_code == 1 and loader.calls == [] and result.brief == ()
    assert "range coverage" in " ".join(result.messages) and not out.exists()
    assert not (world.config / "holdings_issued.jsonl").exists()


def test_a_missing_model_still_prints_a_complete_brief(world):
    world.env.model_path.unlink()

    result = _run(world)

    assert result.exit_code == 0
    text = "\n".join(result.brief)
    assert text.count("No range this week: the volatility model file is missing or unusable.") == 3
    assert result.brief[-1] == wording.BRIEF_DISCLAIMER


# --- run order ---------------------------------------------------------------------------------------------

def test_the_run_order(world, tmp_path):
    order: list[str] = []
    real = Steps()

    def recording(name, function):
        def call(*args, **kwargs):
            order.append(name)
            return function(*args, **kwargs)
        return call

    steps = replace(
        real,
        load_holdings=recording("holdings", real.load_holdings),
        read_log=recording("log", real.read_log),
        load_model=recording("model", real.load_model),
        disclaimer_for=recording("disclaimer", real.disclaimer_for),
        refresh_tickers=recording("refresh", real.refresh_tickers),
        gather=recording("facts", real.gather),
        build_brief=recording("render", real.build_brief),
        write_output=recording("output", real.write_output),
        append_entries=recording("append", real.append_entries),
    )

    result = _run(world, refresh=True, loader=fake_loader_factory(), out=tmp_path / "brief.txt", steps=steps)

    assert result.exit_code == 0
    collapsed = [name for index, name in enumerate(order) if index == 0 or name != order[index - 1]]
    assert collapsed == ["holdings", "log", "model", "disclaimer", "refresh", "facts", "render", "output", "append"]


# --- refresh behaviour ----------------------------------------------------------------------------------

def test_every_ticker_is_refreshed_once_in_file_order(world):
    loader = fake_loader_factory()

    result = _run(world, refresh=True, loader=loader)

    assert result.exit_code == 0 and loader.calls == ["AAA", "BBB", "CCC"]
    assert "Prices refreshed this run." in "\n".join(result.brief)


def test_no_refresh_never_calls_the_loader_and_says_so(world):
    loader = fake_loader_factory()

    result = _run(world, refresh=False, loader=loader)

    assert loader.calls == [] and wording.NOT_REFRESHED_LINE in "\n".join(result.brief)


def test_the_vendor_limiter_ends_one_call_and_all_three_still_appear(world):
    loader = fake_loader_factory({"BBB": SystemExit(RATE_LIMIT)})

    result = _run(world, refresh=True, loader=loader)

    text = "\n".join(result.brief)
    assert result.exit_code == 0 and loader.calls == ["AAA", "BBB"]
    for ticker in ("AAA", "BBB", "CCC"):
        assert f"--- {ticker} " in text
    assert "not attempted" in text and len(_log(world).entries) == 3


def test_a_genuine_exit_propagates_and_no_brief_is_produced(world):
    loader = fake_loader_factory({"AAA": SystemExit("interpreter is going down")})

    with pytest.raises(SystemExit):
        _run(world, refresh=True, loader=loader)

    assert not (world.config / "holdings_issued.jsonl").exists()


def test_a_refresh_error_on_one_ticker_degrades_only_that_holding(world):
    loader = fake_loader_factory({"BBB": RuntimeError("boom")})

    result = _run(world, refresh=True, loader=loader)

    text = "\n".join(result.brief)
    assert result.exit_code == 0 and "refresh failed; last bar 2026-10-09" in text
    assert text.count("refresh failed; last bar") == 1


# --- degraded holdings keep exit 0 ---------------------------------------------------------------------

def test_a_ticker_without_prices_and_one_that_errors_are_still_in_the_brief_and_the_log(world, tmp_path):
    holdings = write_holdings_toml(world.config / "h2.toml", _toml("AAA", "NOPRICE", "BBB"))
    real = Steps()

    def gather(ticker, **kwargs):
        broken = (lambda t: 1 / 0) if ticker == "BBB" else None
        return real.gather(ticker, **kwargs, **({"range_fn": broken} if broken else {}))

    result = _run(world, holdings=holdings, steps=replace(real, gather=gather))

    text = "\n".join(result.brief)
    assert result.exit_code == 0
    assert "No stored prices for NOPRICE." in text and "could not be computed (ZeroDivisionError); see the log." in text
    statuses = {e.ticker: e.status for e in _log(world).entries}
    assert statuses == {"AAA": "ok", "NOPRICE": "no_prices", "BBB": "error"}


# --- the log ---------------------------------------------------------------------------------------------

def test_one_private_line_per_holding_beside_the_holdings_file(world):
    result = _run(world)

    path = world.config / "holdings_issued.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert result.exit_code == 0 and [r["ticker"] for r in rows] == ["AAA", "BBB", "CCC"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    text = path.read_text()
    for secret in ("4321", "4322", "40.5", "41.5", "2025-06-1"):
        assert secret not in text


def test_a_redacted_run_still_appends_to_the_log(world):
    _run(world, redact=True)

    assert len(_log(world).entries) == 3


def test_the_log_records_market_figures_only_never_a_level_or_a_holding(world):
    holdings = write_holdings_toml(world.config / "holdings.toml", _toml("AAA", levels=(("below", 1000.0), ("above", 1000.0))))

    _run(world, holdings=holdings)

    (entry,) = _log(world).entries
    assert entry.close == round(entry.close, 2) and entry.status == "ok" and entry.calibrated is True
    assert entry.model_version == "har-rv-test-0001" and entry.refreshed is False
    text = (world.config / "holdings_issued.jsonl").read_text()
    assert "own words" not in text and "1000.0" not in text and "levels" not in text and "comparator" not in text


def test_a_provisional_run_is_not_refused_and_logs_provisional_true(world):
    result = _run(world, now=ict("2026-10-09 11:00"))

    assert result.exit_code == 0 and result.brief[1] == wording.PROVISIONAL_WARNING
    assert all(e.provisional for e in _log(world).entries)


def test_a_run_after_the_close_logs_provisional_false(world):
    _run(world, now=ict("2026-10-09 16:30"))

    assert not any(e.provisional for e in _log(world).entries)


def test_an_append_failure_after_the_brief_exits_1_and_says_so(world):
    def failing(path, entries):
        raise IssuedLogError("the issued-brief log could not be appended to (PermissionError)")

    result = _run(world, steps=replace(Steps(), append_entries=failing))

    assert result.exit_code == 1 and result.brief and "could not be appended" in " ".join(result.messages)


def test_the_next_weeks_run_compares_with_the_range_that_was_logged(world):
    import math

    first = _run(world)
    assert "first brief: no previous range" in "\n".join(first.brief)
    issued = {e.ticker: e for e in _log(world).entries}
    for ticker, seed in (("AAA", 1), ("BBB", 2), ("CCC", 3)):
        closes = list(make_closes(400, seed=seed))
        extension = [closes[-1] * (1 + 0.004 * n) for n in range(1, 6)]
        world.env.add_ticker(ticker, [*closes, *extension], sessions_ending("2026-10-16", 405))

    second = _run(world, now=ict("2026-10-16 16:30"))

    assert not any(line.startswith("NOTE:") for line in second.brief)  # the stored closes did not change
    for ticker, seed in (("AAA", 1), ("BBB", 2), ("CCC", 3)):
        entry = issued[ticker]
        base = list(make_closes(400, seed=seed))[-1]
        inside = abs(math.log(base * (1 + 0.004 * 5) / base)) * 100 <= entry.band_pct
        sentence = (
            f"Last week's range was ±{round(entry.band_pct, 2):g}% ({entry.band_lo:.2f} to {entry.band_hi:.2f}): "
            f"the close was {'inside' if inside else 'outside'} it."
        )
        assert sentence in second.brief, sentence


def test_a_bad_log_line_is_skipped_counted_and_the_brief_is_produced(world):
    (world.config / "holdings_issued.jsonl").write_text("garbage\n")

    result = _run(world)

    assert result.exit_code == 0 and any("1 line" in m and "skipped" in m for m in result.messages)


# --- output ---------------------------------------------------------------------------------------------

def test_stdout_is_the_default_and_nothing_is_written_under_the_repository(world):
    before = sorted(world.repo.rglob("*"))

    result = _run(world)

    assert result.written_to is None and result.brief
    assert sorted(world.repo.rglob("*")) == before


def test_out_writes_a_private_file(world, tmp_path):
    out = tmp_path / "elsewhere" / "brief.txt"
    out.parent.mkdir()

    result = _run(world, out=out)

    assert result.exit_code == 0 and result.written_to == out
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert out.read_text().splitlines() == list(result.brief)


def test_out_replaces_an_existing_file_and_makes_it_private(world, tmp_path):
    out = tmp_path / "brief.txt"
    out.write_text("old")
    out.chmod(0o644)

    _run(world, out=out)

    assert stat.S_IMODE(out.stat().st_mode) == 0o600 and out.read_text() != "old"


@pytest.mark.parametrize("redact", [False, True])
def test_out_inside_reports_is_refused_always(world, redact):
    target = world.repo / "reports" / "brief.txt"
    loader = fake_loader_factory()

    result = _run(world, redact=redact, out=target, refresh=True, loader=loader)

    assert result.exit_code == 1 and not target.exists() and loader.calls == []


def test_an_unredacted_brief_may_not_go_anywhere_in_the_repository(world):
    target = world.repo / "notes" / "brief.txt"
    target.parent.mkdir()

    result = _run(world, out=target)

    assert result.exit_code == 1 and not target.exists()


def test_a_redacted_brief_may_not_go_inside_the_repository_either(world):
    target = world.repo / "notes" / "brief.txt"
    target.parent.mkdir()

    result = _run(world, redact=True, out=target)

    assert result.exit_code == 1 and not target.exists() and "inside the repository" in " ".join(result.messages)


def test_a_failed_output_write_exits_1_and_does_not_log(world, tmp_path):
    result = _run(world, out=tmp_path / "missing_dir" / "brief.txt")

    assert result.exit_code == 1 and not (world.config / "holdings_issued.jsonl").exists()


def test_a_directory_warning_goes_to_the_messages(world):
    world.config.chmod(0o755)

    result = _run(world)

    assert result.exit_code == 0 and any("directory" in m for m in result.messages)


# --- a re-run on the same bar reads what an earlier week said, never its own entry ------------------------

def _seed_log(world, *entries):
    from app.services.brief.issued_log import append_entries

    append_entries(world.config / "holdings_issued.jsonl", entries)


def _facts_text(result):
    return [line for line in result.brief if line.startswith(("NOTE:", "Last week's range", "first brief", "no range was issued", "last week's brief"))]


def test_a_rerun_on_the_same_bar_says_the_same_things_about_the_past(world):
    from .test_brief_support import make_issued_entry

    dates = sessions_ending("2026-10-09", 400)
    seeded = (
        make_issued_entry("AAA", as_of=dates[-6], close=41.0, band_pct=2.7, band_lo=39.9, band_hi=42.1),
        make_issued_entry("BBB", as_of=dates[-30], close=999.0),  # a close that no longer matches: the NOTE
    )
    _seed_log(world, *seeded)

    first = _run(world)
    redacted = _run(world, redact=True)
    again = _run(world)

    assert _facts_text(first) == _facts_text(again) and _facts_text(first)
    assert any("first brief" in l for l in first.brief) and any("NOTE: the close stored for" in l for l in first.brief)
    # the redacted copy keeps the NOTE and drops every log-derived week sentence; the NOTE is unchanged between runs
    assert [l for l in redacted.brief if l.startswith("NOTE:")] == [l for l in first.brief if l.startswith("NOTE:")]
    assert not any(l.startswith(("Last week's range", "first brief")) for l in redacted.brief)


def test_the_first_brief_wording_survives_a_rerun(world):
    first = _run(world)
    second = _run(world)

    assert [l for l in first.brief if "first brief" in l] == [l for l in second.brief if "first brief" in l]
    assert sum("first brief" in l for l in first.brief) == 3


# --- print before append ----------------------------------------------------------------------------------

def test_the_log_is_appended_only_after_the_brief_was_emitted(world):
    order = []
    real = Steps()
    steps = replace(real, append_entries=lambda path, entries: order.append("append") or real.append_entries(path, entries))

    result = _run_with_emit(world, lambda lines: order.append(f"emit:{len(lines)}"), steps=steps)

    assert result.exit_code == 0 and order[0].startswith("emit:") and order[-1] == "append"


def _run_with_emit(world, emit, steps=None, **options):
    opts = RunOptions(holdings_path=world.holdings, redact=options.get("redact", False), out=options.get("out"), refresh=False)
    return run_weekly_brief(opts, repo_root=world.repo, now=AFTER_CLOSE, sleep=lambda s: None, steps=steps or Steps(), emit=emit)


def test_a_closed_pipe_exits_1_and_leaves_no_log_entry(world):
    def broken_pipe(lines):
        raise BrokenPipeError()

    result = _run_with_emit(world, broken_pipe)

    assert result.exit_code == 1 and "no log line was added" in " ".join(result.messages)
    assert not (world.config / "holdings_issued.jsonl").exists()


def test_ctrl_c_while_writing_leaves_no_log_entry(world):
    def interrupted(lines):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        _run_with_emit(world, interrupted)

    assert not (world.config / "holdings_issued.jsonl").exists()


def test_a_failed_file_write_leaves_no_log_entry(world, tmp_path):
    result = _run(world, out=tmp_path / "no_such_dir" / "brief.txt")

    assert result.exit_code == 1 and not (world.config / "holdings_issued.jsonl").exists()


# --- output safety -----------------------------------------------------------------------------------------

def test_out_may_not_be_the_holdings_file_or_the_log(world):
    loader = fake_loader_factory()
    for target in (world.holdings, world.config / "holdings_issued.jsonl"):
        (world.config / "holdings_issued.jsonl").write_text("")
        before = world.holdings.read_text()

        result = _run(world, out=target, refresh=True, loader=loader)

        assert result.exit_code == 1 and "holdings file or the issued-brief log" in " ".join(result.messages)
        assert world.holdings.read_text() == before and loader.calls == []


def test_out_may_not_be_a_hard_link_to_the_holdings_file(world, tmp_path):
    link = tmp_path / "alias.txt"
    os_link = __import__("os").link
    os_link(world.holdings, link)

    result = _run(world, out=link)

    assert result.exit_code == 1 and world.holdings.read_text().startswith("[[holdings]]")


def test_out_is_never_written_through_a_symlink(world, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    link = tmp_path / "link.txt"
    link.symlink_to(victim)

    result = _run(world, out=link)

    assert result.exit_code == 1 and victim.read_text() == "keep me"


def test_a_short_write_is_completed(tmp_path, monkeypatch):
    import os

    real = os.write
    monkeypatch.setattr(run_mod.os, "write", lambda fd, data: real(fd, bytes(data[:7])))
    out = tmp_path / "brief.txt"
    lines = tuple(f"line {n} " + "x" * 40 for n in range(20))

    run_mod.write_output(out, lines)

    assert out.read_text().splitlines() == list(lines)


def test_the_issued_log_may_never_land_in_the_repository(world):
    inside = world.repo / "somewhere" / "holdings.toml"
    inside.parent.mkdir()
    steps = replace(Steps(), load_holdings=lambda path, **kw: Steps().load_holdings(world.holdings, **kw))

    result = _run(world, holdings=inside, steps=steps)  # a loader that passes: the log check still refuses

    assert result.exit_code == 1 and "inside the repository" in " ".join(result.messages)
    assert not (inside.parent / "holdings_issued.jsonl").exists()


def test_a_directory_others_can_write_is_refused(world):
    world.config.chmod(0o770)

    result = _run(world, refresh=True, loader=fake_loader_factory())

    assert result.exit_code == 1 and "chmod 700" in " ".join(result.messages)


def test_a_git_working_tree_above_the_holdings_gives_a_warning(world):
    (world.tmp / ".git").mkdir()

    result = _run(world)

    assert result.exit_code == 0 and any("git working tree" in m for m in result.messages)


# --- third-party text never enters the brief -----------------------------------------------------------

def test_text_a_refresh_prints_goes_to_stderr_not_into_the_brief(world, capsys):
    def noisy_loader(ticker, timings=None):
        print("VNAI PROMO: upgrade now")
        return {"status": "ok"}

    result = _run(world, refresh=True, loader=noisy_loader)

    captured = capsys.readouterr()
    assert "VNAI PROMO" not in "\n".join(result.brief) and "VNAI PROMO" not in captured.out
    assert "VNAI PROMO" in captured.err


# --- the final text guard ---------------------------------------------------------------------------------

def test_a_failed_text_guard_exits_1_with_no_output_and_no_log(world, monkeypatch, tmp_path):
    from app.services.brief import wording

    monkeypatch.setattr(wording, "FOOTER", "Please sell.")
    out = tmp_path / "brief.txt"

    result = _run(world, out=out)

    assert result.exit_code == 1 and result.brief == () and not out.exists()
    assert "line" in " ".join(result.messages) and not (world.config / "holdings_issued.jsonl").exists()


def test_a_holding_that_cannot_be_built_is_shown_and_the_others_are_still_logged(world, monkeypatch):
    from app.services.brief import compose

    real = compose.market_sections.next_five_lines

    def selective(facts):
        if facts.ticker == "BBB":
            raise KeyError("x")
        return real(facts)

    monkeypatch.setattr(compose.market_sections, "next_five_lines", selective)

    result = _run(world)

    assert "could not build this holding: KeyError" in "\n".join(result.brief)
    assert result.exit_code == 0 and [e.ticker for e in _log(world).entries] == ["AAA", "BBB", "CCC"]


# --- stdout destination warnings ---------------------------------------------------------------------------

def test_stdout_warnings_for_a_file_others_can_read(tmp_path):
    import os

    path = tmp_path / "out.txt"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
    os.fchmod(descriptor, 0o644)
    try:
        warnings = run_mod.stdout_warnings(descriptor, tmp_path / "repo", redact=False)
    finally:
        os.close(descriptor)

    assert any("readable by other users" in w for w in warnings)


def test_stdout_warnings_for_a_file_inside_the_repository(tmp_path):
    import os

    repo = tmp_path / "repo"
    repo.mkdir()
    descriptor = os.open(repo / "out.txt", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        warnings = run_mod.stdout_warnings(descriptor, repo, redact=False)
    finally:
        os.close(descriptor)

    assert any("inside the repository" in w for w in warnings) and not any("readable" in w for w in warnings)


def test_no_stdout_warning_for_a_pipe_a_private_outside_file_or_a_redacted_copy(tmp_path):
    import os

    read_end, write_end = os.pipe()
    private = os.open(tmp_path / "p.txt", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        assert run_mod.stdout_warnings(write_end, tmp_path / "repo", redact=False) == ()
        assert run_mod.stdout_warnings(private, tmp_path / "repo", redact=False) == ()
        assert run_mod.stdout_warnings(private, tmp_path, redact=True) == ()
    finally:
        for descriptor in (read_end, write_end, private):
            os.close(descriptor)
