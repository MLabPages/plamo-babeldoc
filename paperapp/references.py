"""参考文献リストの項目かどうかを見分ける。"""

from __future__ import annotations

import html
import re

_TAGS = re.compile(r"<[^>]+>|\{\s*v\s*\d+\s*\}")
_YEAR = re.compile(r"(?<!\d)(19|20)\d{2}[a-z]?(?!\d)")
_NUM_START = re.compile(r"^\s*(\[\d{1,3}\]|\(\d{1,3}\)|\d{1,3}\.)\s+\S")
# 「Surname, A.」「Surname, Alice」「Surname A,」「van der Berg, J.」のような書き出し
_AUTHOR_START = re.compile(
    r"^\s*(?:\[\d{1,3}\]\s*|\d{1,3}\.\s+)?"
    r"(?:(?:van|von|de|der|den|da|di|le|la|du)\s+)*"
    r"[A-Z\u00C0-\u024F][A-Za-z\u00C0-\u024F'’\-]+"
    r"(?:\s[A-Z][A-Za-z\u00C0-\u024F'’\-]+)?"
    r"(?:,\s*(?:[A-Z]\.|[A-Z][a-z\u00C0-\u024F]+)|\s[A-Z]{1,3},)"
)
_INITIAL_START = re.compile(r"^\s*(?:\[\d{1,3}\]\s*|\d{1,3}\.\s+)?(?:[A-Z]\.\s?){1,3}[A-Z][a-z]+,")
_BIB_SIGNAL = re.compile(
    r"doi\.org|\bdoi:|https?://|\bet al\.|\bVol\.|\bvol\.|\bpp\.|\bIn:|\(Eds?\.\)|Journal|Proceedings|"
    r"\d+\s*\(\d+\)|\d+\s*[–\-]\s*\d+|Press\b|\bISBN",
)
# 「Luangrath, A.W.,」「Peck, J.,」のような姓＋イニシャル（本文中の引用 Krishna et al., 2024 には付かない）
_AUTHOR_INITIALS = re.compile(r"[A-Z\u00C0-\u024F][A-Za-z\u00C0-\u024F'’\-]+,\s(?:[A-Z]\.\s?-?){1,3}(?=[,&\s(]|$)")
_DOI = re.compile(r"doi\.org|\bdoi:", re.IGNORECASE)
_VOL_PAGES = re.compile(r"\d+\s*\(\d+\)|\d+\s*[–\-]\s*\d+|\bpp?\.\s*\d")
_BRACKET_NUM = re.compile(r"\[\d{1,3}\]")
_JP = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


def clean(text: str) -> str:
    return html.unescape(_TAGS.sub(" ", text)).strip()


def is_reference_entry(text: str) -> bool:
    t = clean(text)
    if len(t) < 25 or len(_JP.findall(t)) > 0.2 * len(t):
        return False
    n_doi = len(_DOI.findall(t))
    n_init = len(_AUTHOR_INITIALS.findall(t))
    n_years = len(_YEAR.findall(t))
    # 参考文献欄が数項目まとめて 1 段落になっている場合
    if len(t) > 600:
        per_k = 1000 / len(t)
        if n_doi * per_k >= 1.0 or (n_init >= 4 and n_init * per_k >= 1.5 and n_years >= 3):
            return True
        if len(t) > 1500:
            return _numbered_block(t, n_years)
    if _numbered_block(t, n_years):
        return True
    # 項目の途中で切れた断片（DOI と巻・号・ページがある短い段落）
    if len(t) < 600 and n_doi and _VOL_PAGES.search(t):
        return True
    head = t[:240]
    if not _YEAR.search(head):
        return False
    signals = len(_BIB_SIGNAL.findall(t))
    if _AUTHOR_START.match(t) and (signals >= 1 or re.search(r"\(\s*(19|20)\d{2}[a-z]?\s*\)", head)):
        return True
    if _INITIAL_START.match(t) and signals >= 1:
        return True
    if _NUM_START.match(t) and signals >= 2:
        return True
    return False


def _numbered_block(t: str, n_years: int) -> bool:
    """[2] 著者, “題名,” … のような番号つき（IEEE 形式）の参考文献が並んだ段落。"""
    return len(_BRACKET_NUM.findall(t)) >= 2 and n_years >= 2 and t.count("“") + t.count('"') >= 2
