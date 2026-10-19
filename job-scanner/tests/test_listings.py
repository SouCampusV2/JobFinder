"""What each Jobs tab actually contains, and in what order. These queries decide
what the user sees; a wrong filter hides real matches without any error."""

THRESHOLD = 60


async def test_all_tab_hides_applied_jobs(db, add_job):
    await add_job(score=80, external_id="a")
    await add_job(score=80, applied=1, external_id="b")

    assert len(await db.list_jobs(applied=0)) == 1
    assert len(await db.list_jobs(applied=1)) == 1


async def test_strong_tab_includes_pinned_regardless_of_score(db, add_job):
    await add_job(score=90, external_id="high")
    await add_job(score=10, pinned=1, external_id="pin")
    await add_job(score=10, external_id="low")

    strong = await db.list_strong_jobs(THRESHOLD)

    titles = {j["external_id"] for j in strong}
    assert titles == {"high", "pin"}
    assert await db.count_strong_jobs(THRESHOLD) == 2


async def test_strong_tab_hides_applied(db, add_job):
    await add_job(score=90, applied=1, external_id="done")
    assert await db.list_strong_jobs(THRESHOLD) == []


async def test_lists_are_newest_first(db, add_job):
    first = await add_job(score=90, external_id="1")
    second = await add_job(score=10, external_id="2")
    third = await add_job(score=50, external_id="3")

    ids = [j["id"] for j in await db.list_jobs(applied=0)]

    assert ids == [third, second, first], "score must not drive the order"


async def test_limit_keeps_the_newest_not_the_best(db, add_job):
    old_high = await add_job(score=99, external_id="old")
    new_low = await add_job(score=5, external_id="new")

    rows = await db.list_jobs(applied=0, limit=1)

    assert [r["id"] for r in rows] == [new_low], f"limit dropped the newest row (kept {old_high})"


async def test_applied_tab_is_ordered_by_when_you_applied(db, add_job):
    first = await add_job(score=70, external_id="1")
    second = await add_job(score=70, external_id="2")
    # Apply to the OLDER job last - it must then come first.
    await db.set_applied(second, 1)
    await db.set_applied(first, 1)

    ids = [j["id"] for j in await db.list_jobs(applied=1, order="applied")]

    assert ids[0] == first


async def test_favorites_survive_being_applied(db, add_job):
    job_id = await add_job(score=70, favorite=1, applied=1, external_id="f")
    assert [j["id"] for j in await db.list_favorites()] == [job_id]


async def test_counts_match_the_lists_they_label(db, add_job):
    await add_job(score=90, external_id="a")
    await add_job(score=20, external_id="b")
    await add_job(score=90, applied=1, external_id="c")

    assert await db.count_jobs(applied=0) == len(await db.list_jobs(applied=0))
    assert await db.count_jobs(applied=1) == len(await db.list_jobs(applied=1))
    assert await db.count_strong_jobs(THRESHOLD) == len(await db.list_strong_jobs(THRESHOLD))


async def test_delete_removes_the_job_and_its_assets(db, add_job):
    job_id = await add_job(score=70, external_id="d")
    await db.save_asset(job_id, "cover_letter", "text")

    await db.delete_job(job_id)

    assert await db.get_job(job_id) is None
    assert await db.get_assets(job_id) == {}


async def test_applied_toggle_records_and_clears_the_timestamp(db, add_job):
    job_id = await add_job(score=70, external_id="t")

    await db.set_applied(job_id, 1)
    assert (await db.get_job(job_id))["applied_at"] is not None

    await db.set_applied(job_id, 0)
    assert (await db.get_job(job_id))["applied_at"] is None
