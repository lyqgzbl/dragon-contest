import asyncio
import random
import contextlib

from nonebot.adapters import Bot
from sqlalchemy import func, select
from nonebot import get_bot
from nonebot.log import logger
from nonebot_plugin_orm import get_session
from nonebot_plugin_alconna import MsgTarget, Target, UniMessage

from .utils import generate_comparison_image, run_single_battle
from .models import DragonContest, DragonContestPlayer, ContestStatus


async def _get_alive_players(sess, contest_id: int) -> list[DragonContestPlayer]:
    return (
        await sess.scalars(
            select(DragonContestPlayer).where(
                DragonContestPlayer.contest_id == contest_id,
                DragonContestPlayer.eliminated.is_(False),
            )
        )
    ).all()


async def _load_target(contest, contest_id: int, sess) -> MsgTarget | None:
    try:
        return Target.load(contest.target)
    except Exception:
        logger.opt(colors=True).error(
            f"<red>比赛ID {contest_id} 的目标反序列化失败,比赛取消</red>"
        )
        contest.status = ContestStatus.FINISHED.value
        await sess.commit()
        return None


async def _load_bot(target: MsgTarget, contest, sess) -> Bot | None:
    try:
        return get_bot(target.self_id)
    except Exception:
        logger.opt(colors=True).warning(
            "<yellow>未找到可用的机器人实例,此任务将被跳过</yellow>"
        )
        contest.status = ContestStatus.FINISHED.value
        await sess.commit()
        return None


async def _send_battle_result(
    *,
    p1: DragonContestPlayer,
    p2: DragonContestPlayer,
    round_no: int,
    battle_no: int,
    winner: DragonContestPlayer,
    loser: DragonContestPlayer,
    reason: str,
    compare_data: dict,
    target: MsgTarget,
    bot,
) -> None:
    await UniMessage.text(
        f"第 {round_no} 轮·第 {battle_no}：{p1.dragon_name} vs {p2.dragon_name}"
    ).send(target=target, bot=bot)
    try:
        payload = dict(compare_data or {})
        payload["title"] = "龙龙大赛"
        payload["subtitle"] = (
            f"第 {round_no} 轮·第 {battle_no} 场：{p1.dragon_name} vs {p2.dragon_name}"
        )
        payload["columns"] = [
            "维度",
            winner.dragon_name,
            loser.dragon_name,
        ]
        img = await generate_comparison_image(payload)
        await UniMessage.image(raw=img).send(target=target, bot=bot)
    except Exception:
        logger.exception("发送对战结果图片失败，回退为文字")
        await UniMessage.text(
            f"对战结果：\n"
            f"选手1：{p1.dragon_name}\n"
            f"选手2：{p2.dragon_name}\n"
            f"获胜者：{winner.dragon_name}\n"
            f"失败者：{loser.dragon_name}\n"
            f"理由：{reason}\n"
        ).send(target=target, bot=bot)


async def _contest_stopped(sess, contest_id: int) -> bool:
    contest = await sess.get(DragonContest, contest_id)
    return not contest or contest.status != ContestStatus.RUNNING.value


async def _run_round(
    *,
    sess,
    contest_id: int,
    round_no: int,
    alive_players: list[DragonContestPlayer],
    target: MsgTarget,
    bot,
) -> bool:
    battle_no = 1
    while len(alive_players) >= 2:
        p1 = alive_players.pop(random.randrange(len(alive_players)))
        p2 = alive_players.pop(random.randrange(len(alive_players)))
        winner, loser, reason, compare_data = await run_single_battle(p1, p2, round_no)
        loser.eliminated = True
        sess.add(loser)
        await _send_battle_result(
            p1=p1,
            p2=p2,
            round_no=round_no,
            battle_no=battle_no,
            winner=winner,
            loser=loser,
            reason=reason,
            compare_data=compare_data,
            target=target,
            bot=bot,
        )
        battle_no += 1
        await sess.commit()
        if await _contest_stopped(sess, contest_id):
            return True
        alive_count = await sess.scalar(
            select(func.count())
            .select_from(DragonContestPlayer)
            .where(
                DragonContestPlayer.contest_id == contest_id,
                DragonContestPlayer.eliminated.is_(False),
            )
        )
        if alive_count and alive_count > 1:
            await asyncio.sleep(60)
    return False


