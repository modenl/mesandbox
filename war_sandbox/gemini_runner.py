import json
import os
import shutil
import subprocess
from functools import lru_cache
from typing import Any, Dict, List, Optional


class GeminiError(RuntimeError):
    pass


def _gemini_executable() -> str:
    candidates = [
        os.environ.get("GEMINI_BIN"),
        shutil.which("gemini"),
        "/opt/homebrew/bin/gemini",
        "/usr/local/bin/gemini",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    raise GeminiError("Could not locate gemini executable")


def extract_json_value(text: str) -> Any:
    text = text.strip()
    if not text:
        raise GeminiError("Empty Gemini response")

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    decoder = json.JSONDecoder()
    for start in range(len(text)):
        if text[start] not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[start:])
            return value
        except json.JSONDecodeError:
            continue
    raise GeminiError("Could not find JSON value in Gemini response")


def extract_json_blob(text: str) -> Dict[str, Any]:
    value = extract_json_value(text)
    if not isinstance(value, dict):
        raise GeminiError("Expected JSON object in Gemini response")
    return value


def run_text_prompt(prompt: str, model: Optional[str] = None) -> str:
    cmd = [_gemini_executable(), "-p", prompt, "-o", "json"]
    if model:
        cmd.extend(["-m", model])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GeminiError(result.stderr.strip() or result.stdout.strip())

    outer = json.loads(result.stdout)
    return str(outer.get("response", "")).strip()


def run_structured_prompt(prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
    response = run_text_prompt(prompt, model=model)
    return extract_json_blob(response)


@lru_cache(maxsize=256)
def _translate_title_batch_cached(
    language: str,
    titles_json: str,
    model: Optional[str],
) -> tuple[str, ...]:
    titles = json.loads(titles_json)
    if not titles:
        return tuple()
    target_language = "Simplified Chinese" if language == "zh" else "English"
    prompt = f"""
Translate each news headline into {target_language}.

Rules:
- Preserve names, places, numbers, and military designations accurately.
- Do not add or remove claims.
- Keep each line concise and headline-like.
- Return one JSON object only.
- Format:
  {{
    "translations": [
      {{"index": 0, "text": "..."}}
    ]
  }}

Headlines:
{json.dumps(titles, ensure_ascii=False, indent=2)}
""".strip()
    payload = run_structured_prompt(prompt, model=model)
    translated = [""] * len(titles)
    for row in payload.get("translations", []):
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(titles):
            translated[index] = str(row.get("text", "")).strip()
    return tuple(translated)


def translate_news_titles(
    titles: List[str],
    language: str,
    model: Optional[str] = None,
) -> List[str]:
    if not titles:
        return []
    translations = list(
        _translate_title_batch_cached(
            language,
            json.dumps(titles, ensure_ascii=False),
            model,
        )
    )
    return [
        translations[index] if index < len(translations) and translations[index] else title
        for index, title in enumerate(titles)
    ]
