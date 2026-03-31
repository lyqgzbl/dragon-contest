import re
import json
import random
import html
from datetime import datetime
from pathlib import Path
from typing import cast

from sqlalchemy import select
from nonebot.log import logger
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_apscheduler import scheduler
from nonebot import get_plugin_config, get_driver
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


def _cmp_clean_text(value: object) -> str:
    text = str(value or "").strip()
    return " ".join(text.splitlines()).strip()


def _cmp_escape(text: str) -> str:
    return html.escape(text, quote=True)


def _cmp_normalize_columns(value: object) -> list[str]:
    columns = [_cmp_clean_text(v) for v in value] if isinstance(value, list) else []
    if len(columns) < 3:
        columns += [""] * (3 - len(columns))
    return columns[:3]


def _cmp_normalize_cell(cell: object) -> dict[str, str]:
    if isinstance(cell, dict):
        cell_dict = cast(dict[str, object], cell)
        return {
            "title": _cmp_clean_text(cell_dict.get("title", "")),
            "content": _cmp_clean_text(cell_dict.get("content", "")),
        }
    return {"title": "", "content": _cmp_clean_text(cell)}


def _cmp_normalize_row(row: object) -> list[dict[str, str]]:
    if not isinstance(row, list):
        return []
    cells = [_cmp_normalize_cell(cell) for cell in row[:3]]
    if len(cells) < 3:
        cells += [{"title": "", "content": ""}] * (3 - len(cells))
    return cells


