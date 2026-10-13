"""scripts/weekly_brief.py: a thin entry point (usage errors, option mapping, where output goes)."""

from __future__ import annotations

import importlib.util

import pytest

from app.services.brief.run import RunResult

from .test_brief_support import BACKEND, brief_isolation  # noqa: F401

SCRIPT = BACKEND / "scripts" / "weekly_brief.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("weekly_brief_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def captured(script, monkeypatch):
    seen = {}

    def fake_run(options, emit=None, share_count_fn=None):
        seen["options"] = options
        seen["emit"] = emit
        seen["share_count_fn"] = share_count_fn
        result = seen["result"]
        if emit is not None and result.brief and result.written_to is None:
            emit(result.brief)  # what the real run does before it appends its log
        return result

    monkeypatch.setattr(script, "run_weekly_brief", fake_run)
    seen["result"] = RunResult(0, ("line one", "line two"), ())
    return seen


def test_defaults_refresh_print_and_do_not_redact(script, captured, capsys):
    code = script.main([])

    options = captured["options"]
    assert code == 0 and options.refresh is True and options.redact is False
    assert options.holdings_path is None and options.out is None
    assert capsys.readouterr().out == "line one\nline two\n"


def test_the_options_are_mapped(script, captured, tmp_path):
    script.main(["--holdings", str(tmp_path / "h.toml"), "--redact", "--no-refresh", "--out", str(tmp_path / "o.txt")])

    options = captured["options"]
    assert options.holdings_path == tmp_path / "h.toml" and options.out == tmp_path / "o.txt"
    assert options.redact is True and options.refresh is False


def test_sizing_is_on_by_default_and_the_flag_turns_it_off(script, captured):
    script.main([])
    assert captured["options"].sizing is True

    script.main(["--no-sizing"])
    assert captured["options"].sizing is False and captured["options"].refresh is True  # prices are still refreshed


def test_the_script_hands_the_run_the_one_share_count_fetch_function(script, captured):
    from app.services.share_count.fetch import read_share_count

    script.main([])

    assert captured["share_count_fn"] is read_share_count


def test_messages_go_to_stderr_and_the_exit_code_is_returned(script, captured, capsys):
    captured["result"] = RunResult(1, (), ("error: nope",))

    code = script.main([])

    out = capsys.readouterr()
    assert code == 1 and out.out == "" and "error: nope" in out.err


def test_a_written_brief_is_not_also_printed(script, captured, capsys, tmp_path):
    captured["result"] = RunResult(0, ("secret line",), (), written_to=tmp_path / "o.txt")

    script.main(["--out", str(tmp_path / "o.txt")])

    out = capsys.readouterr()
    assert "secret line" not in out.out and "o.txt" in out.err


def test_an_unknown_option_is_a_usage_error_with_no_run(script, captured):
    assert script.main(["--bogus"]) == 2
    assert "options" not in captured


def test_help_exits_zero_and_describes_the_privacy_rules(script, captured, capsys):
    assert script.main(["--help"]) == 0
    text = capsys.readouterr().out
    assert "chmod 600" in text and "/mnt/c" in text and "after the market close" in text
    assert "Personal, non-commercial" in text and "Exit code" in text


def test_the_brief_goes_through_the_emit_hook_and_is_flushed(script, captured, capsys):
    script.main([])

    assert captured["emit"] is script._emit_stdout
    assert capsys.readouterr().out == "line one\nline two\n"


def test_a_closed_pipe_is_reported_by_the_emit_hook_as_an_error(script, monkeypatch):
    class Broken:
        def write(self, text):
            raise BrokenPipeError()

        def flush(self):
            pass

        def fileno(self):
            raise OSError

    monkeypatch.setattr(script.sys, "stdout", Broken())

    with pytest.raises(BrokenPipeError):
        script._emit_stdout(("a",))


def test_ctrl_c_returns_130_with_a_message(script, monkeypatch, capsys):
    def interrupted(options, emit=None, share_count_fn=None):
        raise KeyboardInterrupt()

    monkeypatch.setattr(script, "run_weekly_brief", interrupted)

    assert script.main([]) == 130
    assert "no log line was added" in capsys.readouterr().err


def test_a_stdout_file_warning_is_printed_to_stderr(script, captured, monkeypatch, capsys):
    monkeypatch.setattr(script, "stdout_warnings", lambda fd, root, redact: ("warning: demo",))
    monkeypatch.setattr(script.sys, "stdout", type("S", (), {"fileno": lambda self: 1, "write": lambda self, t: None, "flush": lambda self: None})())

    script.main([])

    assert "warning: demo" in capsys.readouterr().err


def test_the_script_has_the_package_plus_thin_script_shape():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "sys.path.insert(0" in source and "def build_parser" in source and "def main(argv" in source
    assert 'raise SystemExit(main())' in source
    assert "sqlite3" not in source and "tomllib" not in source  # logic lives in the package


def test_the_no_refresh_help_and_docstring_say_the_share_count_call_can_still_happen(script):
    parser = script.build_parser()
    help_text = next(a.help for a in parser._actions if "--no-refresh" in a.option_strings)

    assert "prices" in help_text and "--no-sizing" in help_text and "share count" in help_text
    doc = " ".join(script.__doc__.split())
    assert "`--no-refresh` skips the price refresh only" in doc and "the share-count call" in doc and "or `--no-sizing` is given" in doc
