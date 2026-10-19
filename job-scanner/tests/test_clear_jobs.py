"""`clear_jobs` deletes in bulk - the highest-blast-radius function in the app.

The first test is a regression guard for a shipped bug: "Clear results" on the
Jobs page wiped the Applied tab, destroying application history that cannot be
recovered by re-scanning.
"""


async def test_clear_never_touches_applied_history(db, add_job):
    """THE regression: clearing a results list must not erase what you applied to."""
    applied = await add_job(score=90, applied=1, external_id="a")
    junk = await add_job(score=90, external_id="b")

    removed = await db.clear_jobs()

    assert removed == 1
    assert await db.get_job(applied) is not None, "applied job was deleted"
    assert await db.get_job(junk) is None


async def test_clear_keeps_saved_and_pinned(db, add_job):
    saved = await add_job(score=70, favorite=1, external_id="s")
    pinned = await add_job(score=20, pinned=1, external_id="p")
    plain = await add_job(score=70, external_id="x")

    removed = await db.clear_jobs()

    assert removed == 1
    assert await db.get_job(saved) is not None
    assert await db.get_job(pinned) is not None
    assert await db.get_job(plain) is None


async def test_clear_strong_tab_only_removes_at_or_above_threshold(db, add_job):
    strong = await add_job(score=80, external_id="hi")
    weak = await add_job(score=30, external_id="lo")

    removed = await db.clear_jobs(min_score=60)

    assert removed == 1
    assert await db.get_job(strong) is None
    assert await db.get_job(weak) is not None, "below-threshold job cleared from the wrong tab"


async def test_clear_all_tab_also_removes_unscored(db, add_job):
    """The All tab lists unscored jobs, so clearing it must empty them too -
    otherwise the list stays full after 'Clear results'."""
    unscored = await add_job(external_id="u")
    scored = await add_job(score=50, external_id="s")

    removed = await db.clear_jobs()

    assert removed == 2
    assert await db.get_job(unscored) is None
    assert await db.get_job(scored) is None


async def test_clear_scored_only_spares_unscored(db, add_job):
    unscored = await add_job(external_id="u")
    await add_job(score=50, external_id="s")

    removed = await db.clear_jobs(scored_only=True)

    assert removed == 1
    assert await db.get_job(unscored) is not None


async def test_clear_removes_generated_assets_too(db, add_job):
    """Assets are child rows; leaving them behind orphans them forever."""
    job_id = await add_job(score=90, external_id="a")
    await db.save_asset(job_id, "cover_letter", "Dear hiring manager")
    assert await db.get_assets(job_id) != {}

    await db.clear_jobs()

    assert await db.get_job(job_id) is None
    assert await db.get_assets(job_id) == {}


async def test_clear_on_empty_db_is_a_noop(db):
    assert await db.clear_jobs() == 0
