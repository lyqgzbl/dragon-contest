from sqlalchemy import select
from nonebot import get_bot
from nonebot.log import logger
from nonebot_plugin_orm import get_session
from nonebot_plugin_alconna import MsgTarget, Target, UniMessage

from .utils import run_single_battle
from .models import DragonContest, DragonContestPlayer, ContestStatus

async def run_contest(contest_id: int):
    async with get_session() as sess:
        try:
            sess.sync_session.expire_on_commit = False
        except Exception:
            try:
                sess.expire_on_commit = False  # type: ignore[attr-defined]
            except Exception:
                pass
        contest = await sess.get(DragonContest, contest_id)
        if not contest:
            return
        if contest.status != ContestStatus.RUNNING.value:
            return
        current_round = contest.current_round or 1
        try:
            target: MsgTarget = Target.load(contest.target)
        except Exception:
            logger.opt(colors=True).error(
                f"<red>比赛ID {contest_id} 的目标反序列化失败,比赛取消</red>"
            )
            contest.status = ContestStatus.FINISHED.value
            await sess.commit()
            return
        try:
            bot = get_bot(target.self_id)
        except Exception:
            logger.opt(colors=True).warning("<yellow>未找到可用的机器人实例,此任务将被跳过</yellow>")
            contest.status = ContestStatus.FINISHED.value
            await sess.commit()
            return
        players = (
            await sess.scalars(
                select(DragonContestPlayer)
                .where(
                    DragonContestPlayer.contest_id == contest_id,
                    DragonContestPlayer.eliminated.is_(False),
                )
            )
        ).all()
        if len(players) < 2:
            await UniMessage.text("比赛人数不足,比赛取消").send(target=target, bot=bot)
            contest.status = ContestStatus.FINISHED.value
            await sess.commit()
            return
        await UniMessage.text(
            f"龙龙大赛开始,本次参赛人数为: {len(players)}"
        ).send(target=target, bot=bot)
        round_no = current_round
        while True:
            contest_now = await sess.get(DragonContest, contest_id)
            if not contest_now:
                break
            if contest_now.status != ContestStatus.RUNNING.value:
                break
            contest = contest_now
            alive_players = (
                await sess.scalars(
                    select(DragonContestPlayer)
                    .where(
                        DragonContestPlayer.contest_id == contest_id,
                        DragonContestPlayer.eliminated.is_(False),
                    )
                )
            ).all()
            if len(alive_players) <= 1:
                break
            await UniMessage.text(
                f"第 {round_no} 轮比赛开始,当前剩余选手: {len(alive_players)}"
            ).send(target=target, bot=bot)
            for i in range(0, len(alive_players), 2):
                if i + 1 >= len(alive_players):
                    await UniMessage.text(
                        f"选手 {alive_players[i].dragon_name} 获得轮空,直接晋级下一轮"
                    ).send(target=target, bot=bot)
                    continue
                p1 = alive_players[i]
                p2 = alive_players[i + 1]
                winner, loser, reason = await run_single_battle(p1, p2, round_no)
                loser.eliminated = True
                sess.add(loser)
                await UniMessage.text(
                    f"对战结果：\n"
                    f"选手1：{p1.dragon_name}\n"
                    f"选手2：{p2.dragon_name}\n"
                    f"获胜者：{winner.dragon_name}\n"
                    f"失败者：{loser.dragon_name}\n"
                    f"理由：{reason}\n"
                    ).send(target=target, bot=bot)
                await sess.commit()
            round_no += 1
            contest.current_round = round_no
            sess.add(contest)
            await sess.commit()
        champion = (
            await sess.scalars(
                select(DragonContestPlayer)
                .where(
                    DragonContestPlayer.contest_id == contest_id,
                    DragonContestPlayer.eliminated.is_(False),
                )
            )
        ).first()
        if champion:
            await UniMessage.text(
                "龙龙大赛圆满结束\n"
                f"本届龙龙大赛冠军为: {champion.dragon_name}!"
                ).send(target=target, bot=bot)
        contest.status = ContestStatus.FINISHED.value
        sess.add(contest)
        await sess.commit()
