import html
from pathlib import Path
from typing import cast

from nonebot import get_plugin_config
from nonebot.log import logger
from nonebot_plugin_htmlrender import md_to_pic

from ..config import Config

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
    reason = _cmp_clean_text(compare_data.get("reason", "裁判宣判了胜利"))
    return [
        {
            "title": "",
            "rows": [
                [
                    {"title": "", "content": "终局宣判"},
                    {"title": "获胜理由", "content": reason},
                    {"title": "败者陈词", "content": "——"},
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
        parts.append(f'<th class="cmp-head cmp-col-{idx}">{col_text}</th>')
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
    footer_text = _cmp_escape("Designed by lyqgzbl & Powered by dragon-contest")
    parts.append(f'<div class="cmp-footer">{footer_text}</div>')
    return "\n".join(parts)


async def _cmp_render_markdown(markdown: str) -> bytes:
    css_file = (
        Path(__file__).parent.parent
        / "templates"
        / ("compare_dark.css" if plugin_config.dc_image_is_dark else "compare.css")
    )
    kwargs: dict = {"width": 1000}
    if css_file.exists():
        kwargs["css_path"] = str(css_file)
    return await md_to_pic(markdown, **kwargs)


async def generate_comparison_image(compare_data: dict) -> bytes:
    title = _cmp_clean_text(compare_data.get("title", "龙龙大赛")) or "龙龙大赛"
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
