"""Safety rules for learned correction pairs."""

from __future__ import annotations

import re

_EDGE_PUNCT = re.compile(r"^[^\w가-힣]+|[^\w가-힣]+$", re.UNICODE)
_NON_WORD = re.compile(r"[^\w가-힣]+", re.UNICODE)

_REFERENCE_STEMS = {
    "그",
    "이",
    "저",
    "그것",
    "이것",
    "저것",
    "그거",
    "이거",
    "저거",
    "그녀",
    "그분",
    "이분",
    "저분",
    "그사람",
    "이사람",
    "저사람",
    "그여자",
    "이여자",
    "저여자",
    "그여인",
    "이여인",
    "저여인",
    "그남자",
    "이남자",
    "저남자",
    "그아이",
    "이아이",
    "저아이",
    "그애",
    "이애",
    "저애",
    "나",
    "저",
    "너",
    "우리",
    "당신",
    "자기",
}

_REFERENCE_SUFFIXES = (
    "에게서는",
    "한테서는",
    "께서는",
    "이라는",
    "라는",
    "이라고",
    "라고",
    "처럼",
    "보다",
    "에게",
    "한테",
    "께서",
    "께",
    "에서",
    "으로",
    "부터",
    "까지",
    "밖에",
    "마저",
    "조차",
    "마다",
    "만큼",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "도",
    "만",
    "에",
    "와",
    "과",
    "로",
    "나",
    "야",
)


def clean_pair_text(text: str) -> str:
    """Strip punctuation around a learned pair candidate."""
    return _EDGE_PUNCT.sub("", text).strip()


def _compact(text: str) -> str:
    return _NON_WORD.sub("", clean_pair_text(text))


def is_contextual_reference(text: str) -> bool:
    """True for pronouns/demonstrative references that should stay local."""
    compact = _compact(text)
    if not compact:
        return False

    candidate = compact
    for _ in range(4):
        if candidate in _REFERENCE_STEMS:
            return True
        for suffix in _REFERENCE_SUFFIXES:
            if candidate.endswith(suffix) and len(candidate) > len(suffix) + 1:
                candidate = candidate[: -len(suffix)]
                break
        else:
            break
    return candidate in _REFERENCE_STEMS


def is_safe_correction_pair(wrong: str, right: str) -> bool:
    """Whether a pair is safe to learn, pre-pass, or propagate globally."""
    wrong = clean_pair_text(wrong)
    right = clean_pair_text(right)
    if not wrong or not right or wrong == right:
        return False
    if is_contextual_reference(wrong) or is_contextual_reference(right):
        return False
    return True