async def _get_running_contest(sess, contest_id: int) -> DragonContest | None:
    contest = await sess.get(DragonContest, contest_id)
    if not contest:
        return None
    if contest.status != ContestStatus.RUNNING.value:
        return None
    return contest


async def _prepare_contest_context(sess, contest_id: int):
    contest = await _get_running_contest(sess, contest_id)
    if not contest:
        return None
    target: MsgTarget | None = await _load_target(contest, contest_id, sess)
    if not target:
        return None
    bot = await _load_bot(target, contest, sess)
    if not bot:
        return None
    return contest, target, bot, (contest.current_round or 1)


async def _announce_start_or_cancel(
    sess,
    contest_id: int,
    contest,
    target,
    bot,
) -> bool:
    players = await _get_alive_players(sess, contest_id)
    if len(players) < 2:
        await UniMessage.text("比赛人数不足,比赛取消").send(target=target, bot=bot)
        contest.status = ContestStatus.FINISHED.value
        await sess.commit()
        return False
    await UniMessage.text(f"龙龙大赛开始,本次参赛人数为: {len(players)}").send(
        target=target, bot=bot
    )
    return True


async def _run_contest_rounds(
    sess,
    contest_id: int,
    round_no: int,
    target: MsgTarget,
    bot,
)->DragonContest | None:
    latest_contest = await sess.get(DragonContest, contest_id)
    while latest_contest and latest_contest.status == ContestStatus.RUNNING.value:
        alive_players = await _get_alive_players(sess, contest_id)
        if len(alive_players) <= 1:
            break
        await UniMessage.text(
            f"第 {round_no} 轮比赛开始,当前剩余选手: {len(alive_players)}"
        ).send(target=target, bot=bot)
        should_stop = await _run_round(
            sess=sess,
            contest_id=contest_id,
            round_no=round_no,
            alive_players=list(alive_players),
            target=target,
            bot=bot,
        )
        if should_stop:
            break
        if len(alive_players) % 2 == 1:
            bye_player = alive_players[-1]
            await UniMessage.text(
                f"选手 {bye_player.dragon_name} 获得轮空,直接晋级下一轮"
            ).send(target=target, bot=bot)
        round_no += 1
        latest_contest.current_round = round_no
        sess.add(latest_contest)
        await sess.commit()
        latest_contest = await _get_running_contest(sess, contest_id)
    return latest_contest


async def _finish_contest(sess, contest_id: int, contest, target, bot) -> None:
    champion = (
        await sess.scalars(
            select(DragonContestPlayer).where(
                DragonContestPlayer.contest_id == contest_id,
                DragonContestPlayer.eliminated.is_(False),
            )
        )
    ).first()
    if champion:
        await UniMessage.text(
            f"龙龙大赛圆满结束\n本届龙龙大赛冠军为: {champion.dragon_name}!"
        ).send(target=target, bot=bot)
    if contest:
        contest.status = ContestStatus.FINISHED.value
        sess.add(contest)
        await sess.commit()


async def run_contest(contest_id: int) -> None:
    async with get_session() as sess:
        with contextlib.suppress(AttributeError, Exception):
            sess.sync_session.expire_on_commit = False
        context = await _prepare_contest_context(sess, contest_id)
        if not context:
            return
        contest, target, bot, round_no = context
        should_start = await _announce_start_or_cancel(
            sess,
            contest_id,
            contest,
            target,
            bot,
        )
        if not should_start:
            return
        contest = await _run_contest_rounds(
            sess,
            contest_id,
            round_no,
            target,
            bot,
        )
        await _finish_contest(sess, contest_id, contest, target, bot)
