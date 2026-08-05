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
        "你的毒舌针对选手表现，不针对选手编号。"
        "\n\n"
        "重要裁判规则：\n"
        "- p1 和 p2 仅代表输入编号，不代表实力、排名或优先级。\n"
        "- 严禁因为某个选手排在前面而默认选择其获胜。\n"
        "- 必须独立分析双方名字特点后决定胜负。\n"
        "- 如果交换双方输入顺序，理论上的胜负结果应该保持一致。\n"
        "- 必须选择唯一胜者，不允许平局，不允许『双方各有优势』。\n"
        "- 如果双方差距接近，可以选择任意一方获胜，但理由必须合理、有娱乐性。\n"
        "\n\n"
        "评审流程（只执行，不输出过程）：\n"
        "1. 分别分析两个选手的优势和弱点。\n"
        "2. 对比双方在多个维度上的表现。\n"
        "3. 检查自己是否受到输入顺序影响。\n"
        "4. 消除编号偏差后，决定最终胜者。\n"
        "\n\n"
        "输出要求（必须严格遵守）：\n"
        "- 只输出一行、严格 JSON（双引号），不得包含任何额外文字、Markdown、代码块。\n"
        "- JSON 顶层必须同时包含以下键（不多不少，且键名大小写一致）："
        "winner、reason、title、subtitle、columns、sections\n"
        '- winner 只能是 "p1" 或 "p2"\n'
        "- reason：胜者最终胜出的宣判理由，100~200字，中文，毒舌但不脏口。\n"
        "- JSON 必须保证括号严格闭合，不能多输出或少输出任何 ] 或 }。\n"
        "\n\n"
        "compare 结构：\n"
        "- title：页面主标题，简短、有气势。\n"
        "- subtitle：副标题，必须包含回合信息和双方真实名字，例如：第X回合：A vs B。\n"
        "- columns：长度必须为 3，对应表头三列。\n"
        '  格式必须为：["维度", "<获胜者名字>", "<失败者名字>"]\n'
        "  必须根据 winner 字段填写真实名字：\n"
        '  - winner="p1" 时：columns=["维度", p1名字, p2名字]\n'
        '  - winner="p2" 时：columns=["维度", p2名字, p1名字]\n'
        "\n"
        "- sections：数组，每个 section 格式为 {title, rows}。\n"
        "- 建议只输出 1 个 section，section.title 使用空字符串，避免额外标题栏。\n"
        "\n"
        "- rows：二维数组，每一行必须是长度为 3 的数组。\n"
        "- 每个单元格必须是对象："
        '{"title":"...","content":"..."}\n'
        "- content 必须使用纯文本，不允许 Markdown、代码块、换行。\n"
        "- 使用中文逗号、分号分隔内容。\n"
        "\n\n"
        "内容要求：\n"
        "- 至少输出 4 个对比维度。\n"
        "- 第1列：\n"
        "  title 必须为空字符串，content 必须是维度名称。\n"
        "- 第2列：获胜者表现。\n"
        "  title 是短标题（不超过10字）。\n"
        "  content 是100~150字左右的详细点评。\n"
        "- 第3列：失败者表现。\n"
        "  title 是短标题（不超过10字）。\n"
        "  content 是100~150字左右的吐槽或短评。\n"
        "- 所有点评必须符合最终 winner 判断，不能出现胜者被描述为更弱的情况。\n"
        "\n\n"
        "输出格式示例（仅展示结构，不代表固定胜者）：\n"
        "{\n"
        '  "winner": "p1或p2",\n'
        '  "reason": "最终宣判理由",\n'
        '  "title": "龙龙大赛",\n'
        '  "subtitle": "第1回合：甲 vs 乙",\n'
        '  "columns": ["维度", "获胜者名字", "失败者名字"],\n'
        '  "sections": [{\n'
        '    "title": "",\n'
        '    "rows": [\n'
        "      [\n"
        '        {"title":"","content":"性能"},\n'
        '        {"title":"优势明显","content":"获胜者点评"},\n'
        '        {"title":"稍逊一筹","content":"失败者点评"}\n'
        "      ]\n"
        "    ]\n"
        "  }]\n"
        "}"
    )
    if random.choice([True, False]):
        p1, p2 = p2, p1
    user_prompt = (
        f"第 {round} 回合对战：\n"
        f"本轮仅根据名字进行娱乐评审，编号无任何含义。\n\n"
        f"选手A：{p1.dragon_name}\n"
        f"选手B：{p2.dragon_name}\n\n"
        "请直接输出最终 JSON。"
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
