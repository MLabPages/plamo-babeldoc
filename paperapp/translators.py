from __future__ import annotations

import csv

from . import bdenv  # noqa: F401  (BabelDOC より先に読み込む)
from babeldoc.translator.translator import OpenAITranslator

from .config import GLOSSARY_FILE

# 翻訳呼び出しの成功・失敗数（失敗を見逃さないために worker が確認する）
STATS = {"ok": 0, "fail": 0, "last_error": ""}


def _counted(fn):
    def wrapper(self, text, *args, **kwargs):
        if text is None:
            return fn(self, text, *args, **kwargs)
        try:
            out = fn(self, text, *args, **kwargs)
        except NotImplementedError:
            raise
        except Exception as e:
            STATS["fail"] += 1
            STATS["last_error"] = f"{type(e).__name__}: {e}"[:300]
            raise
        STATS["ok"] += 1
        return out

    return wrapper


def load_glossary() -> list[tuple[str, str]]:
    if not GLOSSARY_FILE.exists():
        return []
    terms = []
    with GLOSSARY_FILE.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            src = (row.get("source") or "").strip()
            tgt = (row.get("target") or "").strip()
            if src and tgt and not src.startswith("#"):
                terms.append((src, tgt))
    return sorted(terms, key=lambda t: -len(t[0]))


def _trim_repetition(text: str) -> str:
    """同じ文が繰り返された出力から、繰り返し部分を取り除く。"""
    import re

    parts = re.split(r"(?<=[。．！？!?])", text)
    seen: set[str] = set()
    out = []
    for p in parts:
        key = p.strip()
        if not key:
            continue
        if key in seen:
            break
        seen.add(key)
        out.append(p)
    return "".join(out).strip() or text


class PlamoTranslator(OpenAITranslator):
    """PLaMo 3 Translate 用。段落ごとに目標言語・常体・用語集を指定して送る。"""

    name = "plamo"

    def __init__(self, *args, **kwargs):
        self.glossary = load_glossary()
        self.form = "plain"
        super().__init__(*args, **kwargs)
        self.add_cache_impact_parameters("glossary", repr(self.glossary))
        self.add_cache_impact_parameters("length_guard", "v1")

    @_counted
    def do_translate(self, text, rate_limit_params=None) -> str:
        # 訳文が繰り返しで暴走しないよう、原文の長さに応じて出力上限を設ける
        limit = min(3000, int(len(text) * 0.9) + 160)
        attempts = [
            {},
            {"repeat_penalty": 1.15, "dry_multiplier": 0.8, "dry_base": 1.75, "dry_allowed_length": 3},
        ]
        result = ""
        for extra in attempts:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                max_tokens=limit,
                messages=self.prompt(text),
                extra_body=extra,
            )
            self.update_token_count(response)
            choice = response.choices[0]
            result = (choice.message.content or "").strip()
            if choice.finish_reason != "length":
                return result
        return _trim_repetition(result)

    def prompt(self, text):
        lower = text.lower()
        lines = ["[plamo-translate]", f"target_lang={self.lang_out}", f"form={self.form}"]
        for src, tgt in self.glossary:
            if src.lower() in lower:
                lines.append(f"glossary={src} => {tgt}")
        lines.append("---")
        return [
            {"role": "system", "content": "\n".join(lines)},
            {"role": "user", "content": text if text.strip() else " "},
        ]

    def do_llm_translate(self, text, rate_limit_params=None):
        # 翻訳専用モデルなので、一括 JSON 翻訳や自動用語抽出は使わせない
        raise NotImplementedError


class GeminiTranslator(OpenAITranslator):
    """Gemini（OpenAI 互換 API）。思考トークンを抑えて出力切れを防ぐ。"""

    name = "gemini"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_body["reasoning_effort"] = "low"
        self.add_cache_impact_parameters("reasoning_effort", "low")

    @_counted
    def do_translate(self, text, rate_limit_params=None):
        return super().do_translate(text, rate_limit_params)

    @_counted
    def do_llm_translate(self, text, rate_limit_params=None):
        return super().do_llm_translate(text, rate_limit_params)
