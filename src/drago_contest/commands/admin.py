from datetime import datetime

from nonebot.log import logger
from sqlalchemy import delete, select, func
from sqlalchemy.exc import IntegrityError
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import MsgTarget, Target

from ..models import ContestStatus, DragonContest, DragonContestPlayer
from ..utils import (
    get_current_contest,
    get_or_create_config,
    register_contest_start_job,
)
from ..commands.command_registry import dragon_contest_command


@dragon_contest_command.assign("create")
async def handle_create_contest(
    time: str,
    limit: int | None,
    sess: async_scoped_session,
    target: MsgTarget,
):
    try:
        dt = datetime.strptime(time, "%Y/%m/%d %H:%M")
    except ValueError:
        await dragon_contest_command.finish("时间格式错误,请使用YYYY/MM/DD HH:MM格式")
        return
    start_ts = int(dt.timestamp())
    config = await get_or_create_config(sess)
    contest_limit = limit if limit is not None else config.default_limit
    if contest_limit < 1 or contest_limit > 32:
        await dragon_contest_command.finish("参加人数限制必须在 1~32 之间")
    contest = DragonContest(
        start_ts=start_ts,
        limit=contest_limit,
        target=Target.dump(target),
    )
    if contest.start_ts <= int(datetime.now().timestamp()):
        await dragon_contest_command.finish("比赛时间必须在未来")
    sess.add(contest)
    try:
        await sess.commit()
        register_contest_start_job(contest)
    except IntegrityError:
        await sess.rollback()
        await dragon_contest_command.finish("创建比赛失败,请检查参数")
    except Exception as e:
        await sess.rollback()
        logger.exception(e)
        await dragon_contest_command.finish("创建比赛失败,请查看日志")
    await dragon_contest_command.finish(
        "已创建龙龙大赛\n"
        f"时间：{time}\n"
        f"人数限制：{contest_limit}\n"
    )


@dragon_contest_command.assign("delete")
async def handle_delete_contest(id: int, sess: async_scoped_session):
    contest = await sess.get(DragonContest, id)
    if not contest:
        await dragon_contest_command.finish(f"未找到ID为 {id} 的龙龙大赛")
    if contest.status == ContestStatus.RUNNING.value:
        await dragon_contest_command.finish("无法删除正在进行中的龙龙大赛")
    await sess.execute(
        delete(DragonContestPlayer).where(DragonContestPlayer.contest_id == id)
    )
    await sess.delete(contest)
    try:
        await sess.commit()
    except Exception as e:
        await sess.rollback()
        logger.exception(e)
        await dragon_contest_command.finish("删除比赛失败,请查看日志")
    await dragon_contest_command.finish(
        f"已删除龙龙大赛（ID: {id}）及其所有参赛数据"
    )


@dragon_contest_command.assign("list")
async def handle_list_contests(sess: async_scoped_session):
    contest = (
        await sess.scalars(
            select(DragonContest).order_by(DragonContest.start_ts.desc())
        )
    ).all()
    if not contest:
        await dragon_contest_command.finish("当前没有正在进行的龙龙大赛")
    lines = ["当前正在进行的龙龙大赛：\n"]
    for c in contest:
        dt = datetime.fromtimestamp(c.start_ts)
        lines.append(
            f"ID: {c.id}\n"
            f"时间：{dt:%Y-%m-%d %H:%M}\n"
            f"人数限制：{c.limit}\n"
            f"━━━━━━━━━━━━━━"
        )
    await dragon_contest_command.finish("\n".join(lines))


@dragon_contest_command.assign("status")
async def handle_contest_status(sess: async_scoped_session):
    contest = await get_current_contest(sess)
    if not contest:
        await dragon_contest_command.finish("当前没有正在进行的龙龙大赛")
    count = await sess.scalar(
        select(func.count())
        .select_from(DragonContestPlayer)
        .where(DragonContestPlayer.contest_id == contest.id)
    ) or 0
    phase = "进行中" if contest.status == ContestStatus.RUNNING.value else "报名中"
    await dragon_contest_command.finish(
        "龙龙大赛\n\n"
        f"当前阶段：{phase}\n"
        f"时间：{datetime.fromtimestamp(contest.start_ts):%Y-%m-%d %H:%M}\n"
        f"报名人数：{count}/{contest.limit}"
    )
