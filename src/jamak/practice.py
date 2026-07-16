"""Per-user tutorial practice sessions (PLAN v4 §4.3).

A *baseline* practice job (one per course, `practice_course` set) is frozen
after rehearsal; every reviewer who starts a course gets a *clone* — a deep
copy of the baseline's Korean segments under a synthetic video_id
"<base>~<key>". Clones make parallel practice collision-free by construction
and "start over" is just re-cloning. The synthetic video_id lets every
existing video_id-keyed endpoint operate on clones unchanged; the frontend
strips the "~..." suffix when embedding the YouTube player.
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from sqlmodel import Session, select

from .db import Job, Segment, SttBlob, Translation, get_session, utcnow

SESSION_KEY_RE = re.compile(r"^[a-z0-9-]{4,40}$")
CLONE_TTL_DAYS = 7

# [WH-CHANGE v0.9.92 | FEAT | 2026-07-17 | CHG-20260717-133]
# Reason: 사용자 확정 — "연습5는 타이밍 작업에 특화되게, 그 전에 것들은 다 되어
#   있어야 해". 타이밍 코스는 **글자 검수가 끝난 자막**에서 출발해야 손볼 것이
#   시간뿐이다. 그런데 STT 셀은 그 전제를 깼다(실측):
#     #9  49.5~52.3 "문장은 일부러 아주 빠르게 말해서 읽을 시간이 모자라도록 만든"
#     #10 52.3~54.3 "문장입니다. 화면에 빨간 표시가 뜰 겁니다."
#   대본은 "**이** 문장은…"인데 첫 낱말이 없고, 한 문장이 두 셀로 갈렸으며,
#   그 탓에 "일부러 빠르게 말해 읽을 시간이 모자란" 드릴 문장이 cps 9.4로
#   주저앉아 **빨간 표시가 뜨지 않았다**(기준 17).
#   → 셀을 **대본 문장 단위로 재구성**한다. 텍스트는 대본 원문(완벽), 시각은
#   stt.json의 **word 타임스탬프에 정렬**해서 얻는다 — 시각을 대본에 하드코딩
#   하지 않으므로 재렌더로 발화 시각이 바뀌어도 따라온다(대본 텍스트가 그대로인
#   한). UI 드릴 재료지 학습 데이터가 아니다 (practice 전용, structure 선례).
# Related: CHANGELOG CHG-20260717-133.
TIMING_SCRIPT: list[str] = [
    "다섯 번째 연습입니다.",
    "이번에는 자막이 뜨고 사라지는 시간, 타이밍입니다.",
    "타이밍은 글자 검수를 다 끝낸 뒤에 하시기를 권합니다.",
    "글 고치기와 시간 맞추기를 한꺼번에 하면 너무 버겁습니다.",
    "방금 일부러 조용한 시간을 길게 두었습니다.",
    "자막이 말보다 일찍 뜨거나 늦게 사라지면 보기에 어색합니다.",
    "시작은 간단합니다.",
    "자막 목록 맨 위의 둘, 타이밍 탭을 누르세요.",
    "시간을 만지는 도구는 이 탭에서만 나옵니다.",
    "이 문장은 일부러 아주 빠르게 말해서 읽을 시간이 모자라도록 만든 문장입니다 화면에 빨간 표시가 뜰 겁니다.",
    "전부 다 보실 필요는 없습니다.",
    "다음 문제 버튼을 누르면 손볼 자막으로 바로 데려다 줍니다.",
    "문제가 있는 것만 골라 보세요.",
    "고치는 곳은 영상 바로 밑입니다.",
    "시간 줄에 지금 편집 중인 자막의 시작과 끝이 나옵니다.",
    "눈을 영상에 둔 채로 그 자리에서 고치시면 됩니다.",
    "말이 시작되는 순간, 알트와 대괄호 열기.",
    "지금 재생 위치가 이 자막의 시작이 됩니다.",
    "말이 끝나는 순간, 알트와 대괄호 닫기.",
    "여기서 자막을 끝내고 다음으로 넘깁니다.",
    "그리고 제일 편한 것.",
    "알트와 역슬래시, 발화 맞춤입니다.",
    "이 자막을 말소리 시작과 끝에 알아서 딱 맞춰 줍니다.",
    "조금만 어긋났을 때는 시간 줄의 삼각형 단추입니다.",
    "한 번 누를 때마다 영점 일 초씩 움직입니다.",
    "숫자를 직접 눌러 고쳐 넣으셔도 됩니다.",
    "영상 바로 아래에 자막들이 막대로 늘어선 타임라인도 있습니다.",
    "밝은 손잡이를 좌우로 끌어도 됩니다.",
    "방금도 조용한 구간이 지나갔지요.",
    "무음 다듬기를 누르면, 이런 조용한 구간에 자막이 남지 않게 전체를 한 번에 다듬습니다.",
    "확실한 것만 건드리니 안심하셔도 됩니다.",
    "타이밍까지 다 되면, 영상 왼쪽 아래의 타이밍 검수 완료에 체크하세요.",
    "다섯 번째 연습 끝.",
    "순서만 기억하세요.",
    "문제만 골라서, 영상 밑에서 바로.",
]
# 드릴 대상: 위 목록에서 "일부러 빠르게 말한" 문장 (읽을 시간 부족 → 빨간 표시)
TIMING_FAST_SENTENCE = 9
TIMING_FAST_CPS = 22.0  # 결함 주입 후 목표 cps (경고 기준 17 위)

# Deterministic screen-draft defects planted at course-bind time (P5 found the
# scripted baits were all defeated by whisper hotwords — the STT is too good).
# Injection edits text_llm on the BASELINE once; every clone inherits the same
# start state, so drills are identical for all reviewers. Replacements are
# idempotent: once applied, the source word is gone and the rule no-ops.
COURSE_TEXT_DEFECTS: dict[str, list[tuple[str, str, int]]] = {
    # course id -> [(correct, planted_typo, max_rows_to_touch)]
    "basic": [
        ("깻잎", "깨입", 1),
        ("밤나무", "밥나무", 1),
        ("축지법", "축제법", 1),
        ("공중부양", "공중부용", 1),
    ],
    # fast(찾기·바꾸기)는 아래 전용 분기에서 처리한다 — 단순 치환으로는 STT가
    # 제각각 낸 이름 변종을 하나로 모을 수 없다 (CHG-20260717-129).
}


def _norm_ko(s: str) -> str:
    return re.sub(r"[^가-힣0-9a-zA-Z]", "", s or "")


def _align_sentences(
    sentences: list[str], words: list[dict]
) -> list[tuple[str, float, float]] | None:
    """대본 문장 → (문장, start, end). stt.json word 타임스탬프에 정렬해서 얻는다.

    대본 전체와 STT 전체를 정규화 문자열로 놓고 difflib으로 맞춘 뒤, 각 문장의
    끝 위치를 STT 글자 위치로 옮기고, 그 글자가 속한 word의 시각을 쓴다.
    STT가 낱말을 흘리거나 잘못 들어도(연습2 "0.75를", 연습5 "이 문장은")
    앞뒤 일치 블록이 위치를 잡아 주므로 셀 경계가 밀리지 않는다.
    정렬이 부실하면(일치율 낮음) None — 재구성을 포기하고 STT 셀을 그대로 둔다.
    """
    from difflib import SequenceMatcher

    # STT 글자 위치 -> word 인덱스
    char_word: list[int] = []
    stt_chars: list[str] = []
    for wi, w in enumerate(words):
        for ch in _norm_ko(w.get("word", "")):
            stt_chars.append(ch)
            char_word.append(wi)
    stt = "".join(stt_chars)
    if not stt:
        return None

    script = "".join(_norm_ko(s) for s in sentences)
    sm = SequenceMatcher(None, script, stt, autojunk=False)
    blocks = sm.get_matching_blocks()
    if sm.ratio() < 0.7:  # 대본과 음성이 아예 다른 영상 — 손대지 않는다
        return None

    def script_to_stt(pos: int) -> int | None:
        """대본 글자 위치 → 가장 가까운 STT 글자 위치."""
        best = None
        for a, b, size in blocks:
            if not size:
                continue
            if a <= pos < a + size:
                return b + (pos - a)
            cand = b if pos < a else b + size - 1
            if best is None or abs(a - pos) < best[0]:
                best = (abs(a - pos), cand)
        return best[1] if best else None

    out: list[tuple[str, float, float]] = []
    cur = 0
    prev_w1 = -1
    for sent in sentences:
        n = len(_norm_ko(sent))
        if n == 0:
            continue
        s0 = script_to_stt(cur)
        s1 = script_to_stt(cur + n - 1)
        cur += n
        if s0 is None or s1 is None:
            return None
        w0, w1 = char_word[min(s0, len(char_word) - 1)], char_word[min(s1, len(char_word) - 1)]
        if w1 < w0:
            w0, w1 = w1, w0
        # 첫 낱말이 앞 문장 것으로 잡히면 다음 낱말부터 — STT가 문장 첫 낱말을
        # 흘리면("이 문장은" → "문장은") 그 글자가 앞 문장 끝에 매칭돼 셀이 앞
        # 침묵까지 삼킨다. 그대로 두면 빠른 문장 결함이 발화 전에 끝나 버린다.
        if w0 <= prev_w1:
            w0 = min(prev_w1 + 1, w1)
        prev_w1 = w1
        start = float(words[w0].get("start") or 0.0)
        end = float(words[w1].get("end") or start)
        if end <= start:
            return None
        out.append((sent.strip(), round(start, 3), round(end, 3)))

    # 시각이 단조증가해야 한다 — 아니면 정렬이 꼬인 것
    for a, b in zip(out, out[1:]):
        if b[1] < a[1]:
            return None
    return out


def _rebuild_timing_cells(session: Session, job: Job, segs: list[Segment]) -> int:
    """연습5 셀을 대본 문장 단위로 재구성 (CHG-20260717-133).

    텍스트·셀 경계는 완성 상태로 만들고, 손볼 것은 **시간만** 남긴다.
    """
    import json

    blob = session.exec(select(SttBlob).where(SttBlob.job_id == job.id)).first()
    if blob is None:
        return 0
    try:
        data = json.loads(blob.data)
    except Exception:
        return 0
    raw = data if isinstance(data, list) else data.get("segments", [])
    words = [w for g in raw for w in (g.get("words") or [])]
    if not words:
        return 0

    aligned = _align_sentences(TIMING_SCRIPT, words)
    if aligned is None:
        return 0
    # 이미 재구성돼 있으면(재바인딩 반복) 다시 하지 않는다 — 멱등
    if len(segs) == len(aligned) and all(
        _norm_ko(s.text_llm) == _norm_ko(t) for s, (t, _, _) in zip(segs, aligned)
    ):
        return 0

    for s in segs:
        session.delete(s)
    session.flush()

    for i, (text, start, end) in enumerate(aligned):
        session.add(
            Segment(
                job_id=job.id,
                idx=i,
                lang="ko",
                start=start,
                end=end,
                text_whisper=text,
                text_llm=text,
                text_youtube="",
                text_final="",
                reviewed=False,
            )
        )
    session.flush()
    return len(aligned)


def inject_course_defects(session: Session, job: Job, course: str) -> int:
    """Plant deterministic defects on the baseline for this course. Returns
    the number of rows changed. Runs at bind time only (caller skips when the
    job is already bound to the same course)."""
    changed = 0
    segs = session.exec(
        select(Segment)
        .where(Segment.job_id == job.id, Segment.lang == "ko")
        .order_by(Segment.idx)
    ).all()

    for correct, typo, max_rows in COURSE_TEXT_DEFECTS.get(course, []):
        touched = 0
        for s in segs:
            if touched >= max_rows:
                break
            src = s.text_llm or s.text_whisper
            if correct in src:
                s.text_llm = src.replace(correct, typo)
                # reviewed rows would hide the draft; baselines are unreviewed,
                # but clear defensively so the defect is always visible.
                s.reviewed = False
                s.text_final = ""
                session.add(s)
                touched += 1
                changed += 1

    if course == "fast":
        # [WH-CHANGE v0.9.88 | FIX | 2026-07-17 | CHG-20260717-129]
        # Reason: 사용자 지적 — "몽치 → 뭉치가 4개가 아니라 2개만 적용돼". 찾기·
        #   바꾸기 드릴은 **같은 이름이 자막마다 똑같이 잘못 적혀 있어야** 한 번의
        #   바꾸기로 전부 고쳐지고, 나레이션(L12)도 "한 번에 다 바뀝니다"라고
        #   약속한다. 그런데 STT는 제각각이었다 — 뭉치(정확)·뭥치(자연 오인식)가
        #   섞였고 옛 주입은 `max_rows=2`로 묶여 2행만 몽치가 됐다. 그래서 바꾼
        #   뒤에도 이름이 남아 약속이 깨졌다.
        #   강아지 이야기 4줄(대본 L8~L11)의 이름 변종을 전부 `몽치`로 통일한다.
        #   기능을 설명하는 L12("만약 뭉치라는 이름이…")는 건드리지 않는다 —
        #   지시문의 이름까지 틀리면 무엇을 무엇으로 바꿔야 하는지 알 수가 없다.
        #   UI 드릴 재료 보정이지 학습 데이터가 아니다 (practice 전용).
        # Related: CHANGELOG CHG-20260717-129.
        name_re = re.compile(r"뭉치|뭥치|뭉티|뭉지|뭉찌")
        for s in segs:
            src = s.text_llm or s.text_whisper or ""
            if "만약" in src:
                continue  # 기능 설명 줄 — 이름을 올바르게 둔다
            new = name_re.sub("몽치", src)
            if new != src:
                s.text_llm = new
                s.text_final = ""
                s.reviewed = False
                session.add(s)
                changed += 1

    if course == "basic":
        # [WH-CHANGE v0.9.73 | FIX | 2026-07-17 | CHG-20260717-110]
        # Reason: Whisper가 나레이션 L8 "잘 하셨습니다."의 첫 글자를 **앞 대사(L7)
        #   꼬리에 잘못 찍어** 한 단어가 3초 떨어진 두 셀로 갈렸다 —
        #   #13 "잘"(66.6~67.6, L7 구간 안) + #14 "하셨습니다"(70.6~71.3, L8 자리).
        #   연습1은 첫 튜토리얼이고 투어가 셀 텍스트를 나레이션과 대조하는 단계라,
        #   "잘"만 있는 셀은 "지금 → 실제 말" 안내를 무의미하게 만든다(사용자 지적).
        #   앞 조각을 지우고 본체에 붙여 한 셀로 되돌린다. 시각은 본체 것을 쓴다 —
        #   앞 조각의 start를 살리면 자막이 L7 발화 위에 뜬다.
        #   UI 드릴 재료 보정이지 학습 데이터가 아니다 (practice 전용, structure 선례).
        # Related: CHANGELOG CHG-20260717-110.
        for a, b in zip(segs, segs[1:]):
            ta = (a.text_llm or a.text_whisper or "").strip()
            tb = (b.text_llm or b.text_whisper or "").strip()
            if ta == "잘" and tb.startswith("하셨습니다"):
                b.text_llm = f"잘 {tb}"
                b.text_final = ""
                b.reviewed = False
                session.add(b)
                session.delete(a)
                session.flush()
                for i, x in enumerate(
                    sorted((s for s in segs if s is not a), key=lambda s: s.start)
                ):
                    if x.idx != i:
                        x.idx = i
                        session.add(x)
                changed += 1
                break

    if course == "structure":
        # [WH-CHANGE v0.9.13 | FIX | 2026-07-15 | CHG-20260715-037]
        # Reason: 나누기 드릴은 "너무 긴 자막" 하나가 있어야 성립하는데 STT가
        #   대본의 초장문(L2)을 여러 행으로 쪼개고 꼬리 겹침까지 남겼음 —
        #   해당 구간 행들을 병합하고 대본 원문으로 되돌린다 (UI 드릴 재료,
        #   학습 데이터 아님 — practice 전용).
        # Related: CHANGELOG CHG-20260715-037.
        LONG = (
            "제가 지금부터 숨도 안 쉬고 아주 길게 말할 텐데 이렇게 길게 말하면 "
            "자막 한 칸에 글이 꽉 차서 보는 사람이 미처 다 읽기도 전에 자막이 "
            "지나가 버리기 때문에 중간의 적당한 곳에서 둘로 나누어 주는 것이 좋습니다"
        )
        # 창은 대본 L2(초장문) 발화 구간만: 17.0~32.5s (timing.json 16.54~32.74).
        # 넓게 잡으면 앞 대사("차분히 다듬는...") 행까지 삼킨다 — 실제로 삼켜서
        # 좁힘. 텍스트 앵커('숨도')로 이중 확인.
        def _nm(t: str) -> str:
            return re.sub(r"[^\w가-힣]", "", t or "")

        span = [
            s
            for s in segs
            if "길지요" not in (s.text_llm or "")
            and (
                (s.end > 17.0 and s.start < 32.5)
                # STT가 문장 머리를 창보다 이르게 찍는 경우: 텍스트가 초장문의
                # 일부면 흡수 (14.1s '제가 지금부터…' 조각 실측)
                or (s.start >= 12.0 and s.start < 32.5 and _nm(s.text_llm or s.text_whisper) in _nm(LONG))
            )
        ]
        joined = " ".join((s.text_llm or s.text_whisper or "") for s in span)
        if span and "숨도" in joined and (len(span) > 1 or span[0].text_llm != LONG):
            first = span[0]
            first.end = max(x.end for x in span)
            first.text_llm = LONG
            first.text_final = ""
            first.reviewed = False
            session.add(first)
            for x in span[1:]:
                session.delete(x)
            session.flush()
            rest = sorted(
                (s for s in segs if s not in span[1:]), key=lambda s: s.start
            )
            for i, s in enumerate(rest):
                if s.idx != i:
                    s.idx = i
                    session.add(s)
            changed += 1

    if course == "timing":
        # [WH-CHANGE v0.9.92 | FEAT | 2026-07-17 | CHG-20260717-133]
        # Reason: 타이밍 코스는 **글자 검수가 끝난 자막**에서 출발해야 한다(사용자
        #   확정). 먼저 셀을 대본 문장 단위로 재구성해 텍스트·경계를 완성시키고,
        #   그 위에 **시간 결함만** 심는다. 아래 두 결함이 대본이 약속한 드릴 재료다.
        # Related: CHANGELOG CHG-20260717-133.
        n_rebuilt = _rebuild_timing_cells(session, job, segs)
        if n_rebuilt:
            changed += n_rebuilt
            segs = session.exec(
                select(Segment)
                .where(Segment.job_id == job.id, Segment.lang == "ko")
                .order_by(Segment.idx)
            ).all()

        # 결함 1 — 빠른 문장: 대본 L4가 "읽을 시간이 모자라도록" 만든 문장인데
        # 실제 발화는 cps 5.6이라 빨간 표시가 안 뜬다(기준 17). **끝을 발화 끝에
        # 두고 시작을 늦춰** 표시 시간을 줄인다 → cps 22로 빨간 표시가 뜨고,
        # 자막이 "말보다 늦게 뜨는"(대본 L2가 말한 그 증상) 화면이 된다.
        # Alt+\ (발화 맞춤)를 누르면 실제 말소리 구간으로 돌아가 정상이 된다.
        # 시작을 늦추는 쪽을 택한 이유: 끝을 당기면 자막이 **발화가 시작되기도
        # 전에 사라져**(정렬상 이 셀의 start가 발화보다 이르다) 어르신에겐
        # 고칠 거리가 아니라 그냥 혼란이다.
        if n_rebuilt and TIMING_FAST_SENTENCE < len(segs):
            s = segs[TIMING_FAST_SENTENCE]
            n_chars = len((s.text_llm or "").replace(" ", ""))
            want = round(s.end - n_chars / TIMING_FAST_CPS, 3)
            if n_chars and want > s.start and want < s.end:
                s.start = want
                session.add(s)
                changed += 1

        # 결함 2 — 무음에 걸친 자막: 뒤에 1.5초 이상 침묵이 있는 첫 셀의 끝을
        # 침묵 속으로 늘린다 (✂ 무음 다듬기 재료).
        # `n_rebuilt` 안에서만 심는다 — 재구성은 멱등이라 두 번째 호출부터는
        # 0이고, 결함도 따라서 한 번만 심긴다. 이 가드가 없으면 재바인딩마다
        # **결함이 하나씩 늘어난다**: 첫 쌍을 심으면 그 간격이 0.15로 좁아져
        # 다음 호출은 *다른* 쌍을 찾아 또 심는다 (재실행 검증에서 실측).
        if n_rebuilt:
            for a, b in zip(segs, segs[1:]):
                if b.start - a.end >= 1.5:
                    a.end = round(b.start - 0.15, 3)
                    session.add(a)
                    changed += 1
                    break

    return changed


def _clone_video_id(base_video_id: str, session_key: str) -> str:
    # hash, don't truncate: two keys sharing a prefix must not collide on the
    # UNIQUE video_id (found in E2E with "browser-user-a"/"...-b")
    digest = hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:10]
    return f"{base_video_id}~{digest}"


def get_or_create_practice_session(
    base_video_id: str, session_key: str, reset: bool = False
) -> dict:
    """Return (creating if needed) this browser's clone of a baseline practice
    job. reset=True discards the existing clone first — 'start over'."""
    if "~" in base_video_id:
        raise ValueError("already a practice-session video")
    if not SESSION_KEY_RE.match(session_key):
        raise ValueError("bad session key")

    with get_session() as session:
        base = session.exec(
            select(Job).where(Job.video_id == base_video_id)
        ).first()
        if base is None:
            raise LookupError(f"no job for {base_video_id}")
        if not base.practice or base.clone_of is not None:
            raise PermissionError("연습용 영상이 아닙니다")  # BR-DATA-001 guard
        # ko-single-track contract: no fork tracks on tutorial videos
        non_ko = session.exec(
            select(Segment.id)
            .where(Segment.job_id == base.id, Segment.lang != "ko")
            .limit(1)
        ).first()
        if non_ko is not None:
            raise PermissionError("연습용 영상에 번역 트랙이 있어 복제할 수 없습니다")

        existing = session.exec(
            select(Job).where(
                Job.clone_of == base.id, Job.session_key == session_key
            )
        ).first()
        if existing is not None and not reset:
            return {"video_id": existing.video_id, "created": False}
        if existing is not None:
            _delete_clone(session, existing)

        clone = Job(
            video_id=_clone_video_id(base.video_id, session_key),
            url=base.url,
            title=base.title,
            channel=base.channel,
            duration_seconds=base.duration_seconds,
            upload_date=base.upload_date,
            status=base.status,
            practice=True,
            clone_of=base.id,
            session_key=session_key,
        )
        session.add(clone)
        session.commit()
        session.refresh(clone)

        for s in session.exec(
            select(Segment)
            .where(Segment.job_id == base.id, Segment.lang == "ko")
            .order_by(Segment.idx)
        ).all():
            data = s.model_dump(exclude={"id"})
            data["job_id"] = clone.id
            session.add(Segment(**data))
        blob = session.exec(
            select(SttBlob).where(SttBlob.job_id == base.id)
        ).first()
        if blob is not None:
            session.add(SttBlob(job_id=clone.id, data=blob.data))
        session.commit()
        return {"video_id": clone.video_id, "created": True}


def _delete_clone(session: Session, clone: Job) -> None:
    """Delete a practice clone and its rows. Double guard (clone_of set AND
    practice) — this must never be reachable for real review data."""
    assert clone.clone_of is not None and clone.practice, "refusing: not a clone"
    seg_ids = session.exec(
        select(Segment.id).where(Segment.job_id == clone.id)
    ).all()
    if seg_ids:
        for tr in session.exec(
            select(Translation).where(Translation.segment_id.in_(seg_ids))
        ).all():
            session.delete(tr)
        for seg in session.exec(
            select(Segment).where(Segment.job_id == clone.id)
        ).all():
            session.delete(seg)
    for blob in session.exec(
        select(SttBlob).where(SttBlob.job_id == clone.id)
    ).all():
        session.delete(blob)
    # [WH-CHANGE v0.8.7 | FIX | 2026-07-15 | CHG-20260715-027]
    # Reason: on Postgres the ORM emitted DELETE job before DELETE sttblob in
    # the same flush -> sttblob_job_id_fkey violation -> 연습 재입장이 500으로
    # 죽음 (로컬 SQLite는 FK 미강제라 E2E가 못 잡았음). 자식 행 삭제를 먼저
    # flush해 순서를 명시적으로 고정한다.
    # Related: CHANGELOG CHG-20260715-027.
    session.flush()
    session.delete(clone)
    session.commit()


def cleanup_stale_clones(ttl_days: int = CLONE_TTL_DAYS) -> int:
    """Drop practice clones idle longer than the TTL (worker housekeeping)."""
    cutoff = utcnow() - timedelta(days=ttl_days)
    removed = 0
    with get_session() as session:
        stale = session.exec(
            select(Job).where(
                Job.clone_of != None,  # noqa: E711
                Job.practice == True,  # noqa: E712
                Job.updated_at < cutoff,
            )
        ).all()
        for clone in stale:
            _delete_clone(session, clone)
            removed += 1
    return removed
