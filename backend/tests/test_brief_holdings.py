"""holdings.py: the TOML file, its validation and the refusals (spec: "Holdings live in a TOML file...")."""

from __future__ import annotations

import ast
import re
from datetime import date

import pytest

from app.services.brief import holdings as holdings_mod
from app.services.brief.holdings import HoldingsError, default_holdings_path, directory_warnings, load_holdings

from .test_brief_support import (  # noqa: F401  (brief_isolation is an autouse fixture)
    BACKEND, VALID_TOML, brief_isolation, write_holdings_toml,
)

TODAY = date(2026, 10, 12)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture
def outside(tmp_path):
    folder = tmp_path / "config"
    folder.mkdir(mode=0o700)
    return folder


def _load(path, repo, **kwargs):
    return load_holdings(path, repo_root=repo, today=TODAY, **kwargs)


def _entry(**fields):
    base = {"ticker": '"AAA"', "shares": "1000", "cost": "41.80"}
    base.update({k: v for k, v in fields.items() if v is not None})
    return "[[holdings]]\n" + "\n".join(f"{k} = {v}" for k, v in base.items()) + "\n"


def test_a_valid_file_loads_with_its_level(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", VALID_TOML)

    (holding,) = _load(path, repo)

    assert (holding.ticker, holding.shares, holding.cost) == ("AAA", 1000, 41.80)
    assert holding.purchase_date == date(2025, 6, 10)
    assert holding.shares_as_of == date(2025, 6, 10)  # defaults to purchase_date
    (level,) = holding.levels
    assert (level.comparator, level.price, level.entered) == ("below", 41.60, date(2026, 10, 2))
    assert level.text == "Trim 300 shares if the close is below 41.60"


def test_optional_fields_default_to_none(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", _entry())

    (holding,) = _load(path, repo)

    assert holding.purchase_date is None and holding.shares_as_of is None and holding.levels == ()  # neither date: null


def test_an_explicit_shares_as_of_is_kept(outside, repo):
    body = _entry(purchase_date="2025-06-10", shares_as_of="2025-07-01")
    path = write_holdings_toml(outside / "holdings.toml", body)

    (holding,) = _load(path, repo)

    assert holding.purchase_date == date(2025, 6, 10) and holding.shares_as_of == date(2025, 7, 1)


def test_shares_as_of_defaults_to_the_purchase_date(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", _entry(purchase_date="2025-06-10"))

    (holding,) = _load(path, repo)

    assert holding.shares_as_of == date(2025, 6, 10)


def test_iso_strings_are_accepted_as_dates(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", _entry(purchase_date='"2025-06-10"'))

    assert _load(path, repo)[0].purchase_date == date(2025, 6, 10)


def test_integer_costs_are_accepted(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", _entry(cost="42"))

    assert _load(path, repo)[0].cost == 42.0


@pytest.mark.parametrize(
    ("fields", "mentions"),
    [
        ({"shares": "0"}, "shares"),
        ({"shares": "-5"}, "shares"),
        ({"shares": "10.5"}, "shares"),
        ({"shares": "true"}, "shares"),
        ({"shares": '"1000"'}, "shares"),
        ({"cost": "0"}, "cost"),
        ({"cost": '"41.8"'}, "cost"),
        ({"cost": "nan"}, "cost"),
        ({"ticker": '"sab"'}, "ticker"),
        ({"ticker": '"TOOLONGTICKER1"'}, "ticker"),
        ({"ticker": "7"}, "ticker"),
        ({"purchase_date": "2026-10-13"}, "purchase_date"),
        ({"purchase_date": '"not a date"'}, "purchase_date"),
        ({"shares_as_of": "2027-01-01"}, "shares_as_of"),
    ],
)
def test_each_invalid_field_is_named_without_echoing_shares_or_cost(outside, repo, fields, mentions):
    fields = {"shares": "7654321", "cost": "98765.4", **fields}
    path = write_holdings_toml(outside / "holdings.toml", _entry(**fields))

    with pytest.raises(HoldingsError) as caught:
        _load(path, repo)

    message = str(caught.value)
    assert mentions in message and "entry 1" in message
    assert "7654321" not in message and "98765.4" not in message


def test_a_missing_field_is_named(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", "[[holdings]]\nticker = \"AAA\"\nshares = 5\n")

    with pytest.raises(HoldingsError, match="cost"):
        _load(path, repo)


LEVEL = """
  [[holdings.levels]]
  comparator = "below"
  price = 41.6
  entered = 2026-10-02
  text = "x"
"""


@pytest.mark.parametrize(
    ("old", "new", "mentions"),
    [
        ('comparator = "below"', 'comparator = "near"', "comparator"),
        ("entered = 2026-10-02\n", "", "entered"),
        ("price = 41.6", "price = 0", "price"),
        ("price = 41.6\n", "", "price"),
        ('text = "x"', 'text = ""', "text"),
        ('text = "x"', 'text = "' + "y" * 301 + '"', "text"),
        ('text = "x"', 'text = "a\\nb"', "text"),
        ('text = "x"', 'text = "a\\u0007b"', "text"),
        ("entered = 2026-10-02", "entered = 2026-11-02", "entered"),
    ],
)
def test_each_invalid_level_field_is_named(outside, repo, old, new, mentions):
    path = write_holdings_toml(outside / "holdings.toml", _entry() + LEVEL.replace(old, new))

    with pytest.raises(HoldingsError) as caught:
        _load(path, repo)

    assert mentions in str(caught.value) and "level 1" in str(caught.value)


def test_a_level_text_of_exactly_300_characters_is_accepted(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", _entry() + LEVEL.replace('"x"', '"' + "y" * 300 + '"'))

    assert len(_load(path, repo)[0].levels[0].text) == 300


def test_a_duplicate_ticker_is_refused(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", _entry() + _entry(shares="5"))

    with pytest.raises(HoldingsError, match="more than once"):
        _load(path, repo)


def test_a_file_without_holdings_is_refused(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", "# nothing here\n")

    with pytest.raises(HoldingsError, match="no holdings"):
        _load(path, repo)


def test_broken_toml_names_a_position_but_not_the_content(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", "[[holdings]]\nshares = 7654321 7654321\n")

    with pytest.raises(HoldingsError) as caught:
        _load(path, repo)

    assert "TOML" in str(caught.value) and "7654321" not in str(caught.value)


@pytest.mark.parametrize("mode", [0o600, 0o400])
def test_private_modes_are_accepted(outside, repo, mode):
    path = write_holdings_toml(outside / "holdings.toml", _entry(), mode=mode)

    assert _load(path, repo)[0].ticker == "AAA"


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o660, 0o777])
def test_group_or_world_access_is_refused_and_mode_600_is_asked_for(outside, repo, mode):
    path = write_holdings_toml(outside / "holdings.toml", _entry(), mode=mode)

    with pytest.raises(HoldingsError, match="chmod 600"):
        _load(path, repo)


def test_a_file_owned_by_someone_else_is_refused(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", _entry())

    with pytest.raises(HoldingsError, match="owned by another user"):
        load_holdings(path, repo_root=repo, today=TODAY, uid=path.stat().st_uid + 1)


def test_a_missing_file_names_the_path_and_nothing_else(outside, repo):
    path = outside / "holdings.toml"

    with pytest.raises(HoldingsError) as caught:
        _load(path, repo)

    assert str(path) in str(caught.value)


def test_a_directory_is_not_a_holdings_file(outside, repo):
    with pytest.raises(HoldingsError, match="not a regular file"):
        _load(outside, repo)


def test_a_path_inside_the_repository_is_refused_before_it_is_read(repo):
    inside = repo / "backend" / "holdings.toml"  # does not exist: the refusal comes first

    with pytest.raises(HoldingsError, match="inside the repository"):
        _load(inside, repo)


def test_a_symlink_into_the_repository_is_refused(outside, repo):
    target = write_holdings_toml(repo / "real.toml", _entry())
    link = outside / "holdings.toml"
    link.symlink_to(target)

    with pytest.raises(HoldingsError, match="inside the repository"):
        _load(link, repo)


def test_the_default_path_uses_xdg_config_home():
    assert default_holdings_path({"XDG_CONFIG_HOME": "/cfg"}) == holdings_mod.Path("/cfg/stock-foresight/holdings.toml")


def test_the_default_path_falls_back_to_dot_config(tmp_path):
    expected = tmp_path / ".config" / "stock-foresight" / "holdings.toml"

    assert default_holdings_path({}, home=tmp_path) == expected
    assert default_holdings_path({"XDG_CONFIG_HOME": ""}, home=tmp_path) == expected


def test_the_default_path_is_outside_the_repository():
    assert not default_holdings_path().resolve().is_relative_to(BACKEND.parent)


def test_a_readable_directory_gives_a_warning_not_a_refusal(tmp_path, repo):
    open_dir = tmp_path / "open"
    open_dir.mkdir()
    open_dir.chmod(0o755)
    path = write_holdings_toml(open_dir / "holdings.toml", _entry())

    assert any("directory" in w for w in directory_warnings(path))
    assert _load(path, repo)[0].ticker == "AAA"


@pytest.mark.parametrize("mode", [0o770, 0o702, 0o777, 0o720])
def test_a_directory_others_can_write_is_refused(tmp_path, repo, mode):
    shared = tmp_path / "shared"
    shared.mkdir()
    path = write_holdings_toml(shared / "holdings.toml", _entry())
    shared.chmod(mode)

    with pytest.raises(HoldingsError, match="chmod 700"):
        _load(path, repo)


def test_a_private_directory_gives_no_warning(outside):
    path = write_holdings_toml(outside / "holdings.toml", _entry())

    assert directory_warnings(path) == ()


def test_a_git_working_tree_above_the_file_gives_a_warning(outside):
    (outside / ".git").mkdir()
    nested = outside / "sub"
    nested.mkdir(mode=0o700)
    path = write_holdings_toml(nested / "holdings.toml", _entry())

    assert any("git working tree" in w for w in directory_warnings(path))


def test_a_symlinked_holdings_path_is_read_from_its_target(tmp_path, outside, repo):
    target_dir = tmp_path / "real"
    target_dir.mkdir(mode=0o700)
    target = write_holdings_toml(target_dir / "holdings.toml", _entry())
    link = outside / "holdings.toml"
    link.symlink_to(target)

    assert _load(link, repo)[0].ticker == "AAA"


def test_the_file_is_opened_without_following_a_final_symlink_and_read_from_one_descriptor():
    import inspect

    source = inspect.getsource(holdings_mod._read_private_file)

    assert "O_NOFOLLOW" in source and "fstat" in source and "read_text" not in source


# --- hardening: unknown keys, caps, odd characters, hostile TOML ---------------------------------------

def test_an_unknown_entry_key_is_named_without_its_value(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", _entry(share_count="7654321"))

    with pytest.raises(HoldingsError) as caught:
        _load(path, repo)

    assert "share_count" in str(caught.value) and "entry 1" in str(caught.value) and "7654321" not in str(caught.value)


def test_an_unknown_level_key_is_named(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", _entry() + LEVEL.replace('text = "x"', 'text = "x"\n  priority = 9'))

    with pytest.raises(HoldingsError, match='level 1: unknown field "priority"'):
        _load(path, repo)


@pytest.mark.parametrize("char", ["\u2028", "\u2029", "\u0085", "\u202e", "\u200b", "\ue000", "\u0378"])
def test_a_level_text_with_a_hidden_or_separator_character_is_refused(outside, repo, char):
    escaped = f"\\u{ord(char):04x}"
    path = write_holdings_toml(outside / "holdings.toml", _entry() + LEVEL.replace('text = "x"', f'text = "a{escaped}b"'))

    with pytest.raises(HoldingsError, match="text"):
        _load(path, repo)


def test_shares_above_the_cap_are_refused(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", _entry(shares=str(10**12 + 1)))

    with pytest.raises(HoldingsError, match="shares"):
        _load(path, repo)
    ok = write_holdings_toml(outside / "ok.toml", _entry(shares=str(10**12)))
    assert _load(ok, repo)[0].shares == 10**12


def test_a_file_over_256_kib_is_refused(outside, repo):
    path = write_holdings_toml(outside / "holdings.toml", "# " + "x" * (256 * 1024) + "\n" + _entry())

    with pytest.raises(HoldingsError, match="larger than 256 KiB"):
        _load(path, repo)


def test_too_many_holdings_and_too_many_levels_are_refused(outside, repo):
    many = "".join(_entry(ticker=f'"T{n}"') for n in range(holdings_mod.MAX_HOLDINGS + 1))
    with pytest.raises(HoldingsError, match="more than"):
        _load(write_holdings_toml(outside / "a.toml", many), repo)
    levels = _entry() + LEVEL * (holdings_mod.MAX_LEVELS_PER_HOLDING + 1)
    with pytest.raises(HoldingsError, match="levels"):
        _load(write_holdings_toml(outside / "b.toml", levels), repo)


@pytest.mark.parametrize("body", ["x = " + "[" * 5000 + "]" * 5000, "a = " + "{b = " * 400 + "1" + "}" * 400])
def test_hostile_nesting_is_a_holdings_error_not_a_crash(outside, repo, body):
    path = write_holdings_toml(outside / "holdings.toml", body)

    with pytest.raises(HoldingsError):
        _load(path, repo)


def test_invalid_utf8_is_a_holdings_error(outside, repo):
    path = outside / "holdings.toml"
    path.write_bytes(b"\xff\xfe\x00")
    path.chmod(0o600)

    with pytest.raises(HoldingsError):
        _load(path, repo)


def test_the_default_today_is_the_vietnam_date():
    import inspect

    assert "ict_now" in inspect.getsource(holdings_mod.load_holdings) and "date.today" not in inspect.getsource(holdings_mod)


def test_the_ticker_pattern_equals_the_feed_parsers():
    from app.services.company_feed import fetch  # the test may import the feed; the package may not

    assert holdings_mod.TICKER_PATTERN.pattern == fetch._TICKER.pattern


# --- task 2.3: holdings never reach a database or the API --------------------------------------

def test_no_brief_module_imports_a_database_or_a_web_framework():
    banned = {"sqlite3", "fastapi", "starlette", "app.api"}
    package = BACKEND / "app" / "services" / "brief"
    offenders = []
    for path in package.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [alias.name for alias in node.names] if isinstance(node, ast.Import)
                else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            )
            offenders += [f"{path.name}: {n}" for n in names if any(n == b or n.startswith(b + ".") for b in banned)]
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.db"):
                allowed = {"app.db": {"connection"}, "app.db.connection": {"open_readonly"}}  # a read-only opener only
                if {a.name for a in node.names} - allowed.get(node.module, set()):
                    offenders.append(f"{path.name}: from {node.module} import {[a.name for a in node.names]}")
            if isinstance(node, ast.Import):
                offenders += [f"{path.name}: {a.name}" for a in node.names if a.name.startswith("app.db")]

    assert offenders == []


def test_no_route_refers_to_holdings_or_the_brief():
    from app.main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        module = getattr(getattr(route, "endpoint", None), "__module__", "")
        assert not re.search(r"holding|brief", path, re.I), path
        assert not module.startswith("app.services.brief"), module
    api_sources = "".join(p.read_text(encoding="utf-8") for p in (BACKEND / "app" / "api").rglob("*.py"))
    assert "services.brief" not in api_sources and "holdings.toml" not in api_sources
