"""Stage 2.5 — Split: cut long whisper segments into subtitle-sized pieces.

Whisper emits breath-group segments that can run 20+ seconds — far too
much text for one subtitle. Word timestamps let us re-cut precisely:
prefer sentence boundaries (문장부호, 어미+pause), force a cut when a
piece would exceed the char/duration budget.
"""

from __future__ import annotations

import re
import statistics

from ..config import MAX_CHARS_PER_LINE, MAX_LINES, MAX_SEGMENT_SECONDS
from .stt import SttSegment, Word

DEFAULT_MAX_CHARS = MAX_CHARS_PER_LINE * MAX_LINES  # hard budget per subtitle (36)
DEFAULT_SOFT_CHARS = 20  # at a sentence boundary past this length, cut proactively
BOUNDARY_GAP = 0.6  # silence between words that counts as a natural break
# a real pause: force a cut here even for a short line, so a subtitle never
# spans silence (subtitle ends at the last spoken word, the next starts at the
# next spoken word, and the quiet gap between shows no subtitle at all)
SILENCE_SPLIT = 0.7
MIN_LEARN_SAMPLES = 40  # need this many reviewed subtitles before learning length


def learned_line_budget() -> tuple[int, int] | None:
    """(soft, hard) char budget learned from human-reviewed subtitles.

    The reviewer's final subtitles ARE their preferred length. We fit the
    split budget to them so future videos are cut the way this reviewer
    likes — one more thing the ouroboros loop extracts from finished work.
    Returns None until enough reviewed samples exist.
    """
    from sqlmodel import select

    from ..db import Job, Segment, get_session

    with get_session() as session:
        rows = session.exec(
            # [WH-CHANGE v0.4.3 | FIX | 2026-07-14 | CHG-20260714-005]
            # Reason: practice(연습용) jobs are a sandbox — tutorial edits must not
            #   feed any ouroboros learning path, not just absorb_job().
            # Related: docs/tutorial/PLAN.md Codex review BLOCKER-3.
            select(Segment.text_final)
            .join(Job, Segment.job_id == Job.id)
            .where(
                # ko only: this is the Korean line-length budget. Forked
                # translation segments (non-ko text_final, ADR-0006) run longer
                # per cue and would inflate the budget, over-splitting Korean.
                Segment.lang == "ko",
                Segment.reviewed == True,  # noqa: E712
                Job.practice == False,  # noqa: E712
            )
        ).all()
    lengths = sorted(len(t.strip()) for t in rows if t and t.strip())
    if len(lengths) < MIN_LEARN_SAMPLES:
        return None

    def pct(p: float) -> int:
        return lengths[min(len(lengths) - 1, int(p * len(lengths)))]

    hard = int(min(48, max(24, pct(0.9))))
    soft = int(min(hard - 2, max(14, statistics.median(lengths))))
    return soft, hard

_SENT_END = re.compile(r"[.?!…]$|[다요죠지]\?*$")


def _text_of(words: list[Word]) -> str:
    return "".join(w.word for w in words).strip()


# [WH-CHANGE v0.9.85 | FIX | 2026-07-17 | CHG-20260717-125]
# Reason: 사용자 보고 — 연습2에 "0.75를" / ".75를 누르고 들으면…" 두 셀이 겹쳐
#   나왔다. 뿌리는 교정도 에코도 아니고 **여기**였다: whisper가 한 어절 "0.75를"을
#   두 토큰 `0`(65.63~66.79) + `.75를`(67.53~68.23)으로 쪼개면서 그 사이에 0.74초
#   갭을 찍었고, SILENCE_SPLIT(0.7)이 그 갭을 침묵으로 보고 **어절 한가운데를
#   잘랐다** → `"0"` 한 글자짜리 셀 탄생 → LLM이 문맥으로 "0.75를"이라 확장 →
#   옆 셀의 ".75를…"과 텍스트 중복. 즉 중복은 마지막 증상일 뿐이었다.
#   whisper 토큰은 새 어절일 때만 선행 공백을 갖는다(`_text_of`가 공백 없이
#   join하는 것이 그 증거) — 이미 갖고 있던 정보를 안 쓰고 있었다.
# Related: CHANGELOG CHG-20260717-125.
def _mid_word(words: list[Word], i: int) -> bool:
    """words[i] 다음이 같은 어절인가 — 원문에서 공백 없이 붙어 있나.

    붙어 있으면 그 사이는 자를 수 없다: 아무리 갭이 길어도 한 낱말을 두
    자막으로 쪼개는 것이고, 조각난 쪽은 뜻을 잃는다("0", ".75를").
    """
    if i + 1 >= len(words):
        return False
    return not words[i + 1].word[:1].isspace()


