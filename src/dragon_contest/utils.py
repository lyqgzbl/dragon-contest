import re
import json
import random
from datetime import datetime

from sqlalchemy import select
from nonebot import get_plugin_config, get_driver
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import async_scoped_session, get_session

from .config import Config
from .models import (
    ContestStatus,
    DragonContest,
    DragonContestConfig,
    DragonContestPlayer,
)


driver = get_driver()
plugin_config = get_plugin_config(Config)


async def get_signup_contest(sess: async_scoped_session) -> DragonContest | None:
    now_ts = int(datetime.now().timestamp())
    signup_end = now_ts + plugin_config.dc_signup_before_seconds
    return await sess.scalar(
        select(DragonContest)
        .where(
            DragonContest.start_ts >= now_ts,
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
        from .contest_runner import run_contest
        await run_contest(contest_id)
    except Exception:
        logger.exception("启动龙龙大赛失败")


async def run_single_battle(
    p1: DragonContestPlayer,
    p2: DragonContestPlayer,
    round: int,
):
    from . import openai_handler
    if openai_handler is None:
        winner, loser = random.sample([p1, p2], 2)
        return (
            winner,
            loser,
            "未配置 OpenAI,随机决出胜负"
        )
    system_prompt = (
        "你是龙龙大赛的裁判。"
        "只输出一段 JSON，不要输出任何额外文本。"
        "JSON 格式如下："
        '{"winner":"p1|p2","reason":"..."}'
    )
    user_prompt = (
        f"第 {round} 回合对战：\n"
        f"选手1：{p1.dragon_name}\n"
        f"选手2：{p2.dragon_name}\n\n"
        "请从战斗力、智慧、速度、防御、技能等方面综合比较，"
        "给出更强者，并用一句话说明原因。"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        content = await openai_handler.get_response(messages)
    except Exception:
        logger.exception("调用 OpenAI 接口失败,随机决出胜负")
        winner, loser = random.sample([p1, p2], 2)
        return (
            winner,
            loser,
            "调用 OpenAI 接口失败,随机决出胜负"
        )
    match = re.search(r"\{.*\}", content, flags=re.S)
    if not match:
        winner, loser = random.sample([p1, p2], 2)
        return (
            winner,
            loser,
            f"AI 输出格式错误,随机决出胜负。原始输出：{content}"
        )
    try:
        data = json.loads(match.group(0))
    except Exception:
        winner, loser = random.sample([p1, p2], 2)
        return (
            winner,
            loser,
            f"输出解析失败,随机决出胜负。原始输出：{content}"
        )
    winner_flag = str(data.get("winner", "")).strip().lower()
    reason = str(data.get("reason", "")).strip()
    if not reason:
        reason = "AI 未给出明确理由"
    if winner_flag == "p1":
        return p1, p2, reason
    elif winner_flag == "p2":
        return p2, p1, reason
    winner, loser = random.sample([p1, p2], 2)
    return (
        winner,
        loser,
        f"AI 输出胜者不明确,随机决出胜负。原始输出：{content}"
    )


@driver.on_startup
async def restore_contest_start_jobs():
    async with get_session() as sess:
        now_ts = int(datetime.now().timestamp())
        contests = await sess.scalars(
            select(DragonContest)
            .where(
                DragonContest.start_ts > now_ts,
                DragonContest.status == ContestStatus.SIGNUP.value,
            )
        )
        for contest in contests:
            if contest.start_ts <= now_ts:
                continue
            register_contest_start_job(contest.id, contest.start_ts)
