from datetime import datetime

from sqlalchemy import select
from nonebot import get_driver
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import get_session

from ..models import ContestStatus, DragonContest

driver = get_driver()


def register_contest_start_job(contest_id: int, start_ts: int):
    scheduler.add_job(
        on_contest_start,
        trigger="date",
        run_date=datetime.fromtimestamp(start_ts),
        args=[contest_id],
        id=f"dragon_contest_start_{contest_id}",
        replace_existing=True,
    )


async def on_contest_start(contest_id: int):
    async with get_session() as sess:
        contest = await sess.get(DragonContest, contest_id)
        if not contest:
            return
        if contest.status == ContestStatus.RUNNING.value:
            return
        contest.status = ContestStatus.RUNNING.value
        sess.add(contest)
        try:
            await sess.commit()
        except Exception as e:
            await sess.rollback()
            logger.exception(e)
            return
    try:
        from ..contest_runner import run_contest

        await run_contest(contest_id)
    except Exception:
        logger.exception("启动龙龙大赛失败")


@driver.on_startup
async def restore_contest_start_jobs():
    now_ts = int(datetime.now().timestamp())
    async with get_session() as sess:
        contests = await sess.scalars(
            select(DragonContest).where(
                DragonContest.status == ContestStatus.SIGNUP.value,
            )
        )
        pending_contests = [(contest.id, contest.start_ts) for contest in contests]
    for contest_id, start_ts in pending_contests:
        if start_ts <= now_ts:
            logger.info(f"发现过期未启动的龙龙大赛，立即启动: contest_id={contest_id}")
            await on_contest_start(contest_id)
            continue
        register_contest_start_job(contest_id, start_ts)
        logger.info(
            f"已恢复龙龙大赛启动任务: contest_id={contest_id}, start_ts={start_ts}"
        )
