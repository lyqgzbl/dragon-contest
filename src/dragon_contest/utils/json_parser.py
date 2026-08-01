import json
import re
from typing import Any


def _scan_valid_json_prefix(cleaned: str, cut_idx: int) -> tuple[bool, list[str]]:
    cur_stack: list[str] = []
    in_str = False
    esc = False
    for i in range(cut_idx):
        c = cleaned[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c in "{[":
                cur_stack.append(c)
            elif c in "}]":
                expected_open = "{" if c == "}" else "["
                if cur_stack and cur_stack[-1] == expected_open:
                    cur_stack.pop()
                else:
                    return False, []
    return not in_str, cur_stack


def _reconstruct_closing_json(cleaned: str) -> dict | list | None:
    for cut_idx in range(len(cleaned), 0, -1):
        valid_prefix, cur_stack = _scan_valid_json_prefix(cleaned, cut_idx)
        if valid_prefix and cur_stack:
            closing = "".join(
                "}" if item == "{" else "]" for item in reversed(cur_stack)
            )
            candidate = cleaned[:cut_idx] + closing
            try:
                data = json.loads(candidate, strict=False)
                if isinstance(data, (dict, list)):
                    return data
            except Exception:
                pass
    return None


def _repair_json_data(s: str) -> dict | list | None:
    cleaned = re.sub(r"^```(?:json)?\s*", "", s.strip(), flags=re.I | re.M)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.I | re.M).strip()
    if not cleaned:
        return None

    try:
        data = json.loads(cleaned, strict=False)
        if isinstance(data, (dict, list)):
            return data
    except Exception:
        pass

    try:
        decoder = json.JSONDecoder(strict=False)
        start_idx = cleaned.find("{")
        if start_idx == -1:
            start_idx = cleaned.find("[")
        if start_idx != -1:
            data, _ = decoder.raw_decode(cleaned[start_idx:])
            if isinstance(data, (dict, list)):
                return data
    except Exception:
        pass

    return _reconstruct_closing_json(cleaned)


def _find_json_bracket_sub(cleaned: str, sec_pos: int) -> str | None:
    start_idx = cleaned.find("[", sec_pos)
    if start_idx == -1:
        return None
    bracket_count = 0
    end_idx = -1
    for i in range(start_idx, len(cleaned)):
        if cleaned[i] == "[":
            bracket_count += 1
        elif cleaned[i] == "]":
            bracket_count -= 1
            if bracket_count == 0:
                end_idx = i + 1
                break
    return cleaned[start_idx:end_idx] if end_idx != -1 else None


def _extract_sections_array(cleaned: str) -> list | None:
    sec_pos = cleaned.find('"sections"')
    if sec_pos == -1:
        sec_pos = cleaned.find("'sections'")
    if sec_pos == -1:
        return None
    sec_str = _find_json_bracket_sub(cleaned, sec_pos)
    if not sec_str:
        return None
    res = _repair_json_data(sec_str)
    if isinstance(res, list):
        return res
    try:
        import ast

        data = ast.literal_eval(sec_str)
        return data if isinstance(data, list) else None
    except Exception:
        return None


def _regex_extract_json(cleaned: str) -> dict | None:
    extracted: dict[str, Any] = {}
    winner_match = re.search(
        r'["\']?winner["\']?\s*[:；=]?\s*["\']?(p1|p2)["\']?', cleaned, re.I
    )
    if winner_match:
        extracted["winner"] = winner_match.group(1).lower()

    reason_match = re.search(
        r'["\']?reason["\']?\s*[:；=]?\s*["\'](.*?)["\']\s*,\s*["\']?(?:title|subtitle|columns|sections)["\']?',
        cleaned,
        re.S,
    )
    if not reason_match:
        reason_match = re.search(
            r'["\']?reason["\']?\s*[:；=]?\s*["\']?([^"\'\n\}]+)', cleaned
        )
    if reason_match:
        extracted["reason"] = reason_match.group(1).strip()

    sections_data = _extract_sections_array(cleaned)
    if sections_data is not None:
        extracted["sections"] = sections_data

    return extracted if "winner" in extracted else None


def _try_raw_decode(cleaned: str) -> dict | None:
    res = _repair_json_data(cleaned)
    if isinstance(res, dict):
        return res
    return None


def _parse_ai_json_response(content: str) -> dict | None:
    cleaned = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.I | re.M)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.I | re.M).strip()

    res = _repair_json_data(cleaned)
    if isinstance(res, dict):
        return res

    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        json_str = match.group(0)
        res = _repair_json_data(json_str)
        if isinstance(res, dict):
            return res

        try:
            import ast

            data = ast.literal_eval(json_str)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return _regex_extract_json(cleaned)
