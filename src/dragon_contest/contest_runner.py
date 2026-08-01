import asyncio
import random
from dataclasses import dataclass

from nonebot import get_bot, get_plugin_config
from nonebot.adapters import Bot
from nonebot.log import logger
from nonebot_plugin_alconna import MsgTarget, Target, UniMessage
from nonebot_plugin_orm import get_session
from sqlalchemy import func, select

from .config import Config
from .models import ContestStatus, DragonContest, DragonContestPlayer
from .utils import generate_comparison_image, run_single_battle

plugin_config = get_plugin_config(Config)


@dataclass(frozen=True)
class PlayerSnapshot:
    id: int
    dragon_name: str


@dataclass(frozen=True)
class ContestContext:
    target: MsgTarget
    bot: Bot
    round_no: int


async def _get_alive_players(contest_id: int) -> list[PlayerSnapshot]:
    async with get_session() as sess:
        rows = (
            await sess.execute(
                select(DragonContestPlayer.id, DragonContestPlayer.dragon_name).where(
                    DragonContestPlayer.contest_id == contest_id,
                    DragonContestPlayer.eliminated.is_(False),
                )
            )
        ).all()
    return [
        PlayerSnapshot(id=int(row.id), dragon_name=str(row.dragon_name)) for row in rows
    ]


async def _mark_contest_finished(contest_id: int) -> None:
    async with get_session() as sess:
        contest = await sess.get(DragonContest, contest_id)
        if not contest:
            return
        contest.status = ContestStatus.FINISHED.value
        sess.add(contest)
        await sess.commit()


async def _mark_player_eliminated_and_check_alive(
    contest_id: int, player_id: int
) -> tuple[bool, int]:
    async with get_session() as sess:
        contest = await sess.get(DragonContest, contest_id)
        if not contest or contest.status != ContestStatus.RUNNING.value:
            return True, 0

        player = await sess.scalar(
            select(DragonContestPlayer).where(
                DragonContestPlayer.id == player_id,
                DragonContestPlayer.contest_id == contest_id,
            )
        )
        if player:
            player.eliminated = True
            sess.add(player)
            await sess.commit()

        alive_count = (
            await sess.scalar(
                select(func.count())
                .select_from(DragonContestPlayer)
                .where(
                    DragonContestPlayer.contest_id == contest_id,
                    DragonContestPlayer.eliminated.is_(False),
                )
            )
            or 0
        )
        return False, alive_count


async def _advance_round(contest_id: int, round_no: int) -> None:
    async with get_session() as sess:
        contest = await sess.get(DragonContest, contest_id)
        if not contest or contest.status != ContestStatus.RUNNING.value:
            return
        contest.current_round = round_no
        sess.add(contest)
        await sess.commit()


async def _contest_stopped(contest_id: int) -> bool:
    async with get_session() as sess:
        contest = await sess.get(DragonContest, contest_id)
        return not contest or contest.status != ContestStatus.RUNNING.value


async def _get_champion(contest_id: int) -> PlayerSnapshot | None:
    async with get_session() as sess:
        champion = await sess.scalar(
            select(DragonContestPlayer)
            .where(
                DragonContestPlayer.contest_id == contest_id,
                DragonContestPlayer.eliminated.is_(False),
            )
            .order_by(DragonContestPlayer.id)
        )
        if not champion:
            return None
        return PlayerSnapshot(
            id=int(champion.id),
            dragon_name=str(champion.dragon_name),
        )


async def _load_target(target_data: dict, contest_id: int) -> MsgTarget | None:
    try:
        return Target.load(target_data)
    except Exception:
        logger.opt(colors=True).error(
            f"<red>比赛ID {contest_id} 的目标反序列化失败,比赛取消</red>"
        )
        await _mark_contest_finished(contest_id)
        return None


async def _load_bot(target: MsgTarget, contest_id: int) -> Bot | None:
    try:
        return get_bot(target.self_id)
    except Exception:
        logger.opt(colors=True).warning(
            "<yellow>未找到可用的机器人实例,此任务将被跳过</yellow>"
        )
        await _mark_contest_finished(contest_id)
        return None


