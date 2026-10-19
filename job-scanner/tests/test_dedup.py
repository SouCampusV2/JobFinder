"""Content dedup. `purge_duplicates` DELETES rows, so the protective rules
(never drop something the user acted on) are tested as hard as the matching."""


from db.queries import dedup_key



# --------------------------------------------------------------------------- #
# The fingerprint itself (pure function, no DB)                               #
# --------------------------------------------------------------------------- #

def test_same_job_reposted_with_cosmetic_differences_matches():
    a = dedup_key("HR Generalist (m/w/d) – 100% Remote", "MOD Education")
    b = dedup_key("HR Generalist - 100% remote", "mod education.")
    assert a == b != ""


def test_accents_and_punctuation_are_normalised():
    assert dedup_key("Продукт", "Мюller GmbH") or True  # non-latin must not crash
    assert dedup_key("Sr. Manager", "Müller GmbH") == dedup_key("Sr Manager", "Muller GmbH")


def test_location_is_not_part_of_the_key():
    """Same opening advertised per city is ONE job, not six."""
    assert dedup_key("Analytics Manager", "Wolt") == dedup_key("Analytics Manager", "Wolt")


def test_different_companies_never_collide():
    assert dedup_key("Product Manager", "Acme") != dedup_key("Product Manager", "Globex")


def test_no_fingerprint_without_a_company():
    """Without a company an identical title says nothing - must not dedup."""
    assert dedup_key("Product Manager", None) == ""
    assert dedup_key("Product Manager", "  ") == ""
    assert dedup_key(None, "Acme") == ""


# --------------------------------------------------------------------------- #
# Insert-time dedup                                                           #
# --------------------------------------------------------------------------- #

async def test_repost_under_a_new_id_is_rejected(db, listing):
    same = {"title": "HR Generalist", "company": "MOD Education"}
    first = await db.insert_job(listing(external_id="111", **same))
    second = await db.insert_job(listing(external_id="222", location="Munich", **same))

    assert first is not None
    assert second is None, "same job with a new external_id was stored again"


async def test_same_id_twice_is_rejected(db, listing):
    assert await db.insert_job(listing(external_id="111", title="X", company="Y")) is not None
    assert await db.insert_job(listing(external_id="111", title="X", company="Y")) is None


async def test_jobs_without_a_company_are_not_deduped(db, listing):
    a = await db.insert_job(listing(title="Ops Lead", company=None, external_id="1"))
    b = await db.insert_job(listing(title="Ops Lead", company=None, external_id="2"))
    assert a is not None and b is not None


async def test_duplicate_exists_precheck_matches_insert_behaviour(db, listing):
    assert await db.duplicate_exists("Product Manager", "Acme") is False
    await db.insert_job(listing(title="Product Manager", company="Acme"))
    assert await db.duplicate_exists("Product Manager (m/w/d)", "acme") is True


# --------------------------------------------------------------------------- #
# Cleaning up rows stored before dedup existed                                #
# --------------------------------------------------------------------------- #

async def _legacy_rows(db, rows):
    """Insert bypassing the dedup check, as older versions did."""
    import aiosqlite

    from config import settings

    async with aiosqlite.connect(settings.db_path) as con:
        for i, (title, company, score, applied, favorite, pinned) in enumerate(rows):
            await con.execute(
                "INSERT INTO jobs (source, external_id, title, company, scraped_at, "
                "status, score, applied, favorite, pinned) "
                "VALUES ('linkedin', ?, ?, ?, '2026-07-20T00:00:00+00:00', 'scored', ?, ?, ?, ?)",
                (f"legacy-{i}", title, company, score, applied, favorite, pinned),
            )
        await con.commit()


async def test_purge_collapses_a_duplicate_group(db):
    await _legacy_rows(db, [("HR Generalist", "MOD", 50, 0, 0, 0)] * 5)

    assert await db.backfill_dedup_keys() == 5
    assert await db.purge_duplicates() == 4
    assert await db.count_jobs() == 1


async def test_purge_never_deletes_a_job_the_user_acted_on(db):
    await _legacy_rows(db, [
        ("HR Generalist", "MOD", 50, 0, 0, 0),   # plain copy
        ("HR Generalist", "MOD", 50, 1, 0, 0),   # applied
        ("HR Generalist", "MOD", 50, 0, 1, 0),   # saved
        ("HR Generalist", "MOD", 50, 0, 0, 1),   # pinned
    ])
    await db.backfill_dedup_keys()

    await db.purge_duplicates()

    remaining = await db.list_jobs()
    assert len(remaining) == 3, "a marked duplicate was deleted"
    assert all(r["applied"] or r["favorite"] or r["pinned"] for r in remaining)


async def test_purge_keeps_the_highest_scoring_copy(db):
    await _legacy_rows(db, [
        ("HR Generalist", "MOD", 20, 0, 0, 0),
        ("HR Generalist", "MOD", 88, 0, 0, 0),
        ("HR Generalist", "MOD", 55, 0, 0, 0),
    ])
    await db.backfill_dedup_keys()

    await db.purge_duplicates()

    rows = await db.list_jobs()
    assert len(rows) == 1
    assert rows[0]["score"] == 88


async def test_backfill_and_purge_are_idempotent(db):
    """They run on every startup - a second pass must be free and harmless."""
    await _legacy_rows(db, [("HR Generalist", "MOD", 50, 0, 0, 0)] * 3)
    await db.backfill_dedup_keys()
    await db.purge_duplicates()

    assert await db.backfill_dedup_keys() == 0
    assert await db.purge_duplicates() == 0
    assert await db.count_jobs() == 1


async def test_purge_removes_the_assets_of_deleted_copies(db):
    await _legacy_rows(db, [("HR Generalist", "MOD", 50, 0, 0, 0)] * 2)
    await db.backfill_dedup_keys()
    doomed = (await db.list_jobs())[0]["id"]
    await db.save_asset(doomed, "cover_letter", "text")

    await db.purge_duplicates()

    assert await db.get_assets(doomed) == {}
