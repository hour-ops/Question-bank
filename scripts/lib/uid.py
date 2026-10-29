"""question_uid 的唯一入口（阶段 0 规格）。

规则：
  generate_uid(subject, source_url, stem) = sha256(f"{subject}:{source_url}:{stem[:50]}")[:16]

⚠️ 因为 source_url 参与哈希，**同一道题从两个源抓到会得到两个 uid**。
因此额外提供 content_fingerprint()：不受 source_url 影响的"跨源同题"二级指纹，
落库前用它查重（见决策记录第 6 节第 9 条）。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# 全角/半角标点与常见符号（归一化时剔除，避免同题因标点差异被判为不同题）
_PUNCT_RE = re.compile(r"[\s，。、；：？！“”‘’（）【】《》〈〉,.。;:?！\"'()\[\]<>~—\-_/\\|+*=&%$#@^`{}]+")


def normalize_stem(stem: str) -> str:
    """归一化题干：NFKC 全角转半角 → 去空白 → 去标点。用于跨源同题判定。"""
    if not stem:
        return ""
    s = unicodedata.normalize("NFKC", stem)
    s = _PUNCT_RE.sub("", s)
    return s.strip().lower()


def generate_uid(subject: str, source_url: str, stem: str) -> str:
    """源内唯一 uid：sha256(f"{subject}:{source_url}:{stem[:50]}")[:16]"""
    raw = f"{subject}:{source_url}:{(stem or '')[:50]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def content_fingerprint(subject: str, stem: str) -> str:
    """跨源同题指纹：sha256(f"{subject}:{归一化题干}")[:16]，与 source_url 无关。"""
    raw = f"{subject}:{normalize_stem(stem)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


__all__ = ["generate_uid", "content_fingerprint", "normalize_stem"]
