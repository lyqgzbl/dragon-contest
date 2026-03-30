from datetime import datetime
import contextlib

from arclet.alconna import Arparma
from nonebot.log import logger
from sqlalchemy import delete, select, func
from sqlalchemy.exc import IntegrityError
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import MsgTarget, Target

from ..models import ContestStatus, DragonContest, DragonContestPlayer
from ..utils import (
    get_current_contest,
    get_or_create_config,
    register_contest_start_job,
)
from ..commands.command_registry import (
    dragon_contest_command,
    add_dragon_contest_player_command,
    remove_dragon_contest_player_command,
    list_dragon_contest_player_command,
)


async def _handle_create_contest(
    date: str,
    time: str,
    limit: int | None,
    sess: async_scoped_session,
    target: MsgTarget,
):
    time_str = f"{date} {time}"
    try:
        dt = datetime.strptime(time_str, "%Y/%m/%d %H:%M")
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
    await sess.flush()
    contest_id = int(contest.id)
    try:
        await sess.commit()
        register_contest_start_job(contest_id, start_ts)
    except IntegrityError:
        await sess.rollback()
        await dragon_contest_command.finish("创建比赛失败,请检查参数")
    except Exception as e:
        await sess.rollback()
        logger.exception(e)
        await dragon_contest_command.finish("创建比赛失败,请查看日志")
    await dragon_contest_command.finish(
        f"已创建龙龙大赛\n时间：{time_str}\n人数限制：{contest_limit}\n"
    )


async def _handle_delete_contest(id: int, sess: async_scoped_session):
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
    await dragon_contest_command.finish(f"已删除龙龙大赛（ID: {id}）及其所有参赛数据")


async def _handle_force_delete_contest(id: int, sess: async_scoped_session):
    contest = await sess.get(DragonContest, id)
    if not contest:
        await dragon_contest_command.finish(f"未找到ID为 {id} 的龙龙大赛")
    with contextlib.suppress(Exception):
        scheduler.remove_job(f"dragon_contest_start_{id}")
    await sess.execute(
        delete(DragonContestPlayer).where(DragonContestPlayer.contest_id == id)
    )
    await sess.delete(contest)
    try:
        await sess.commit()
    except Exception as e:
        await sess.rollback()
        logger.exception(e)
        await dragon_contest_command.finish("强制删除比赛失败,请查看日志")
    await dragon_contest_command.finish(
        f"已强制删除龙龙大赛（ID: {id}）及其所有参赛数据"
    )


async def _handle_list_contests(sess: async_scoped_session):
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


async def _handle_contest_status(sess: async_scoped_session):
    contest = await get_current_contest(sess)
    if not contest:
        await dragon_contest_command.finish("当前没有正在进行的龙龙大赛")
    count = (
        await sess.scalar(
            select(func.count())
            .select_from(DragonContestPlayer)
            .where(DragonContestPlayer.contest_id == contest.id)
        )
        or 0
    )
    phase = "进行中" if contest.status == ContestStatus.RUNNING.value else "报名中"
    await dragon_contest_command.finish(
        "龙龙大赛\n\n"
        f"当前阶段：{phase}\n"
        f"时间：{datetime.fromtimestamp(contest.start_ts):%Y-%m-%d %H:%M}\n"
        f"报名人数：{count}/{contest.limit}"
    )


@dragon_contest_command.handle()
async def handle_admin_dispatch(
    result: Arparma,
    sess: async_scoped_session,
    target: MsgTarget,
):
    create = result.query("create")
    if create is not None:
        date = str(create.args.get("date", "")).strip()
        time = str(create.args.get("time", "")).strip()
        number_opt = create.options.get("number") if create.options else None
        limit = None
        if number_opt is not None:
            limit = number_opt.args.get("limit")
        await _handle_create_contest(date, time, limit, sess, target)
        return
    delete_cmd = result.query("delete")
    if delete_cmd is not None:
        contest_id = delete_cmd.args.get("id")
        await _handle_delete_contest(int(contest_id), sess)
        return
    force_delete_cmd = result.query("force_delete")
    if force_delete_cmd is not None:
        contest_id = force_delete_cmd.args.get("id")
        await _handle_force_delete_contest(int(contest_id), sess)
        return
    if result.query("list") is not None:
        await _handle_list_contests(sess)
        return
    if result.query("status") is not None:
        await _handle_contest_status(sess)
        return


