"""utils 门面包。"""

from .battle import BattlePlayer, run_single_battle
from .json_parser import (
    _extract_sections_array,
    _find_json_bracket_sub,
    _parse_ai_json_response,
    _reconstruct_closing_json,
    _regex_extract_json,
    _repair_json_data,
    _scan_valid_json_prefix,
    _try_raw_decode,
)
from .render import (
    _cmp_build_html,
    _cmp_clean_text,
    _cmp_default_sections,
    _cmp_escape,
    _cmp_normalize_cell,
    _cmp_normalize_columns,
    _cmp_normalize_row,
    _cmp_normalize_sections,
    _cmp_render_header,
    _cmp_render_markdown,
    _cmp_render_rows,
    _cmp_render_table_head,
    generate_comparison_image,
)
from .scheduler import (
    on_contest_start,
    register_contest_start_job,
    restore_contest_start_jobs,
)
from .service import (
    _contest_signup_locks,
    get_active_contest,
    get_contest_champion,
    get_contest_signup_lock,
    get_current_contest,
    get_or_create_config,
    get_signup_contest,
)

__all__ = [
    # battle
    "BattlePlayer",
    "_cmp_build_html",
    # render
    "_cmp_clean_text",
    "_cmp_default_sections",
    "_cmp_escape",
    "_cmp_normalize_cell",
    "_cmp_normalize_columns",
    "_cmp_normalize_row",
    "_cmp_normalize_sections",
    "_cmp_render_header",
    "_cmp_render_markdown",
    "_cmp_render_rows",
    "_cmp_render_table_head",
    # service
    "_contest_signup_locks",
    "_extract_sections_array",
    "_find_json_bracket_sub",
    "_parse_ai_json_response",
    "_reconstruct_closing_json",
    "_regex_extract_json",
    "_repair_json_data",
    # json_parser
    "_scan_valid_json_prefix",
    "_try_raw_decode",
    "generate_comparison_image",
    "get_active_contest",
    "get_contest_champion",
    "get_contest_signup_lock",
    "get_current_contest",
    "get_or_create_config",
    "get_signup_contest",
    "on_contest_start",
    # scheduler
    "register_contest_start_job",
    "restore_contest_start_jobs",
    "run_single_battle",
]
