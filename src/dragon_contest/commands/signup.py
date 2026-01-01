from datetime import datetime

from nonebot.adapters import Event
from nonebot.log import logger
from sqlalchemy import delete, select, func
from sqlalchemy.exc import IntegrityError
from nonebot_plugin_orm import async_scoped_session

from ..models import DragonContestPlayer
from ..utils import get_signup_contest
from ..commands.command_registry import (
    cancel_dragon_contest_command,
    join_dragon_contest_command,
    revise_dragon_name_command,
)


@join_dragon_contest_command.handle()
async def handle_join_contest(
    name: str,
    sess: async_scoped_session,
    event: Event,
):
    contest = await get_signup_contest(sess)
    if not contest:
        await join_dragon_contest_command.finish("当前阶段的龙龙大赛已无法进行该操作")
    contest_id = int(contest.id)
    contest_limit = int(contest.limit)
    contest_start_ts = int(contest.start_ts)
    current_count = await sess.scalar(
        select(func.count())
        .select_from(DragonContestPlayer)
        .where(DragonContestPlayer.contest_id == contest_id)
    ) or 0
    if current_count >= contest_limit:
        await join_dragon_contest_command.finish("本次龙龙大赛报名人数已满")
    player = DragonContestPlayer(
        contest_id=contest_id,
        user_id=str(event.get_user_id()),
        dragon_name=name,
    )
    sess.add(player)
    try:
        await sess.commit()
    except IntegrityError:
        await sess.rollback()
        await join_dragon_contest_command.finish("你已经报名过本次龙龙大赛")
    except Exception as e:
        await sess.rollback()
        logger.exception(e)
        await join_dragon_contest_command.finish("加入比赛失败,请查看日志")
    dt = datetime.fromtimestamp(contest_start_ts)
    await join_dragon_contest_command.finish(
        "报名成功！\n"
        f"龙龙名称：{name}\n"
        f"比赛时间：{dt:%Y-%m-%d %H:%M}"
    )


@cancel_dragon_contest_command.handle()
async def handle_cancel_contest(
    sess: async_scoped_session,
    event: Event,
):
    contest = await get_signup_contest(sess)
    if not contest:
        await cancel_dragon_contest_command.finish("当前阶段的龙龙大赛已无法进行该操作")
    stmt = (
        delete(DragonContestPlayer)
        .where(
            DragonContestPlayer.contest_id == contest.id,
            DragonContestPlayer.user_id == str(event.get_user_id()),
        )
        .returning(DragonContestPlayer.id)
    )
    result = await sess.execute(stmt)
    deleted_ids = result.scalars().all()
    if not deleted_ids:
        await cancel_dragon_contest_command.finish("你尚未报名本次龙龙大赛")
    try:
        await sess.commit()
    except Exception as e:
        await sess.rollback()
        logger.exception(e)
        await cancel_dragon_contest_command.finish("取消报名失败,请查看日志")
    await cancel_dragon_contest_command.finish("已取消本次龙龙大赛的报名")


@revise_dragon_name_command.handle()
async def handle_revise_dragon_name(
    name: str,
    sess: async_scoped_session,
    event: Event,
):
    contest = await get_signup_contest(sess)
    if not contest:
        await revise_dragon_name_command.finish("当前阶段的龙龙大赛已无法进行该操作")
    contest_id = int(contest.id)
    contest_start_ts = int(contest.start_ts)
    if datetime.now().timestamp() > contest_start_ts - 600:
        await revise_dragon_name_command.finish(
            "距离比赛开始不足10分钟,无法修改龙龙名称"
        )
    player = await sess.scalar(
        select(DragonContestPlayer)
        .where(
            DragonContestPlayer.contest_id == contest_id,
            DragonContestPlayer.user_id == str(event.get_user_id()),
        )
    )
    if not player:
        await revise_dragon_name_command.finish("你尚未报名本次龙龙大赛")
    player.dragon_name = name
    try:
        await sess.commit()
    except Exception as e:
        await sess.rollback()
        logger.exception(e)
        await revise_dragon_name_command.finish("修改龙龙名称失败,请查看日志")
    dt = datetime.fromtimestamp(contest_start_ts)
    await revise_dragon_name_command.finish(
        "龙龙名称修改成功\n"
        f"新名称：{name}\n"
        f"比赛时间：{dt:%Y-%m-%d %H:%M}"
    )
