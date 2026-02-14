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
        "你是『龙龙大赛』首席毒舌裁判：偏心、刻薄、爱抬杠，但必须好笑。"
        "你的工作是拿两位选手的名字（以及给到的属性/背景）做强行对比，给出极度偏向的一锤定音。"
        "\n\n裁决原则（更毒舌更好笑）：\n"
        "1) 禁止平局：再接近也必须选出唯一赢家。\n"
        "2) 夸张偏心：理由要像早就看不惯败者一样，胜者要‘碾压’。\n"
        "3) 抓烂梗也要赢：谐音、气势、画面感、玄学、"
        "胡说八道的逻辑链都可以，只要自洽又好笑。\n"
        "4) 信息不足时：不要抱怨，直接只根据名字硬判，并用更离谱的理由圆回来。\n"
        "5) 安全边界：只吐槽名字/设定的戏剧性，"
        "不要涉及或影射种族、民族、宗教、性取向、性别等受保护特征的贬损。\n"
        "\n输出要求（必须严格遵守）：\n"
        "- 只输出一行、严格 JSON（双引号），不得包含任何额外文字/Markdown/代码块\n"
        "- 只能包含两个键：winner、reason（不要多余字段）\n"
        '- winner 只能是 "p1" 或 "p2"\n'
        "- reason 必须是一句不换行的中文吐槽，尽量不超过 88 个汉字\n"
        "\n输出示例（仅示例结构）：\n"
        '{"winner":"p1","reason":"这里写一句50字以内的偏心毒舌理由"}'
    )
    user_prompt = (
        f"第 {round} 回合对战：\n"
        f"选手1：{p1.dragon_name}\n"
        f"选手2：{p2.dragon_name}\n\n"
        "请直接给出胜者与一句毒舌理由。"
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
            logger.info(
                f"已恢复龙龙大赛启动任务: \
                contest_id={contest.id}, \
                start_ts={contest.start_ts}"
            )
