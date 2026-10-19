"""The Statistic tab's numbers.

The tab is the only place the user sees how the funnel is doing, so a wrong
count here is worse than no tab at all.
"""

from __future__ import annotations


async def test_an_empty_database_reports_zeroes_not_a_crash(db):
    stats = await db.get_statistics(60)

    assert stats["scanned"] == 0
    assert stats["scored"] == 0
    assert stats["matches"] == 0
    assert stats["by_source"] == []
    assert stats["bands"] == []
    assert stats["first_seen"] is None


async def test_counts_follow_the_funnel(db, listing):
    ids = []
    for score in (5, 45, 65, 90):
        job_id = await db.insert_job(listing())
        await db.save_quick_score(job_id, score, "s", [])
        ids.append(job_id)
    unscored = await db.insert_job(listing())
    await db.set_applied(ids[3], True)
    await db.toggle_favorite(ids[2])

    stats = await db.get_statistics(60)

    assert stats["scanned"] == 5          # includes the unscored one
    assert stats["scored"] == 4
    assert stats["matches"] == 2          # 65 and 90
    assert stats["match80"] == 1
    assert stats["applied"] == 1
    assert stats["saved"] == 1
    assert unscored is not None


async def test_the_threshold_moves_the_match_count(db, listing):
    for score in (35, 55, 75):
        job_id = await db.insert_job(listing())
        await db.save_quick_score(job_id, score, "s", [])

    assert (await db.get_statistics(60))["matches"] == 1
    assert (await db.get_statistics(50))["matches"] == 2
    assert (await db.get_statistics(30))["matches"] == 3


async def test_sources_are_counted_separately_with_their_good_ones(db, listing):
    for source, score in (("linkedin", 90), ("linkedin", 10), ("remoteok", 70)):
        job_id = await db.insert_job(listing(source=source))
        await db.save_quick_score(job_id, score, "s", [])

    by_source = {r["source"]: r for r in (await db.get_statistics(60))["by_source"]}

    assert by_source["linkedin"]["n"] == 2
    assert by_source["linkedin"]["good"] == 1
    assert by_source["remoteok"]["good"] == 1


async def test_bands_split_scores_and_ignore_unscored_jobs(db, listing):
    for score in (5, 25, 45, 65, 85, 95):
        job_id = await db.insert_job(listing())
        await db.save_quick_score(job_id, score, "s", [])
    await db.insert_job(listing())        # never scored

    bands = {r["band"]: r["n"] for r in (await db.get_statistics(60))["bands"]}

    assert bands == {"0-19": 1, "20-39": 1, "40-59": 1, "60-79": 1, "80-100": 2}
    assert sum(bands.values()) == 6


async def test_applied_jobs_are_grouped_by_day(db, listing):
    for _ in range(3):
        job_id = await db.insert_job(listing())
        await db.set_applied(job_id, True)

    by_day = (await db.get_statistics(60))["applied_by_day"]

    assert len(by_day) == 1               # all applied today
    assert by_day[0]["n"] == 3
    assert len(by_day[0]["day"]) == 10    # YYYY-MM-DD, the template slices it
