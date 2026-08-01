import random
from typing import Protocol, TypeVar

from nonebot.log import logger

from .json_parser import _parse_ai_json_response


class BattlePlayer(Protocol):
    @property
    def dragon_name(self) -> str: ...


P = TypeVar("P", bound=BattlePlayer)


async def run_single_battle(
    p1: P,
    p2: P,
    round: int,
) -> tuple[P, P, str, dict]:
    def _default_compare_data(*, winner_flag: str, reason: str) -> dict:
        winner_name = p1.dragon_name if winner_flag == "p1" else p2.dragon_name
        loser_name = p2.dragon_name if winner_flag == "p1" else p1.dragon_name
        title = "龙龙大赛"
        subtitle = f"第 {round} 回合：{p1.dragon_name} vs {p2.dragon_name}"
        columns = ["维度", winner_name, loser_name]
        rows = [
            [
                {"title": "", "content": "裁判裁决"},
                {"title": "终局宣判", "content": reason},
                {"title": "败者陈词", "content": "——"},
            ]
        ]
        return {
            "winner": winner_flag,
            "reason": reason,
            "title": title,
            "subtitle": subtitle,
            "columns": columns,
            "sections": [{"title": "", "rows": rows}],
        }

    from .. import openai_handler

    if openai_handler is None:
        winner, loser = random.sample([p1, p2], 2)
        winner_flag = "p1" if winner is p1 else "p2"
        reason = "未配置 OpenAI,随机决出胜负"
        return (
            winner,
            loser,
            reason,
            _default_compare_data(winner_flag=winner_flag, reason=reason),
        )
    system_prompt = (
        "你是『龙龙大赛』首席毒舌裁判：偏心、刻薄、高攻击性的、爱抬杠，但要风趣幽默。"
        "你要基于选手名字做对比评审（不需要真实背景），必须选出唯一胜者，不能平局、不能各有优势。"
        "\n\n输出要求（必须严格遵守）：\n"
        "- 只输出一行、严格 JSON（双引号），不得包含任何额外文字/Markdown/代码块\n"
        "- JSON 顶层必须同时包含以下键（不多不少，且键名大小写一致）："
        "winner、reason、title、subtitle、columns、sections\n"
        '- winner 只能是 "p1" 或 "p2"\n'
        "- reason：胜者胜出的终局理由，100~200 字，中文，毒舌但不脏口\n"
        "- 请特别注意 JSON 括号闭合语法，"
        "严格匹配括号，绝不能多输出任何多余的 ] 或 } 闭合符！\n"
        "\ncompare 结构（用于 compare.md + compare.css 渲染）：\n"
        "- title：页面主标题（简短有气势）\n"
        "- subtitle：副标题（包含回合信息与双方名字，例如：第X回合：A vs B）\n"
        "- columns：长度必须为 3，分别对应表头 3 列（CSS 仅对列索引做颜色区分）\n"
        '  必须为：["维度", "<获胜者名字>", "<失败者名字>"]\n'
        "  且必须根据 winner 字段填入真实名字：\n"
        '  - winner="p1" 时：columns=["维度", p1名字, p2名字]\n'
        '  - winner="p2" 时：columns=["维度", p2名字, p1名字]\n'
        "- sections：数组，每个 section 形如 {title, rows}\n"
        "  为贴合样式，建议只输出 1 个 section，且 section.title 设为空字符串"
        "（避免额外标题栏）。\n"
        "- rows：二维数组；每一行必须是长度为 3 的数组（对应 3 列）；"
        "每个单元格必须是对象"
        '  {"title":"...","content":"..."}\n'
        "- content 用纯文本即可；不要 Markdown 列表、不要代码块、不要换行"
        "（用中文逗号/分号分隔即可）\n"
        "\n内容格式（贴合示例图）：\n"
        "- 至少 4 行维度（例如：性能/平台支持/语言特性/应用领域，"
        "或任意你自拟的对比维度）\n"
        "- 每行第 1 列：title 必须为空字符串，content 必须是该行的『维度名』\n"
        "- 每行第 2 列（获胜者）：title 是一句短标题（<=10字），"
        "content 是一段较长点评（最少100字最多150字）\n"
        "- 每行第 3 列（失败者）：title 是一句短标题（<=10字），"
        "content 是一段较长吐槽/短评（最少100字最多150字）\n"
        "- 所有点评必须与 winner 的胜负关系一致，不能自相矛盾\n"
        "\n输出示例（仅示例结构，不要照抄内容）：\n"
        "{\n"
        '  "winner": "p1",\n'
        '  "reason": "(100~200字终局宣判)",\n'
        '  "title": "龙龙大赛",\n'
        '  "subtitle": "第1回合：甲 vs 乙",\n'
        '  "columns": ["维度", "(获胜者名字)", "(失败者名字)"],\n'
        '  "sections": [{\n'
        '    "title": "",\n'
        '    "rows": [[\n'
        '      {"title": "", "content": "性能"},\n'
        '      {"title": "高效执行", "content": "..."},\n'
        '      {"title": "略显吃力", "content": "..."}\n'
        "    ]]\n"
        "  }]\n"
        "}"
    )
    user_prompt = (
        f"第 {round} 回合对战：\n"
        f"选手1：{p1.dragon_name}\n"
        f"选手2：{p2.dragon_name}\n\n"
        "请直接给出胜者与理由。"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        content = await openai_handler.get_response(
            messages, response_format={"type": "json_object"}
        )
    except Exception:
        logger.exception("调用 OpenAI 接口失败,随机决出胜负")
        winner, loser = random.sample([p1, p2], 2)
        winner_flag = "p1" if winner is p1 else "p2"
        reason = "调用 OpenAI 接口失败,随机决出胜负"
        return (
            winner,
            loser,
            reason,
            _default_compare_data(winner_flag=winner_flag, reason=reason),
        )
    data = _parse_ai_json_response(content)
    logger.debug(f"AI 输出解析结果: {data}, 原始输出: {content}")
    if data is None:
        winner, loser = random.sample([p1, p2], 2)
        winner_flag = "p1" if winner is p1 else "p2"
        reason = f"输出解析失败,随机决出胜负。原始输出：{content}"
        return (
            winner,
            loser,
            reason,
            _default_compare_data(winner_flag=winner_flag, reason=reason),
        )
    winner_flag = str(data.get("winner", "")).strip().lower()
    reason = str(data.get("reason", "")).strip()
    if not reason:
        reason = "AI 未给出明确理由"
    compare_data = dict(data)
    compare_data["winner"] = winner_flag
    compare_data["reason"] = reason
    compare_data.setdefault("title", "龙龙大赛")
    compare_data["subtitle"] = f"第 {round} 回合：{p1.dragon_name} vs {p2.dragon_name}"

    if winner_flag == "p1":
        winner_name, loser_name = p1.dragon_name, p2.dragon_name
        winner_obj, loser_obj = p1, p2
    elif winner_flag == "p2":
        winner_name, loser_name = p2.dragon_name, p1.dragon_name
        winner_obj, loser_obj = p2, p1
    else:
        winner_obj, loser_obj = random.sample([p1, p2], 2)
        winner_flag = "p1" if winner_obj is p1 else "p2"
        winner_name, loser_name = winner_obj.dragon_name, loser_obj.dragon_name
        reason = f"AI 输出胜者不明确,随机决出胜负。原始输出：{content}"
        return (
            winner_obj,
            loser_obj,
            reason,
            _default_compare_data(winner_flag=winner_flag, reason=reason),
        )

    compare_data["columns"] = ["维度", winner_name, loser_name]
    compare_data.setdefault("sections", [])
    return winner_obj, loser_obj, reason, compare_data
