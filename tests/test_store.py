"""`oarena.store`: persistence, aggregates and the rating rebuild."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from oarena.bots import BotSource
from oarena.ratings import CI, Rater, Rating
from oarena.store import (
    SCHEMA_VERSION,
    Game,
    Record,
    Store,
    StoreBatchError,
    StoreBusyError,
    StoreConfigError,
    StoreImportError,
    StoreSchemaError,
)


def source(tmp_path: Path, name: str, *, snapshot: bool = False) -> BotSource:
    directory = tmp_path / ("snaps" if snapshot else "bots") / name
    return BotSource(
        name=name,
        dir=directory,
        entry=directory / "main.py",
        src_hash=f"hash-{name}",
    )


def game(a: str, b: str, winner: str | None, **kwargs: object) -> Game:
    return Game(a=a, b=b, map=str(kwargs.pop("map", "sprint")), winner=winner, **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def seeded(store: Store, tmp_path: Path) -> Store:
    initial = Rating(25.0, 25.0 / 3.0)
    for name in ("alpha", "beta", "gamma"):
        store.upsert_bot(source(tmp_path, name), initial)
    return store


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #


def test_database_is_created_with_the_expected_version(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "oarena.db"
    with Store(path) as st:
        version = st._conn.execute("PRAGMA user_version").fetchone()[0]
    assert path.is_file()
    assert version == SCHEMA_VERSION


def test_a_foreign_schema_fails_closed_without_losing_data(tmp_path: Path) -> None:
    path = tmp_path / "oarena.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ancient (x INT)")
    conn.execute("INSERT INTO ancient VALUES (42)")
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()

    with pytest.raises(StoreSchemaError, match="schema version 99"):
        Store(path)
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT x FROM ancient").fetchone()[0] == 42
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 99
    finally:
        conn.close()


def test_reopening_keeps_the_data(tmp_path: Path) -> None:
    path = tmp_path / "oarena.db"
    with Store(path) as st:
        st.upsert_bot(source(tmp_path, "alpha"), Rating(25.0, 8.0))
    with Store(path) as st:
        assert st.get_bot("alpha") is not None


def test_v1_upgrade_keeps_history(tmp_path: Path) -> None:
    """Removing snapshot support must not reset an existing user's ladder."""
    path = tmp_path / "oarena.db"
    with Store(path) as st:
        st.upsert_bot(source(tmp_path, "alpha"), Rating(25.0, 8.0))
        st.add_game(game("alpha", "beta", "alpha", rated=False))
        # Version 1 differs only by its now-unused ``bots.snapshot`` column;
        # preserve all compatible state while upgrading the marker.
        st._conn.execute("PRAGMA user_version = 1")
        st._conn.commit()

    with Store(path) as st:
        assert st.get_bot("alpha") is not None
        assert st.game_count() == 1
        assert st._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_v2_additive_upgrade_keeps_history_and_adds_import_provenance(tmp_path: Path) -> None:
    path = tmp_path / "oarena.db"
    with Store(path) as st:
        st.upsert_bot(source(tmp_path, "alpha"), Rating(25.0, 8.0))
        st.add_game(
            game("alpha", "beta", "a", rated=False, replay="1.replay26")
        )
        st._conn.execute("ALTER TABLE games DROP COLUMN fcode_version")
        st._conn.execute("ALTER TABLE games DROP COLUMN fcode_metadata_json")
        st._conn.execute("DROP TABLE game_imports")
        st._conn.execute("PRAGMA user_version = 2")
        st._conn.commit()

    with Store(path) as st:
        tables = {
            r[0] for r in st._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert st.get_bot("alpha") is not None
        assert st.game_count() == 1
        assert "game_imports" in tables
        assert "game_batches" in tables
        assert "league_meta" in tables
        columns = {
            row[1] for row in st._conn.execute("PRAGMA table_info(games)")
        }
        assert {
            "a_src_hash",
            "b_src_hash",
            "batch_ordinal",
            "fcode_version",
            "fcode_metadata_json",
        } <= columns
        migrated = st.list_games(limit=1)[0]
        assert migrated.replay == "1.replay26"
        assert migrated.fcode_version == ""
        assert migrated.fcode_metadata_json == ""
        assert st._conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_unreleased_v4_marker_fails_closed_without_losing_history(tmp_path: Path) -> None:
    path = tmp_path / "oarena.db"
    with Store(path) as st:
        st.upsert_bot(source(tmp_path, "alpha"), Rating(25.0, 8.0))
        st.add_game(game("alpha", "beta", "a", rated=False))
        st._conn.execute("PRAGMA user_version = 4")
        st._conn.commit()

    with pytest.raises(StoreSchemaError, match="schema version 4"):
        Store(path)
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# bots
# --------------------------------------------------------------------------- #


def test_upsert_returns_the_stored_row(store: Store, tmp_path: Path) -> None:
    bot = store.upsert_bot(source(tmp_path, "alpha"), Rating(25.0, 8.0))

    assert bot.name == "alpha"
    assert bot.dir == str(tmp_path / "bots" / "alpha")
    assert bot.entry == str(tmp_path / "bots" / "alpha" / "main.py")
    assert bot.active is True and bot.broken is False
    assert bot.rating == Rating(25.0, 8.0)
    assert bot.created and bot.updated


def test_upsert_is_idempotent_and_keeps_the_rating(store: Store, tmp_path: Path) -> None:
    src = source(tmp_path, "alpha")
    store.upsert_bot(src, Rating(25.0, 8.0))
    store.set_rating("alpha", Rating(31.0, 2.0))

    again = store.upsert_bot(src, Rating(25.0, 8.0))

    assert again.rating == Rating(31.0, 2.0)
    assert len(store.bots()) == 1


def test_bots_filters(seeded: Store) -> None:
    seeded.set_active("beta", False)
    seeded.set_broken("gamma", True, "ImportError")

    assert [b.name for b in seeded.bots()] == ["alpha", "beta", "gamma"]
    assert [b.name for b in seeded.bots(active_only=True)] == ["alpha", "gamma"]
    assert [b.name for b in seeded.bots(playable_only=True)] == ["alpha", "gamma"]
    assert seeded.get_bot("gamma").playable is True  # type: ignore[union-attr]


def test_set_broken_clears_the_reason_when_fixed(seeded: Store) -> None:
    seeded.set_broken("alpha", True, "ImportError: boom")
    assert seeded.get_bot("alpha").broken_reason == "ImportError: boom"  # type: ignore[union-attr]
    seeded.set_broken("alpha", False)
    bot = seeded.get_bot("alpha")
    assert bot is not None and bot.broken is False and bot.broken_reason == ""


def test_set_note_and_paths(seeded: Store) -> None:
    seeded.set_note("alpha", "the incumbent")
    seeded.set_paths("alpha", "/new/dir", "/new/dir/main.py")

    bot = seeded.get_bot("alpha")
    assert bot is not None
    assert bot.note == "the incumbent"
    assert (bot.dir, bot.entry) == ("/new/dir", "/new/dir/main.py")


def test_set_hash_records_a_version(seeded: Store) -> None:
    seeded.set_hash("alpha", "aaa")
    seeded.set_hash("alpha", "bbb")

    versions = seeded.versions("alpha")
    assert [v[1] for v in versions] == ["bbb", "aaa"]  # newest first
    assert seeded.get_bot("alpha").src_hash == "bbb"  # type: ignore[union-attr]


def test_latest_versions_returns_one_latest_source_row_per_bot(seeded: Store) -> None:
    seeded.set_hash("alpha", "aaa")
    seeded.set_hash("beta", "bbb")
    seeded.set_hash("alpha", "aaa-2")

    latest = seeded.latest_versions()

    assert set(latest) == {"alpha", "beta"}
    assert latest["alpha"][0] > latest["beta"][0]
    assert latest["alpha"][1]
    assert "gamma" not in latest


def test_get_bot_of_an_unknown_name_is_none(store: Store) -> None:
    assert store.get_bot("nobody") is None


def test_delete_bot_removes_its_games_and_versions(seeded: Store) -> None:
    seeded.set_hash("alpha", "aaa")
    seeded.add_game(game("alpha", "beta", "a"))
    seeded.add_game(game("beta", "gamma", "b"))

    seeded.delete_bot("alpha")

    assert seeded.get_bot("alpha") is None
    assert seeded.versions("alpha") == []
    assert [(g.a, g.b) for g in seeded.list_games()] == [("beta", "gamma")]


# --------------------------------------------------------------------------- #
# games
# --------------------------------------------------------------------------- #


def test_add_game_assigns_an_id_and_a_timestamp(seeded: Store) -> None:
    g = game("alpha", "beta", "a")
    gid = seeded.add_game(g)

    assert gid > 0 and g.id == gid
    assert g.ts

    stored = seeded.get_game(gid)
    assert stored is not None and stored.id == gid


def test_game_round_trips_every_column(seeded: Store) -> None:
    metadata_json = json.dumps(
        {
            "metadata_version": 1,
            "version": "2.3.3",
            "game_constants": {"MAX_TURNS": 1000},
            "enums": {},
            "direction_deltas": {},
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    original = Game(
        a="alpha", b="beta", a_src_hash="hash-alpha", b_src_hash="hash-beta",
        fcode_version="2.3.3", fcode_metadata_json=metadata_json,
        map="duel", seed=17, rated=True, status="ok",
        winner="b", win_condition="core_destroyed", turns=812, duration_ms=4321,
        resign_message="out of ideas", error="", a_titanium=1, a_mined=2,
        a_units=3, a_buildings=4, a_errors=5, b_titanium=6, b_mined=7,
        b_units=8, b_buildings=9, b_errors=10, a_mu_before=25.0,
        a_sigma_before=8.0, a_mu_after=26.0, a_sigma_after=7.5,
        b_mu_before=25.0, b_sigma_before=8.0, b_mu_after=24.0,
        b_sigma_after=7.5, replay="1.replay26", log="1.log", tag="match",
        batch_ordinal=None,
    )
    gid = seeded.add_game(original)
    stored = seeded.get_game(gid)

    assert stored is not None
    for field in vars(original):
        assert getattr(stored, field) == getattr(original, field), field


def test_get_game_of_an_unknown_id_is_none(store: Store) -> None:
    assert store.get_game(999) is None


def test_list_games_is_newest_first_and_respects_limit(seeded: Store) -> None:
    ids = [seeded.add_game(game("alpha", "beta", "a")) for _ in range(5)]
    listed = seeded.list_games(limit=3)

    assert [g.id for g in listed] == list(reversed(ids))[:3]


def test_list_games_filters(seeded: Store) -> None:
    seeded.add_game(game("alpha", "beta", "a", map="sprint"))
    seeded.add_game(game("beta", "gamma", "b", map="duel"))
    seeded.add_game(game("alpha", "gamma", None, map="duel", status="timeout"))
    seeded.add_game(game("alpha", "gamma", "a", map="duel", rated=False))
    seeded.add_game(game("alpha", "beta", "b", map="sprint", a_errors=1))

    assert len(seeded.list_games(bot="alpha")) == 4
    assert len(seeded.list_games(map="duel")) == 3
    assert len(seeded.list_games(bot="alpha", opponent="beta")) == 2
    assert len(seeded.list_games(status="timeout")) == 1
    assert len(seeded.list_games(status="failed")) == 2
    assert len(seeded.list_games(rated_only=True)) == 4


def test_list_games_before_id_is_a_cursor(seeded: Store) -> None:
    ids = [seeded.add_game(game("alpha", "beta", "a")) for _ in range(5)]
    page = seeded.list_games(limit=2, before_id=ids[3])
    assert [g.id for g in page] == [ids[2], ids[1]]


def test_list_games_after_is_a_forward_cursor_and_filters_tag(seeded: Store) -> None:
    first = seeded.add_game(game("alpha", "beta", "a", tag="one"))
    second = seeded.add_game(game("alpha", "beta", "b", tag="two"))
    third = seeded.add_game(game("beta", "alpha", "a", tag="one"))

    assert [g.id for g in seeded.list_games_after(first)] == [second, third]
    assert [g.id for g in seeded.list_games_after(0, limit=1)] == [first]
    assert [g.id for g in seeded.list_games_after(first, tag="one")] == [third]


def test_game_count(seeded: Store) -> None:
    assert seeded.game_count() == 0
    seeded.add_game(game("alpha", "beta", "a"))
    assert seeded.game_count() == 1


def test_game_count_and_listing_can_select_one_tag(seeded: Store) -> None:
    seeded.add_game(game("alpha", "beta", "a", tag="one"))
    seeded.add_game(game("alpha", "beta", "b", tag="two"))
    seeded.add_game(game("beta", "alpha", "a", tag="one"))

    assert seeded.game_count(tag="one") == 2
    assert {g.tag for g in seeded.list_games(tag="one")} == {"one"}


def test_list_batch_games_limits_after_ordering_by_planned_ordinal(
    seeded: Store, rater: Rater
) -> None:
    tag = "web-match-plan-order"
    seeded.reserve_batch(tag, mode="match", requested_games=501)
    for ordinal in range(500, -1, -1):
        seeded.record_game(
            game(
                "alpha",
                "beta",
                "a",
                rated=False,
                tag=tag,
                batch_ordinal=ordinal,
                a_src_hash="hash-alpha",
                b_src_hash="hash-beta",
            ),
            rater,
        )

    games = seeded.list_batch_games(tag, limit=500)

    assert len(games) == 500
    assert [entry.batch_ordinal for entry in games] == list(range(500))
    assert games[0].id > games[-1].id


def test_writer_lease_blocks_a_second_store_but_not_reads(
    seeded: Store, tmp_path: Path
) -> None:
    other = Store(seeded.path)
    try:
        seeded.writer_lock.acquire("test run")
        assert other.get_bot("alpha") is not None
        with pytest.raises(StoreBusyError, match="another oarena writer"):
            other.set_note("alpha", "must not race")
    finally:
        if seeded.writer_lock.held:
            seeded.writer_lock.release()
        other.close()


def test_batch_is_unique_and_game_plus_ratings_roll_back_together(
    seeded: Store, rater: Rater
) -> None:
    seeded.reserve_batch("codex_gate_v1", mode="match", requested_games=2)
    first = game(
        "alpha",
        "beta",
        "a",
        tag="codex_gate_v1",
        batch_ordinal=0,
        a_src_hash="hash-alpha",
        b_src_hash="hash-beta",
    )
    seeded.record_game(first, rater)
    after_first = {
        name: seeded.get_bot(name).rating  # type: ignore[union-attr]
        for name in ("alpha", "beta")
    }

    duplicate = game(
        "alpha",
        "beta",
        "b",
        tag="codex_gate_v1",
        batch_ordinal=0,
        a_src_hash="hash-alpha",
        b_src_hash="hash-beta",
    )
    with pytest.raises(sqlite3.IntegrityError):
        seeded.record_game(duplicate, rater)

    assert seeded.game_count(tag="codex_gate_v1") == 1
    assert {
        name: seeded.get_bot(name).rating  # type: ignore[union-attr]
        for name in ("alpha", "beta")
    } == after_first
    seeded.finish_batch("codex_gate_v1", status="completed")
    assert seeded.batch("codex_gate_v1")["status"] == "aborted"  # type: ignore[index]
    with pytest.raises(StoreBatchError, match="already reserved"):
        seeded.reserve_batch("codex_gate_v1", mode="match", requested_games=2)


@pytest.mark.parametrize("rated", [True, False])
def test_tagged_game_hashes_must_match_current_bots_transactionally(
    seeded: Store, rater: Rater, rated: bool
) -> None:
    seeded.reserve_batch("codex_hash_gate_v1", mode="match", requested_games=1)
    before = {
        name: seeded.get_bot(name).rating  # type: ignore[union-attr]
        for name in ("alpha", "beta")
    }
    mismatched = game(
        "alpha",
        "beta",
        "a",
        rated=rated,
        tag="codex_hash_gate_v1",
        batch_ordinal=0,
        a_src_hash="stale-alpha",
        b_src_hash="hash-beta",
    )

    with pytest.raises(StoreBatchError, match="source hash.*league has"):
        seeded.record_game(mismatched, rater)

    assert seeded.game_count(tag="codex_hash_gate_v1") == 0
    assert seeded.batch("codex_hash_gate_v1")["played_games"] == 0  # type: ignore[index]
    assert {
        name: seeded.get_bot(name).rating  # type: ignore[union-attr]
        for name in ("alpha", "beta")
    } == before


def test_rating_configuration_is_persisted_and_must_match(
    seeded: Store, rater: Rater
) -> None:
    from oarena.config import TrueSkillConfig

    seeded.ensure_rating_config(TrueSkillConfig())
    seeded.ensure_rating_config(TrueSkillConfig())
    with pytest.raises(StoreConfigError, match="do not match"):
        seeded.ensure_rating_config(
            TrueSkillConfig(mu=30.0, sigma=10.0, beta=5.0)
        )


# --------------------------------------------------------------------------- #
# database imports
# --------------------------------------------------------------------------- #


def _source_league(tmp_path: Path, rater: Rater) -> tuple[Store, Path]:
    state = tmp_path / "source" / ".oarena"
    source_store = Store(state / "oarena.db")
    for name in ("alpha", "beta"):
        source_store.upsert_bot(source(tmp_path, name), rater.initial())
    return source_store, state


def test_rated_database_import_is_resumable_and_copies_artifacts(
    seeded: Store, tmp_path: Path, rater: Rater
) -> None:
    source_store, source_state = _source_league(tmp_path, rater)
    replay_dir = tmp_path / "destination" / "replays"
    log_dir = tmp_path / "destination" / "logs"
    try:
        (source_state / "replays").mkdir(parents=True)
        (source_state / "logs").mkdir(parents=True)
        (source_state / "replays" / "1.replay26").write_bytes(b"replay-one")
        (source_state / "logs" / "1.log").write_text("source log", encoding="utf-8")
        first = game(
            "alpha", "beta", "a", rated=True, seed=11, tag="calibration",
            replay="1.replay26", log="1.log", turns=123,
            fcode_version="2.3.3",
            fcode_metadata_json=(
                '{"direction_deltas":{},"enums":{},"game_constants":{},'
                '"metadata_version":1,"version":"2.3.3"}'
            ),
        )
        source_store.add_game(first)
        source_store.add_game(game("alpha", "beta", "b", rated=False, seed=12))
        source_store.add_game(game("beta", "alpha", "b", rated=True, seed=13))
        participant_before = Rating(31.5, 6.25)
        unrelated_before = Rating(17.0, 7.9)
        seeded.set_rating("alpha", participant_before)
        seeded.set_rating("gamma", unrelated_before)

        cutoff = seeded.import_rated_games(
            source_store.path,
            source_key="calibration-v1",
            through=1,
            rater=rater,
            replay_dir=replay_dir,
            log_dir=log_dir,
        )
        assert (cutoff.selected, cutoff.imported, cutoff.skipped) == (1, 1, 0)
        imported = seeded.list_games(limit=1)[0]
        assert (imported.seed, imported.tag, imported.turns) == (11, "calibration", 123)
        assert imported.fcode_version == first.fcode_version
        assert imported.fcode_metadata_json == first.fcode_metadata_json
        assert (replay_dir / imported.replay).read_bytes() == b"replay-one"
        assert (log_dir / imported.log).read_text(encoding="utf-8") == "source log"
        expected_alpha, _expected_beta = rater.update(
            participant_before, rater.initial(), "a"
        )
        assert seeded.get_bot("alpha").rating == expected_alpha  # type: ignore[union-attr]
        assert seeded.get_bot("gamma").rating == unrelated_before  # type: ignore[union-attr]
        assert imported.a_mu_before == pytest.approx(participant_before.mu)
        assert imported.a_sigma_before == pytest.approx(participant_before.sigma)
        assert imported.a_mu_after == pytest.approx(expected_alpha.mu)

        resumed = seeded.import_rated_games(
            source_store.path,
            source_key="calibration-v1",
            through=3,
            rater=rater,
            replay_dir=replay_dir,
            log_dir=log_dir,
        )
        assert (resumed.selected, resumed.imported, resumed.skipped) == (2, 1, 1)
        again = seeded.import_rated_games(
            source_store.path,
            source_key="calibration-v1",
            through=3,
            rater=rater,
            replay_dir=replay_dir,
            log_dir=log_dir,
        )
        assert (again.selected, again.imported, again.skipped) == (2, 0, 2)
        assert seeded.game_count() == 2
        assert seeded.get_bot("gamma").rating == unrelated_before  # type: ignore[union-attr]
    finally:
        source_store.close()


def test_database_import_accepts_a_pre_provenance_v2_source(
    seeded: Store, tmp_path: Path, rater: Rater
) -> None:
    source_store, _source_state = _source_league(tmp_path, rater)
    try:
        source_store.add_game(game("alpha", "beta", "a", rated=True, seed=99))
        source_store._conn.execute("DROP INDEX idx_games_batch_ordinal")
        for column in (
            "a_src_hash",
            "b_src_hash",
            "batch_ordinal",
            "fcode_version",
            "fcode_metadata_json",
        ):
            source_store._conn.execute(f"ALTER TABLE games DROP COLUMN {column}")
        source_store._conn.execute("PRAGMA user_version = 2")
        source_store._conn.commit()

        report = seeded.import_rated_games(
            source_store.path,
            source_key="legacy-v2",
            rater=rater,
            replay_dir=tmp_path / "destination" / "replays",
            log_dir=tmp_path / "destination" / "logs",
        )

        assert report.imported == 1
        imported = seeded.list_games(limit=1)[0]
        assert imported.a_src_hash == "hash-alpha"
        assert imported.b_src_hash == "hash-beta"
        assert imported.batch_ordinal is None
        assert imported.fcode_version == ""
        assert imported.fcode_metadata_json == ""

        source_path = source_store.path
        source_store.close()
        source_store = Store(source_path)  # additive migration fills blank provenance
        resumed = seeded.import_rated_games(
            source_store.path,
            source_key="legacy-v2",
            rater=rater,
            replay_dir=tmp_path / "destination" / "replays",
            log_dir=tmp_path / "destination" / "logs",
        )
        assert (resumed.imported, resumed.skipped) == (0, 1)
    finally:
        source_store.close()


def test_database_import_keeps_tag_only_as_a_non_batch_label(
    seeded: Store, tmp_path: Path, rater: Rater
) -> None:
    source_store, _source_state = _source_league(tmp_path, rater)
    try:
        source_store.reserve_batch("source_gate_v1", mode="match", requested_games=1)
        source_store.record_game(
            game(
                "alpha",
                "beta",
                "a",
                rated=True,
                tag="source_gate_v1",
                batch_ordinal=0,
                a_src_hash="hash-alpha",
                b_src_hash="hash-beta",
            ),
            rater,
        )
        source_store.finish_batch("source_gate_v1", status="completed")

        report = seeded.import_rated_games(
            source_store.path,
            source_key="modern-batch",
            rater=rater,
            replay_dir=tmp_path / "destination" / "replays",
            log_dir=tmp_path / "destination" / "logs",
        )

        assert report.imported == 1
        imported = seeded.list_games(limit=1)[0]
        assert imported.tag == "source_gate_v1"
        assert imported.batch_ordinal is None
        assert seeded.batch("source_gate_v1") is None
        with pytest.raises(StoreBatchError, match="legacy game history"):
            seeded.reserve_batch("source_gate_v1", mode="match", requested_games=1)
    finally:
        source_store.close()


def test_database_import_rejects_a_destination_native_batch_tag_collision(
    seeded: Store, tmp_path: Path, rater: Rater
) -> None:
    source_store, _source_state = _source_league(tmp_path, rater)
    try:
        source_store.reserve_batch("root_gate_v1", mode="match", requested_games=1)
        source_store.record_game(
            game(
                "alpha",
                "beta",
                "a",
                rated=True,
                tag="root_gate_v1",
                batch_ordinal=0,
                a_src_hash="hash-alpha",
                b_src_hash="hash-beta",
            ),
            rater,
        )
        source_store.finish_batch("root_gate_v1", status="completed")
        seeded.reserve_batch("root_gate_v1", mode="match", requested_games=0)
        seeded.finish_batch("root_gate_v1", status="completed")

        with pytest.raises(StoreImportError, match="destination-native batch"):
            seeded.import_rated_games(
                source_store.path,
                source_key="batch-tag-collision",
                rater=rater,
                replay_dir=tmp_path / "destination" / "replays",
                log_dir=tmp_path / "destination" / "logs",
            )

        assert seeded.game_count() == 0
        assert seeded.batch("root_gate_v1")["status"] == "completed"  # type: ignore[index]
    finally:
        source_store.close()


@pytest.mark.parametrize("mutation", ["changed", "missing"])
def test_database_import_rejects_a_rewritten_source_history(
    seeded: Store, tmp_path: Path, rater: Rater, mutation: str
) -> None:
    source_store, _source_state = _source_league(tmp_path, rater)
    try:
        source_store.add_game(game("alpha", "beta", "a", rated=True))
        seeded.import_rated_games(
            source_store.path,
            source_key="immutable-history",
            rater=rater,
            replay_dir=tmp_path / "destination" / "replays",
            log_dir=tmp_path / "destination" / "logs",
        )
        if mutation == "changed":
            source_store._conn.execute("UPDATE games SET winner = 'b' WHERE id = 1")
        else:
            source_store._conn.execute("DELETE FROM games WHERE id = 1")
        source_store._conn.commit()

        with pytest.raises(StoreImportError, match="changed|now missing"):
            seeded.import_rated_games(
                source_store.path,
                source_key="immutable-history",
                rater=rater,
                replay_dir=tmp_path / "destination" / "replays",
                log_dir=tmp_path / "destination" / "logs",
            )
        assert seeded.game_count() == 1
    finally:
        source_store.close()


def test_database_import_rejects_same_database_and_invalid_rated_outcome(
    seeded: Store, tmp_path: Path, rater: Rater
) -> None:
    with pytest.raises(StoreImportError, match="same file"):
        seeded.import_rated_games(
            seeded.path,
            source_key="self",
            rater=rater,
            replay_dir=tmp_path / "replays",
            log_dir=tmp_path / "logs",
        )

    source_store, _source_state = _source_league(tmp_path, rater)
    try:
        source_store.add_game(
            game("alpha", "beta", None, rated=True, status="timeout")
        )
        with pytest.raises(StoreImportError, match="unsupported status"):
            seeded.import_rated_games(
                source_store.path,
                source_key="invalid",
                rater=rater,
                replay_dir=tmp_path / "replays",
                log_dir=tmp_path / "logs",
            )
    finally:
        source_store.close()


def test_database_import_dry_run_and_hash_mismatch_do_not_write(
    seeded: Store, tmp_path: Path, rater: Rater
) -> None:
    source_store, source_state = _source_league(tmp_path, rater)
    replay_dir = tmp_path / "destination" / "replays"
    log_dir = tmp_path / "destination" / "logs"
    try:
        source_store.add_game(game("alpha", "beta", "a", rated=True))
        preview = seeded.import_rated_games(
            source_store.path,
            source_key="preview",
            rater=rater,
            replay_dir=replay_dir,
            log_dir=log_dir,
            source_state_dir=source_state,
            dry_run=True,
        )
        assert preview.dry_run and preview.imported == 0 and preview.selected == 1
        assert seeded.game_count() == 0

        seeded.set_hash("alpha", "different")
        with pytest.raises(StoreImportError, match="source hash mismatch"):
            seeded.import_rated_games(
                source_store.path,
                source_key="preview",
                rater=rater,
                replay_dir=replay_dir,
                log_dir=log_dir,
            )
        assert seeded.game_count() == 0
    finally:
        source_store.close()


def test_all_skipped_import_does_not_claim_current_hashes_still_match(
    seeded: Store, tmp_path: Path, rater: Rater
) -> None:
    source_store, _source_state = _source_league(tmp_path, rater)
    try:
        source_store.add_game(game("alpha", "beta", "a", rated=True))
        seeded.import_rated_games(
            source_store.path,
            source_key="already-done",
            rater=rater,
            replay_dir=tmp_path / "destination" / "replays",
            log_dir=tmp_path / "destination" / "logs",
        )
        seeded.set_hash("alpha", "new-alpha-version")

        report = seeded.import_rated_games(
            source_store.path,
            source_key="already-done",
            rater=rater,
            replay_dir=tmp_path / "destination" / "replays",
            log_dir=tmp_path / "destination" / "logs",
            dry_run=True,
        )

        assert (report.would_import, report.skipped) == (0, 1)
        assert report.bots == ("alpha", "beta")  # referenced, not asserted-current
    finally:
        source_store.close()


def test_database_import_rolls_back_if_an_artifact_destination_exists(
    seeded: Store, tmp_path: Path, rater: Rater
) -> None:
    source_store, source_state = _source_league(tmp_path, rater)
    replay_dir = tmp_path / "destination" / "replays"
    log_dir = tmp_path / "destination" / "logs"
    try:
        (source_state / "replays").mkdir(parents=True)
        (source_state / "replays" / "1.replay26").write_bytes(b"new")
        source_store.add_game(
            game("alpha", "beta", "a", rated=True, replay="1.replay26")
        )
        replay_dir.mkdir(parents=True)
        collision = replay_dir / "1.replay26"
        collision.write_bytes(b"keep")

        with pytest.raises(StoreImportError, match="artifact import failed"):
            seeded.import_rated_games(
                source_store.path,
                source_key="collision",
                rater=rater,
                replay_dir=replay_dir,
                log_dir=log_dir,
            )

        assert seeded.game_count() == 0
        assert collision.read_bytes() == b"keep"
        assert (
            seeded._conn.execute(
                "SELECT COUNT(*) FROM game_imports WHERE source_key = 'collision'"
            ).fetchone()[0]
            == 0
        )
    finally:
        source_store.close()


# --------------------------------------------------------------------------- #
# aggregates
# --------------------------------------------------------------------------- #


def test_record_counts_from_the_bots_point_of_view(seeded: Store) -> None:
    seeded.add_game(game("alpha", "beta", "a"))  # alpha win
    seeded.add_game(game("beta", "alpha", "a"))  # alpha loss
    seeded.add_game(game("alpha", "beta", "draw"))
    seeded.add_game(game("alpha", "beta", None, status="timeout"))  # undecided

    rec = seeded.record("alpha")
    assert (rec.wins, rec.losses, rec.draws, rec.games) == (1, 1, 1, 3)
    assert rec.winrate == pytest.approx(0.5)
    assert rec.score == pytest.approx(1.5)


def test_record_can_be_restricted_to_rated_games(seeded: Store) -> None:
    seeded.add_game(game("alpha", "beta", "a", rated=True))
    seeded.add_game(game("beta", "alpha", "a", rated=False))
    seeded.add_game(game("alpha", "beta", "draw", rated=False))

    complete = seeded.record("alpha")
    rated = seeded.record("alpha", rated_only=True)

    assert (complete.wins, complete.losses, complete.draws, complete.games) == (1, 1, 1, 3)
    assert (rated.wins, rated.losses, rated.draws, rated.games) == (1, 0, 0, 1)
    assert rated.winrate == pytest.approx(1.0)


def test_version_scoped_ladder_aggregates_ignore_prior_source_hashes(seeded: Store) -> None:
    seeded.add_game(
        game(
            "alpha",
            "beta",
            "b",
            a_src_hash="old-alpha",
            b_src_hash="hash-beta",
            a_errors=4,
            ts="2026-01-01T00:00:00+00:00",
        )
    )
    seeded.add_game(
        game(
            "beta",
            "alpha",
            "b",
            a_src_hash="hash-beta",
            b_src_hash="hash-alpha",
            b_errors=1,
            ts="2026-01-02T00:00:00+00:00",
        )
    )

    lifetime = seeded.record("alpha")
    current = seeded.record("alpha", source_hash="hash-alpha")

    assert (lifetime.wins, lifetime.losses, lifetime.games) == (1, 1, 2)
    assert (current.wins, current.losses, current.games) == (1, 0, 1)
    assert seeded.error_count("alpha") == (2, 5)
    assert seeded.error_count("alpha", source_hash="hash-alpha") == (1, 1)
    assert seeded.last_played("alpha", source_hash="hash-alpha") == "2026-01-02T00:00:00+00:00"
    assert seeded.last_played("alpha", source_hash="missing") is None


def test_record_of_an_unplayed_bot(seeded: Store) -> None:
    rec = seeded.record("alpha")
    assert rec == Record()
    assert rec.winrate is None


def test_self_matches_carry_no_record(seeded: Store) -> None:
    seeded.add_game(game("alpha", "alpha", "a", rated=False))
    assert seeded.record("alpha").games == 0


def test_head_to_head_splits_by_opponent(seeded: Store) -> None:
    seeded.add_game(game("alpha", "beta", "a"))
    seeded.add_game(game("alpha", "beta", "a"))
    seeded.add_game(game("gamma", "alpha", "a"))

    h2h = seeded.head_to_head("alpha")
    assert set(h2h) == {"beta", "gamma"}
    assert (h2h["beta"].wins, h2h["beta"].losses) == (2, 0)
    assert (h2h["gamma"].wins, h2h["gamma"].losses) == (0, 1)


def test_matrix_is_symmetric(seeded: Store) -> None:
    seeded.add_game(game("alpha", "beta", "a"))
    seeded.add_game(game("beta", "alpha", "draw"))

    cells = seeded.matrix(["alpha", "beta", "gamma"])

    assert cells["alpha"]["beta"].wins == 1
    assert cells["beta"]["alpha"].losses == 1
    assert cells["alpha"]["beta"].draws == cells["beta"]["alpha"].draws == 1
    assert cells["alpha"]["beta"].games == cells["beta"]["alpha"].games == 2
    assert cells["alpha"]["gamma"] == Record()
    for name in ("alpha", "beta", "gamma"):
        assert set(cells[name]) == {"alpha", "beta", "gamma"}


def test_matrix_ignores_bots_outside_the_request(seeded: Store) -> None:
    seeded.add_game(game("alpha", "gamma", "a"))
    cells = seeded.matrix(["alpha", "beta"])
    assert cells["alpha"]["beta"] == Record()


def test_map_record(seeded: Store) -> None:
    seeded.add_game(game("alpha", "beta", "a", map="sprint"))
    seeded.add_game(game("alpha", "beta", "b", map="duel"))

    per_map = seeded.map_record("alpha")
    assert per_map["sprint"].wins == 1
    assert per_map["duel"].losses == 1


def test_pair_map_record_excludes_other_opponents(seeded: Store) -> None:
    seeded.add_game(game("alpha", "beta", "a", map="sprint"))
    seeded.add_game(game("beta", "alpha", "a", map="sprint"))
    seeded.add_game(game("alpha", "gamma", "a", map="sprint"))

    per_map = seeded.pair_map_record("alpha", "beta")
    assert per_map["sprint"].wins == 1
    assert per_map["sprint"].losses == 1
    assert per_map["sprint"].games == 2


def test_error_count_separates_games_from_tracebacks(seeded: Store) -> None:
    seeded.add_game(game("alpha", "beta", "a", a_errors=3, b_errors=1))
    seeded.add_game(game("beta", "alpha", "a", a_errors=5, b_errors=2))
    seeded.add_game(game("alpha", "beta", "a"))

    assert seeded.error_count("alpha") == (2, 5)
    assert seeded.error_count("beta") == (2, 6)
    assert seeded.error_count("gamma") == (0, 0)


def test_map_play_counts_includes_failed_games(seeded: Store) -> None:
    seeded.add_game(game("alpha", "beta", "a", map="sprint"))
    seeded.add_game(game("alpha", "beta", None, map="sprint", status="timeout"))
    seeded.add_game(game("alpha", "beta", "b", map="duel"))

    assert seeded.map_play_counts() == {"sprint": 2, "duel": 1}


def test_recent_crashes_returns_failures_and_raisers(seeded: Store) -> None:
    ok = seeded.add_game(game("alpha", "beta", "a"))
    crashed = seeded.add_game(game("alpha", "beta", None, status="loadfail_a"))
    raised = seeded.add_game(game("alpha", "beta", "b", a_errors=2))
    opponent_loadfail = seeded.add_game(game("alpha", "beta", None, status="loadfail_b"))
    engine_failure = seeded.add_game(game("alpha", "beta", None, status="engine_error"))
    both_failed = seeded.add_game(
        game("alpha", "beta", None, status="loadfail_both", a_errors=1, b_errors=1)
    )

    ids = [g.id for g in seeded.recent_crashes("alpha")]
    assert ids == [both_failed, raised, crashed]
    assert [g.id for g in seeded.recent_crashes("beta")] == [both_failed, opponent_loadfail]
    assert ok not in ids
    assert opponent_loadfail not in ids
    assert engine_failure not in ids


# --------------------------------------------------------------------------- #
# rating history
# --------------------------------------------------------------------------- #


def test_rating_history_is_oldest_first_with_a_starting_point(seeded: Store) -> None:
    first = seeded.add_game(
        game("alpha", "beta", "a", a_mu_before=25.0, a_sigma_before=8.0,
             a_mu_after=27.0, a_sigma_after=7.0)
    )
    second = seeded.add_game(
        game("beta", "alpha", "b", b_mu_before=27.0, b_sigma_before=7.0,
             b_mu_after=29.0, b_sigma_after=6.0)
    )

    history = seeded.rating_history("alpha")

    # Rating timelines share a global game axis.  The pre-game point belongs
    # immediately before the first game that changed this bot's rating.
    assert [p["game"] for p in history] == [first - 1, first, second]
    assert history[0]["mu"] == pytest.approx(25.0)
    assert history[-1]["mu"] == pytest.approx(29.0)
    assert history[-1]["score"] == pytest.approx(29.0 - CI * 6.0)
    assert [p["mu"] for p in history] == sorted(p["mu"] for p in history)


def test_rating_history_of_an_unplayed_bot_is_its_current_point(seeded: Store) -> None:
    history = seeded.rating_history("alpha")
    assert len(history) == 1
    assert history[0]["mu"] == pytest.approx(25.0)


def test_rating_history_of_an_unknown_bot_is_empty(store: Store) -> None:
    assert store.rating_history("nobody") == []


def test_rating_history_skips_unrated_games(seeded: Store) -> None:
    seeded.add_game(
        game("alpha", "beta", "a", rated=False, a_mu_before=25.0, a_sigma_before=8.0,
             a_mu_after=99.0, a_sigma_after=1.0)
    )
    seeded.add_game(
        game("alpha", "beta", "a", a_mu_before=25.0, a_sigma_before=8.0,
             a_mu_after=27.0, a_sigma_after=7.0)
    )
    # Database id 1 was consumed by an unrated attempt, but this is still the
    # league's first rated game and therefore occupies x=1, not x=2.
    assert [point["game"] for point in seeded.rating_history("alpha")] == [0, 1]


def test_rating_history_is_uncapped_unless_a_window_is_requested(seeded: Store) -> None:
    ids = [
        seeded.add_game(
            game(
                "alpha", "beta", "a", a_mu_before=25.0 + n, a_sigma_before=8.0,
                a_mu_after=26.0 + n, a_sigma_after=7.0,
            )
        )
        for n in range(3)
    ]

    assert [point["game"] for point in seeded.rating_history("alpha")] == [ids[0] - 1, *ids]
    assert [point["game"] for point in seeded.rating_history("alpha", limit=2)] == [ids[1] - 1, *ids[1:]]


# --------------------------------------------------------------------------- #
# recompute
# --------------------------------------------------------------------------- #


def test_recompute_reproduces_the_incremental_ratings(seeded: Store, rater: Rater) -> None:
    results = [
        ("alpha", "beta", "a"), ("beta", "gamma", "draw"), ("alpha", "gamma", "b"),
        ("gamma", "alpha", "a"), ("beta", "alpha", "b"), ("alpha", "beta", "draw"),
    ]
    live = {name: rater.initial() for name in ("alpha", "beta", "gamma")}
    for a, b, winner in results:
        before_a, before_b = live[a], live[b]
        after_a, after_b = rater.update(before_a, before_b, winner)
        live[a], live[b] = after_a, after_b
        seeded.add_game(game(a, b, winner))
    # Store the *wrong* ratings, exactly as a corrupted database would.
    for name in live:
        seeded.set_rating(name, Rating(1.0, 1.0))

    seeded.recompute(rater)

    for name, expected in live.items():
        stored = seeded.get_bot(name)
        assert stored is not None
        assert stored.mu == pytest.approx(expected.mu)
        assert stored.sigma == pytest.approx(expected.sigma)


def test_recompute_rewrites_the_per_game_columns(seeded: Store, rater: Rater) -> None:
    gid = seeded.add_game(game("alpha", "beta", "a"))
    seeded.recompute(rater)

    stored = seeded.get_game(gid)
    assert stored is not None
    assert stored.a_mu_before == pytest.approx(25.0)
    assert stored.a_mu_after is not None and stored.a_mu_after > 25.0
    assert stored.b_mu_after is not None and stored.b_mu_after < 25.0


def test_recompute_ignores_unrated_and_self_games(seeded: Store, rater: Rater) -> None:
    seeded.add_game(game("alpha", "beta", "a", rated=False))
    seeded.add_game(game("alpha", "alpha", "a"))

    seeded.recompute(rater)

    for name in ("alpha", "beta"):
        stored = seeded.get_bot(name)
        assert stored is not None
        assert stored.rating == rater.initial()


# --------------------------------------------------------------------------- #
# maintenance
# --------------------------------------------------------------------------- #


def test_reset_keeps_bots_by_default(seeded: Store, rater: Rater) -> None:
    seeded.add_game(game("alpha", "beta", "a"))
    seeded.set_rating("alpha", Rating(40.0, 1.0))
    seeded.set_broken("alpha", True, "boom")

    seeded.reset(keep_bots=True, rater=rater)

    assert seeded.game_count() == 0
    bot = seeded.get_bot("alpha")
    assert bot is not None
    assert bot.rating == rater.initial()
    assert bot.broken is False

    # A ladder reset starts a new global-game epoch rather than continuing the
    # deleted history's SQLite sequence.
    gid = seeded.add_game(game("alpha", "beta", "a"))
    assert gid == 1


def test_reset_all_drops_the_bots(seeded: Store) -> None:
    seeded.set_hash("alpha", "aaa")
    seeded.add_game(game("alpha", "beta", "a"))

    seeded.reset(keep_bots=False)

    assert seeded.bots() == []
    assert seeded.game_count() == 0
    assert seeded.versions("alpha") == []


def test_replay_and_log_files_are_listed_newest_first(seeded: Store) -> None:
    first = seeded.add_game(game("alpha", "beta", "a", replay="1.replay26", log="1.log"))
    second = seeded.add_game(game("alpha", "beta", "b", replay="2.replay26"))
    seeded.add_game(game("alpha", "beta", "a"))  # no files

    assert seeded.replay_files() == [(second, "2.replay26"), (first, "1.replay26")]
    assert seeded.log_files() == [(first, "1.log")]


def test_clear_replay_and_log(seeded: Store) -> None:
    gid = seeded.add_game(game("alpha", "beta", "a", replay="1.replay26", log="1.log"))
    seeded.clear_replay(gid)
    seeded.clear_log(gid)

    stored = seeded.get_game(gid)
    assert stored is not None and stored.replay == "" and stored.log == ""
    assert seeded.replay_files() == []


def test_set_files_attaches_names_after_insert(seeded: Store) -> None:
    gid = seeded.add_game(game("alpha", "beta", "a"))
    seeded.set_files(gid, f"{gid}.replay26", f"{gid}.log")

    stored = seeded.get_game(gid)
    assert stored is not None
    assert stored.replay == f"{gid}.replay26"
    assert stored.log == f"{gid}.log"


# --------------------------------------------------------------------------- #
# thread safety
# --------------------------------------------------------------------------- #


def test_writes_from_several_threads_all_land(seeded: Store) -> None:
    import threading

    def write() -> None:
        for _ in range(25):
            seeded.add_game(game("alpha", "beta", "a"))

    threads = [threading.Thread(target=write) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert seeded.game_count() == 100


def test_close_is_idempotent(tmp_path: Path) -> None:
    """A second close must be a no-op — shutdown paths call it from `finally:`."""
    store = Store(tmp_path / "s.db")
    store.close()
    store.close()  # must not raise sqlite3.ProgrammingError


def test_pair_counts_include_undecided_games(tmp_path: Path) -> None:
    """Crashes and timeouts still count as attempts.

    Matchmakers spread play by pair count; if a pairing that always fails stayed
    at zero it would look as attractive as a never-played pair and be selected
    forever.
    """
    store = Store(tmp_path / "s.db")
    initial = Rating(25.0, 25.0 / 3.0)
    for name in ("a", "b", "c"):
        store.upsert_bot(source(tmp_path, name), initial)

    for _ in range(5):
        store.add_game(game("a", "b", None, status="timeout", rated=0))
    store.add_game(game("a", "c", "a"))

    counts = store.pair_counts()
    assert counts[("a", "b")] == 5, "failed games must still count as attempts"
    assert counts[("a", "c")] == 1
    assert ("b", "c") not in counts
    # matrix() stays decided-only: a timeout carries no head-to-head signal.
    assert store.matrix(["a", "b"])["a"]["b"].games == 0
    store.close()