def _is_boundary(words: list[Word], i: int) -> bool:
    """Is position i (end of words[i]) a natural cut point?"""
    if _mid_word(words, i):
        return False  # 어절 한가운데 — 구두점이든 갭이든 경계가 아니다
    w = words[i].word.strip()
    if w.endswith(("?", ".", "!", "…")):
        return True
    if i + 1 < len(words) and words[i + 1].start - words[i].end >= BOUNDARY_GAP:
        return True
    return False


def _split_words(words: list[Word], soft_chars: int, max_chars: int) -> list[list[Word]]:
    pieces: list[list[Word]] = []
    cur: list[Word] = []
    for i, w in enumerate(words):
        cur.append(w)
        text = _text_of(cur)
        dur = cur[-1].end - cur[0].start
        global_i = i  # index into full words list for boundary lookahead

        # 어절 한가운데면 어떤 이유로도 자르지 않는다 (CHG-20260717-125). 침묵도
        # 글자수 초과도 낱말을 쪼갤 근거는 못 된다 — 다음 어절 경계까지 미룬다.
        if _mid_word(words, i):
            continue

        # hard cut at a real silence: the speaker paused, so this subtitle ends
        # here and the quiet stretch that follows stays subtitle-free
        next_gap = words[i + 1].start - w.end if i + 1 < len(words) else 0.0
        if next_gap >= SILENCE_SPLIT and cur:
            pieces.append(cur)
            cur = []
            continue

        at_boundary = _is_boundary(words, global_i)
        over_soft = len(text) >= soft_chars
        over_hard = len(text) >= max_chars or dur >= MAX_SEGMENT_SECONDS

        if (at_boundary and over_soft) or over_hard:
            if over_hard and not at_boundary:
                # forced cut: back up to the last boundary inside cur if any
                back = None
                for k in range(len(cur) - 2, 0, -1):
                    if _is_boundary(words, global_i - (len(cur) - 1 - k)):
                        back = k
                        break
                if back is not None and back >= len(cur) // 3:
                    pieces.append(cur[: back + 1])
                    cur = cur[back + 1 :]
                    continue
            pieces.append(cur)
            cur = []
    if cur:
        # a tiny tail reads badly — glue it to the previous piece when the
        # merged text still fits the hard budget, but never glue across a real
        # silence (that pause is exactly where the subtitle should break)
        if (
            pieces
            and len(_text_of(cur)) <= 6
            and len(_text_of(pieces[-1] + cur)) <= max_chars
            and cur[0].start - pieces[-1][-1].end < SILENCE_SPLIT
        ):
            pieces[-1] = pieces[-1] + cur
        else:
            pieces.append(cur)
    return pieces


def split_segments(
    segments: list[SttSegment], budget: tuple[int, int] | None = None
) -> list[SttSegment]:
    soft_chars, max_chars = budget or learned_line_budget() or (
        DEFAULT_SOFT_CHARS,
        DEFAULT_MAX_CHARS,
    )
    out: list[SttSegment] = []
    for seg in segments:
        if not seg.words:
            # no word timings — can't retighten or silence-split; keep as-is
            out.append(seg)
            continue
        # run every segment through the splitter (even short ones): it cuts at
        # internal silences and re-emits each piece on tight word boundaries, so
        # no subtitle keeps spanning a pause or trailing into quiet.
        for piece in _split_words(seg.words, soft_chars, max_chars):
            text = _text_of(piece)
            if not text:
                continue
            out.append(
                SttSegment(
                    start=piece[0].start,
                    end=piece[-1].end,
                    text=text,
                    words=piece,
                    avg_logprob=seg.avg_logprob,
                )
            )
    return out