async def _send_battle_result(
    *,
    p1: PlayerSnapshot,
    p2: PlayerSnapshot,
    round_no: int,
    battle_no: int,
    winner: PlayerSnapshot,
    loser: PlayerSnapshot,
    reason: str,
    compare_data: dict,
    target: MsgTarget,
    bot: Bot,
) -> None:
    await UniMessage.text(
        f"第 {round_no} 轮·第 {battle_no} 场：{p1.dragon_name} vs {p2.dragon_name}"
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


async def _run_round(
    *,
    contest_id: int,
    round_no: int,
    alive_players: list[PlayerSnapshot],
    target: MsgTarget,
    bot: Bot,
) -> tuple[bool, PlayerSnapshot | None]:
    battle_no = 1
    while len(alive_players) >= 2:
        p1 = alive_players.pop(random.randrange(len(alive_players)))
        p2 = alive_players.pop(random.randrange(len(alive_players)))
        winner, loser, reason, compare_data = await run_single_battle(p1, p2, round_no)
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
        is_stopped, alive_count = await _mark_player_eliminated_and_check_alive(
            contest_id, loser.id
        )
        if is_stopped:
            return True, None
        if alive_count > 1:
            await asyncio.sleep(max(1, plugin_config.dc_battle_interval))
    bye_player = alive_players[0] if alive_players else None
    return False, bye_player


async def _prepare_contest_context(contest_id: int) -> ContestContext | None:
    async with get_session() as sess:
        contest = await sess.get(DragonContest, contest_id)
        if not contest or contest.status != ContestStatus.RUNNING.value:
            return None
        target_data = dict(contest.target)
        round_no = int(contest.current_round or 1)
    target = await _load_target(target_data, contest_id)
    if not target:
        return None
    bot = await _load_bot(target, contest_id)
    if not bot:
        return None
    return ContestContext(target=target, bot=bot, round_no=round_no)


async def _announce_start_or_cancel(
    contest_id: int,
    target: MsgTarget,
    bot: Bot,
) -> bool:
    players = await _get_alive_players(contest_id)
    if len(players) < 2:
        await UniMessage.text("比赛人数不足,比赛取消").send(target=target, bot=bot)
        await _mark_contest_finished(contest_id)
        return False
    await UniMessage.text(f"龙龙大赛开始,本次参赛人数为: {len(players)}").send(
        target=target, bot=bot
    )
    return True


async def _run_contest_rounds(
    contest_id: int,
    round_no: int,
    target: MsgTarget,
    bot: Bot,
) -> None:
    while not await _contest_stopped(contest_id):
        alive_players = await _get_alive_players(contest_id)
        if len(alive_players) <= 1:
            break
        await UniMessage.text(
            f"第 {round_no} 轮比赛开始,当前剩余选手: {len(alive_players)}"
        ).send(target=target, bot=bot)
        should_stop, bye_player = await _run_round(
            contest_id=contest_id,
            round_no=round_no,
            alive_players=list(alive_players),
            target=target,
            bot=bot,
        )
        if should_stop:
            break
        if bye_player:
            await UniMessage.text(
                f"选手 {bye_player.dragon_name} 获得轮空,直接晋级下一轮"
            ).send(target=target, bot=bot)
        round_no += 1
        await _advance_round(contest_id, round_no)


async def _finish_contest(contest_id: int, target: MsgTarget, bot: Bot) -> None:
    champion = await _get_champion(contest_id)
    if champion:
        await UniMessage.text(
            f"龙龙大赛圆满结束\n本届龙龙大赛冠军为: {champion.dragon_name}!"
        ).send(target=target, bot=bot)
    await _mark_contest_finished(contest_id)


async def run_contest(contest_id: int) -> None:
    context = await _prepare_contest_context(contest_id)
    if not context:
        return
    should_start = await _announce_start_or_cancel(
        contest_id,
        context.target,
        context.bot,
    )
    if not should_start:
        return
    await _run_contest_rounds(
        contest_id,
        context.round_no,
        context.target,
        context.bot,
    )
    await _finish_contest(contest_id, context.target, context.bot)
