import asyncio
from datetime import datetime

from sqlalchemy import select
from nonebot import get_plugin_config
from nonebot_plugin_orm import async_scoped_session

from ..config import Config
from ..models import (
    ContestStatus,
    DragonContest,
    DragonContestConfig,
    DragonContestPlayer,
)

plugin_config = get_plugin_config(Config)
_contest_signup_locks: dict[int, asyncio.Lock] = {}


def get_contest_signup_lock(contest_id: int) -> asyncio.Lock:
    lock = _contest_signup_locks.get(contest_id)
    if lock is None:
        lock = asyncio.Lock()
        _contest_signup_locks[contest_id] = lock
    return lock


async def get_contest_champion(sess: async_scoped_session) -> str | None:
    champion = await sess.scalar(
        select(DragonContestPlayer.dragon_name)
        .join(DragonContest, DragonContest.id == DragonContestPlayer.contest_id)
        .where(
            DragonContest.status == ContestStatus.FINISHED.value,
            DragonContestPlayer.eliminated.is_(False),
        )
        .order_by(DragonContest.start_ts.desc())
    )
    return champion


async def get_signup_contest(sess: async_scoped_session) -> DragonContest | None:
    now_ts = int(datetime.now().timestamp())
    signup_end = now_ts + plugin_config.dc_signup_before_seconds
    signup_close = now_ts + plugin_config.dc_signup_end_before_seconds
    return await sess.scalar(
        select(DragonContest)
        .where(
            DragonContest.start_ts > signup_close,
            DragonContest.start_ts <= signup_end,
            DragonContest.status == ContestStatus.SIGNUP.value,
        )
        .order_by(DragonContest.start_ts.asc())
    )


async def get_active_contest(sess: async_scoped_session) -> DragonContest | None:
    now_ts = int(datetime.now().timestamp())
    return await sess.scalar(
        select(DragonContest)
        .where(
            DragonContest.start_ts <= now_ts,
            DragonContest.status == ContestStatus.RUNNING.value,
        )
        .order_by(DragonContest.start_ts.desc())
    )


async def get_current_contest(sess: async_scoped_session) -> DragonContest | None:
    contest = await get_active_contest(sess)
    if contest:
        return contest
    return await get_signup_contest(sess)


async def get_or_create_config(sess: async_scoped_session) -> DragonContestConfig:
    config = await sess.get(DragonContestConfig, 1)
    if not config:
        config = DragonContestConfig(
            id=1,
            default_limit=plugin_config.dc_default_dragon_number,
        )
        sess.add(config)
        await sess.flush()
    return config
