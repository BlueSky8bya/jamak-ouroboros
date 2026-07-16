"""무음 다듬기 v2 — 확실한 것만 (ADR-0012 후속, 사용자 승인 2026-07-17).

자막의 시작/끝을 실제 발화에 맞춰 침묵을 걷어낸다. 텍스트는 절대 건드리지 않는다.

v1의 문제 (실측: 발화 있는 셀 7,066개 중 **2,938개(42%)** 를 변경, 되돌리기 없음):
  1. 0.05초만 달라도 손댔다 — 잘라낼 침묵의 **중앙값이 0.00초**인데도 42%를 건드린 이유.
  2. 구간 안 단어를 **전부** 경계로 썼다. Whisper는 화자분리를 안 하므로 청중·질문자
     발화가 끼면 자막이 그쪽으로 끌려갔다 ("다른 사람 말하던 부분까지 포함" — 사용자).

v2는 **증거가 있을 때만** 손댄다:
  - 셀 텍스트와 그 구간에서 들린 말을 정렬해, **일치도가 낮으면 그 셀은 건드리지 않는다**
    (사람이 크게 고쳤거나 다른 화자가 섞인 셀).
  - 셀 텍스트에 **없는 말**(= 다른 화자/제거된 추임새)은 경계 계산에서 뺀다.
  - 앞/뒤 침묵이 **임계 이상**일 때만 자른다.

순수 함수 — 엔드포인트가 DB에 적용한다 (retime.py의 plan/apply 분리와 같은 꼴).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

#: 이 정도 미만으로 어긋난 건 "이미 맞음" — 손대지 않는다 (v1은 0.05였다).
MIN_SILENCE = 0.5
#: 셀 텍스트 ↔ 들린 말 문자 일치도가 이 밑이면 근거 부족 → 그 셀 통째로 건너뛴다.
MIN_ALIGN = 0.6
#: 자막이 이보다 짧아지지 않게 (읽을 시간 확보)
MIN_DUR = 0.30
#: 한 단어의 글자 중 이 비율 이상이 셀 텍스트와 맞아야 "이 셀의 말"로 인정
WORD_MATCH = 0.5

_NORM = re.compile(r"[^가-힣0-9a-zA-Z]+")


def _norm(text: str) -> str:
    return _NORM.sub("", text or "")


@dataclass
class TightenPlan:
    """한 자막의 다듬기 결과. changed=False면 손대지 않는다."""

    start: float
    end: float
    changed: bool
    reason: str  # "" | "weak-align" | "no-speech" | "already-tight" | "trimmed"
    align: float


def plan_cue(
    start: float,
    end: float,
    text: str,
    words: list[tuple[float, float, str]],
    *,
    min_silence: float = MIN_SILENCE,
    min_align: float = MIN_ALIGN,
) -> TightenPlan:
    """이 자막을 실제 발화에 맞출 계획. words = 이 구간에 든 (start, end, 단어).

    words는 시간순이어야 한다. 셀 텍스트와 맞지 않는 단어는 경계에서 제외된다.
    """
    if not words:
        # 예: 유튜브 자막으로 채운 행 (whisper가 아무것도 못 들은 구간) — 손대지 않는다
        return TightenPlan(start, end, False, "no-speech", 1.0)

    shown = _norm(text)
    # 들린 말을 이어 붙이고, 각 글자가 몇 번째 단어에서 왔는지 기억한다
    heard_chars: list[str] = []
    owner: list[int] = []
    for wi, (_s, _e, w) in enumerate(words):
        for ch in _norm(w):
            heard_chars.append(ch)
            owner.append(wi)
    heard = "".join(heard_chars)
    if not heard or not shown:
        return TightenPlan(start, end, False, "weak-align", 0.0)

    sm = SequenceMatcher(None, heard, shown, autojunk=False)
    align = sm.ratio()
    if align < min_align:
        # 사람이 크게 고쳤거나 다른 화자가 섞인 셀 — 근거가 없으므로 그대로 둔다
        return TightenPlan(start, end, False, "weak-align", align)

    # 셀 텍스트와 실제로 맞아떨어진 글자만 표시 → 그 글자를 가진 단어만 "이 셀의 말"
    matched = [0] * len(words)
    total = [0] * len(words)
    for wi in owner:
        total[wi] += 1
    for block in sm.get_matching_blocks():
        for k in range(block.a, block.a + block.size):
            matched[owner[k]] += 1
    keep = [
        w
        for wi, w in enumerate(words)
        if total[wi] and matched[wi] / total[wi] >= WORD_MATCH
    ]
    if not keep:
        return TightenPlan(start, end, False, "weak-align", align)

    ns = min(w[0] for w in keep)
    ne = max(w[1] for w in keep)
    if ne - ns < MIN_DUR:
        ne = ns + MIN_DUR

    # 앞/뒤로 걷어낼 침묵이 임계를 넘을 때만 손댄다
    if max(abs(ns - start), abs(ne - end)) < min_silence:
        return TightenPlan(start, end, False, "already-tight", align)
    return TightenPlan(round(ns, 3), round(ne, 3), True, "trimmed", align)


def words_inside(
    start: float, end: float, words: list[tuple[float, float, str]]
) -> list[tuple[float, float, str]]:
    """중점이 이 구간에 든 단어들 — 단어 하나는 정확히 한 자막에만 속한다."""
    return [w for w in words if start <= (w[0] + w[1]) / 2 < end]