@add_dragon_contest_player_command.handle()
async def handle_add_dragon_contest_player(
    name: str,
    user_id: str,
    sess: async_scoped_session,
):
    contest = await get_current_contest(sess)
    if not contest:
        await add_dragon_contest_player_command.finish("当前没有可报名的龙龙大赛")
    if contest.status != ContestStatus.SIGNUP.value:
        await add_dragon_contest_player_command.finish(
            "当前阶段的龙龙大赛已无法进行该操作"
        )
    count = (
        await sess.scalar(
            select(func.count())
            .select_from(DragonContestPlayer)
            .where(
                DragonContestPlayer.contest_id == contest.id,
                DragonContestPlayer.eliminated.is_(False),
            )
        )
        or 0
    )
    if count >= contest.limit:
        await add_dragon_contest_player_command.finish("本次龙龙大赛报名人数已满")
    exists = await sess.scalar(
        select(func.count())
        .select_from(DragonContestPlayer)
        .where(
            DragonContestPlayer.contest_id == contest.id,
            DragonContestPlayer.user_id == user_id,
        )
    )
    if exists:
        await add_dragon_contest_player_command.finish("该用户已在参赛名单中")
    player = DragonContestPlayer(
        contest_id=contest.id,
        user_id=user_id,
        dragon_name=name,
    )
    sess.add(player)
    try:
        await sess.commit()
    except IntegrityError:
        await sess.rollback()
        await add_dragon_contest_player_command.finish("添加失败,请查看日志")
    except Exception as e:
        await sess.rollback()
        logger.exception(e)
        await add_dragon_contest_player_command.finish("添加失败,请查看日志")
    await add_dragon_contest_player_command.finish(
        f"已成功添加参赛者\n用户ID：{user_id}\n龙龙名称：{name}"
    )


@remove_dragon_contest_player_command.handle()
async def handle_remove_dragon_contest_player(user_id: str, sess: async_scoped_session):
    contest = await get_current_contest(sess)
    if not contest:
        await remove_dragon_contest_player_command.finish("当前没有龙龙大赛")
    if contest.status != ContestStatus.SIGNUP.value:
        await remove_dragon_contest_player_command.finish(
            "当前阶段的龙龙大赛已无法进行该操作"
        )
    player = await sess.scalar(
        select(DragonContestPlayer).where(
            DragonContestPlayer.contest_id == contest.id,
            DragonContestPlayer.user_id == user_id,
        )
    )
    if not player:
        await remove_dragon_contest_player_command.finish("该用户不在参赛名单中")
    dragon_name = str(player.dragon_name)
    await sess.delete(player)
    try:
        await sess.commit()
    except Exception as e:
        await sess.rollback()
        logger.exception(e)
        await remove_dragon_contest_player_command.finish("移除参赛者失败,请查看日志")
    await remove_dragon_contest_player_command.finish(
        f"已成功移除参赛者\n用户ID：{user_id}\n龙龙名称：{dragon_name}"
    )


@list_dragon_contest_player_command.handle()
async def handle_list_dragon_contest_player(sess: async_scoped_session):
    contest = await get_current_contest(sess)
    if not contest:
        await list_dragon_contest_player_command.finish("当前没有龙龙大赛")
    players = (
        await sess.scalars(
            select(DragonContestPlayer)
            .where(DragonContestPlayer.contest_id == contest.id)
            .order_by(DragonContestPlayer.id)
        )
    ).all()
    if not players:
        await list_dragon_contest_player_command.finish("当前没有参赛者")
    lines = [
        "龙龙大赛参赛名单\n",
        f"比赛时间：{datetime.fromtimestamp(contest.start_ts):%Y-%m-%d %H:%M}\n",
    ]
    for idx, p in enumerate(players, start=1):
        status = "❌ 已淘汰" if p.eliminated else "✅ 在赛"
        lines.append(
            f"{idx}. {p.dragon_name}\n   用户ID：{p.user_id}\n   状态：{status}\n"
        )
    await list_dragon_contest_player_command.finish("\n".join(lines))