def _cmp_normalize_sections(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    sections: list[dict[str, object]] = []
    for section in value:
        if not isinstance(section, dict):
            continue
        section_data = cast(dict[str, object], section)
        rows_value = section_data.get("rows", [])
        rows = []
        if isinstance(rows_value, list):
            for row in rows_value:
                normalized = _cmp_normalize_row(row)
                if normalized:
                    rows.append(normalized)
        sections.append(
            {
                "title": _cmp_clean_text(section_data.get("title", "")),
                "rows": rows,
            }
        )
    return sections


def _cmp_default_sections(compare_data: dict) -> list[dict[str, object]]:
    winner = _cmp_clean_text(compare_data.get("winner", ""))
    reason = _cmp_clean_text(compare_data.get("reason", ""))
    return [
        {
            "title": "",
            "rows": [
                [
                    {"title": "", "content": "裁判裁决"},
                    {"title": "获胜者", "content": winner},
                    {"title": "失败者", "content": reason},
                ]
            ],
        }
    ]


def _cmp_render_header(parts: list[str], title: str, subtitle: str):
    if title:
        parts.append(f"<h1>{_cmp_escape(title)}</h1>")
    if subtitle:
        parts.append(
            f'<h2><span class="cmp-subtitle">{_cmp_escape(subtitle)}</span></h2>'
        )


def _cmp_render_table_head(parts: list[str], columns: list[str]):
    parts.append("<thead><tr>")
    for idx, col in enumerate(columns):
        col_text = _cmp_escape(_cmp_clean_text(col))
        parts.append(
            f'<th class="cmp-head cmp-col-{idx}">{col_text}</th>'
        )
    parts.append("</tr></thead>")


def _cmp_render_rows(parts: list[str], rows: object):
    parts.append("<tbody>")
    if isinstance(rows, list):
        for row in rows:
            cells = _cmp_normalize_row(row)
            if not cells:
                continue
            parts.append("<tr>")
            for idx, cell in enumerate(cells):
                parts.append(f'<td class="cmp-cell cmp-col-{idx}">')
                parts.append(
                    f'<div class="cmp-cell-title">{_cmp_escape(cell["title"])}</div>'
                )
                parts.append(
                    '<div class="cmp-cell-content">'
                    f"{_cmp_escape(cell['content'])}"
                    "</div>"
                )
                parts.append("</td>")
            parts.append("</tr>")
    parts.append("</tbody>")


def _cmp_build_html(
    *,
    title: str,
    subtitle: str,
    columns: list[str],
    sections: list[dict[str, object]],
) -> str:
    parts: list[str] = []
    _cmp_render_header(parts, title, subtitle)
    parts.append('<div class="cmp-container">')
    for section in sections:
        parts.append('<div class="cmp-card">')
        section_title = _cmp_clean_text(section.get("title", ""))
        if section_title:
            title_html = _cmp_escape(section_title)
            parts.append(f'<div class="cmp-card-title">{title_html}</div>')
        parts.append('<table class="cmp-table">')
        _cmp_render_table_head(parts, columns)
        _cmp_render_rows(parts, section.get("rows", []))
        parts.append("</table>")
        parts.append("</div>")
    parts.append("</div>")
    return "\n".join(parts)


async def _cmp_render_markdown(markdown: str) -> bytes:
    css_file = Path(__file__).parent / "templates" / "compare.css"
    kwargs: dict = {"width": 1000}
    if css_file.exists():
        kwargs["css_path"] = str(css_file)
    return await md_to_pic(markdown, **kwargs)


async def get_contest_champion(sess: async_scoped_session) -> str | None:
    champion = await sess.scalar(
        select(DragonContestPlayer.dragon_name)
        .join(DragonContest, DragonContest.id == DragonContestPlayer.contest_id)
        .where(DragonContest.status == ContestStatus.FINISHED.value)
        .order_by(DragonContest.start_ts.desc())
    )
    return champion


async def generate_comparison_image(compare_data: dict) -> bytes:
    title = "龙龙大赛"
    subtitle = _cmp_clean_text(compare_data.get("subtitle", ""))
    columns = _cmp_normalize_columns(compare_data.get("columns"))
    sections = _cmp_normalize_sections(compare_data.get("sections"))
    if not any(columns):
        columns = ["维度", "获胜者", "失败者"]
    if not sections:
        sections = _cmp_default_sections(compare_data)

    html_content = _cmp_build_html(
        title=title,
        subtitle=subtitle,
        columns=columns,
        sections=sections,
    )
    try:
        return await _cmp_render_markdown(html_content)
    except Exception:
        logger.exception("生成对比图片失败")
        return await _cmp_render_markdown("<h1>对比图生成失败</h1>")


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

    from . import openai_handler

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
        "{"
        '"winner":"p1",'
        '"reason":"(100~200字终局宣判)",'
        '"title":"龙龙大赛",'
        '"subtitle":"第1回合：甲 vs 乙",'
        '"columns":["维度","(获胜者名字)","(失败者名字)"],'
        '"sections":[{'
        '  "title":"",'
        '  "rows":[['
        '    {"title":"","content":"性能"},'
        '    {"title":"高效执行","content":"..."},'
        '    {"title":"略显吃力","content":"..."}'
        "  ]]"
        "}]"
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
        content = await openai_handler.get_response(messages)
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
    match = re.search(r"\{.*\}", content, flags=re.S)
    if not match:
        winner, loser = random.sample([p1, p2], 2)
        winner_flag = "p1" if winner is p1 else "p2"
        reason = f"AI 输出格式错误,随机决出胜负。原始输出：{content}"
        return (
            winner,
            loser,
            reason,
            _default_compare_data(winner_flag=winner_flag, reason=reason),
        )
    try:
        data = json.loads(match.group(0))
    except Exception:
        winner, loser = random.sample([p1, p2], 2)
        winner_flag = "p1" if winner is p1 else "p2"
        reason = f"输出解析失败,随机决出胜负。原始输出：{content}"
        return (
            winner,
            loser,
            reason,
            _default_compare_data(winner_flag=winner_flag, reason=reason),
        )
    if not isinstance(data, dict):
        data = {}
    winner_flag = str(data.get("winner", "")).strip().lower()
    reason = str(data.get("reason", "")).strip()
    if not reason:
        reason = "AI 未给出明确理由"
    compare_data = dict(data)
    compare_data["winner"] = winner_flag
    compare_data["reason"] = reason
    compare_data.setdefault("title", "龙龙大赛")
    compare_data["subtitle"] = f"第 {round} 回合：{p1.dragon_name} vs {p2.dragon_name}"
    compare_data.setdefault("columns", ["维度", "获胜者", "失败者"])
    compare_data.setdefault("sections", [])
    if winner_flag == "p1":
        return p1, p2, reason, compare_data
    elif winner_flag == "p2":
        return p2, p1, reason, compare_data
    winner, loser = random.sample([p1, p2], 2)
    winner_flag = "p1" if winner is p1 else "p2"
    reason = f"AI 输出胜者不明确,随机决出胜负。原始输出：{content}"
    return (
        winner,
        loser,
        reason,
        _default_compare_data(winner_flag=winner_flag, reason=reason),
    )


@driver.on_startup
async def restore_contest_start_jobs():
    async with get_session() as sess:
        now_ts = int(datetime.now().timestamp())
        contests = await sess.scalars(
            select(DragonContest).where(
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
