from datetime import datetime

from nonebot.adapters import Event
from nonebot.log import logger
from nonebot_plugin_alconna import UniMessage
from sqlalchemy import delete, select, func
from sqlalchemy.exc import IntegrityError
from nonebot_plugin_orm import async_scoped_session

from ..models import DragonContestPlayer
from ..utils import (
    generate_comparison_image,
    get_signup_contest,
    run_single_battle,
    get_contest_champion,
)
from ..commands.command_registry import (
    cancel_dragon_contest_command,
    join_dragon_contest_command,
    revise_dragon_name_command,
    dragon_name_comparison_command,
    dragon_contest_champion_command,
    dragon_contest_help_command,
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
    current_count = (
        await sess.scalar(
            select(func.count())
            .select_from(DragonContestPlayer)
            .where(DragonContestPlayer.contest_id == contest_id)
        )
        or 0
    )
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
        f"报名成功！\n龙龙名称：{name}\n比赛时间：{dt:%Y-%m-%d %H:%M}"
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
        select(DragonContestPlayer).where(
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
        f"龙龙名称修改成功\n新名称：{name}\n比赛时间：{dt:%Y-%m-%d %H:%M}"
    )


@dragon_name_comparison_command.handle()
async def handle_dragon_name_comparison(name1: str, name2: str):
    name1 = str(name1 or "").strip()
    name2 = str(name2 or "").strip()
    if not name1 or not name2:
        await dragon_name_comparison_command.finish("龙龙名称不能为空")
    if name1 == name2:
        await dragon_name_comparison_command.finish("龙龙名称不能相同")
    p1 = DragonContestPlayer(contest_id=0, user_id="comparison_p1", dragon_name=name1)
    p2 = DragonContestPlayer(contest_id=0, user_id="comparison_p2", dragon_name=name2)
    winner = None
    loser = None
    reason = "未知"
    try:
        winner, loser, reason, compare_data = await run_single_battle(p1, p2, 1)
        payload = dict(compare_data or {})
        payload["title"] = "龙龙名称比较"
        payload["subtitle"] = f"{name1} vs {name2}"
        payload["columns"] = ["维度", winner.dragon_name, loser.dragon_name]
        img = await generate_comparison_image(payload)
        await UniMessage.image(raw=img).send(reply_to=True)
    except Exception as e:
        logger.exception(e)
        await dragon_name_comparison_command.finish(
            "龙龙名称比较\n"
            f"名称1：{name1}\n"
            f"名称2：{name2}\n"
            f"胜者：{winner.dragon_name if winner else '未知'}\n"
            f"败者：{loser.dragon_name if loser else '未知'}\n"
            f"理由：{reason}"
        )


@dragon_contest_champion_command.handle()
async def handle_dragon_contest_champion(sess: async_scoped_session):
    try:
        champion_data = await get_contest_champion(sess)
        if not champion_data:
            await dragon_contest_champion_command.send("暂无龙龙大赛冠军数据")
        await dragon_contest_champion_command.send(f"历史龙龙大赛冠军：{champion_data}")
    except Exception as e:
        logger.exception(e)
        await dragon_contest_champion_command.finish("查询龙龙大赛冠军失败,请查看日志")


@dragon_contest_help_command.handle()
async def handle_dragon_contest_help():
    lines = [
        "龙龙大赛命令帮助\n",
        "【管理命令】(仅超级用户)\n",
        "1. /龙龙大赛 创建 YYYY/MM/DD HH:MM [-n|--number 参赛人数]",
        "2. /龙龙大赛 删除 比赛ID",
        "3. /龙龙大赛 强制删除 比赛ID",
        "4. /龙龙大赛 列表",
        "5. /龙龙大赛 状态\n",
        "6. /添加龙龙大赛参赛者 用户ID 龙龙名称",
        "7. /移除龙龙大赛参赛者 用户ID",
        "8. /龙龙大赛参赛名单\n",
        "【参赛者命令】\n",
        "9. /加入龙龙大赛 龙龙名称",
        "10. /取消报名",
        "11. /修改龙龙名称 新的龙龙名称",
        "12. /龙龙名称比较 名称1 名称2",
        "13. /龙龙大赛冠军",
        "14. /龙龙大赛帮助",
    ]
    await dragon_contest_help_command.finish("\n".join(lines))
