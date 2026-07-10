# Handoff — 시드 코퍼스 용어 마이닝 (2026-07-10)

## 무엇을 했나
1년치 사람 검수 코퍼스(`data/seeds/기존 검수 완료본.txt`, ~260만자)에서 hotwords/용어사전을 대량 확보.
교정쌍은 매칭되는 기계 초안이 없어 불가 — 사용자 판단대로 **hotwords + 용어사전만** 채움.

## 구현
- `src/jamak/glossary_mine.py` (신규)
  - `extract_candidates(dir)`: seed.py 리더/토크나이저 재사용, 빈도 상위 1500 후보 (n≥3). API 0.
  - `mine_glossary(dir)`: 후보를 200개씩 청크로 Claude(`CORRECT_MODEL`=sonnet, `thinking:disabled`, `output_config` json_schema)에 넘겨 도메인 어휘만 선별 → `{term, category, variants[]}` → `GlossaryTerm approved=True, confidence=1.0` upsert. 기존 term은 승격.
  - 시스템 프롬프트는 단어 목록만 보냄(전체 코퍼스 X) → 일회성 소액.
- `src/jamak/cli.py`: `jamak glossary-mine [dir=data/seeds]` 커맨드 추가.

## 실행 결과 (검증됨)
- `jamak glossary-mine` → 후보 1500 → 승인 65개 (신규 47 + 승격 18). 토큰 in 19.7k / out 2.1k ≈ **$0.06 일회성**.
- 카테고리: 고유어휘 22, 기독교 13, 지명 10, 인명 6, 한자어 6, 불교 5, 유교 1.
- `whisper_prompt()` / `whisper_hotwords()` 확인 → 축지법/공중부양/하늘궁/신인/석가모니/십자가/동학/석고대죄/용맹정진 등 + 오인식 변형(축지법→축제법, 하늘궁→하늘공/하늘굼 등) 포함.

## 알려진 한계
- 잔여 노이즈: 조사 붙은 형태(신인이, 십자가가, 미국은, 신인님의)가 일부 승인됨. `_TOKEN_RE`가 `[가-힣]{2,}`라 조사 포함 토큰을 하나로 잡음. hotwords에는 **무해**(여전히 편향 보조). `/glossary-review`로 사후 정리 가능.
- 사람 `/glossary-review` 승인을 Claude 자동 승인으로 대체(ADR-0004 stage1에 기록). 소스가 사람 검수 코퍼스라 방어 가능.

## 다음에 할 수 있는 것 (선택)
- `/glossary-review`로 노이즈 prune + 카테고리 손보기.
- 토크나이저 개선(조사 스트리핑)으로 헤드워드 품질↑ — 재마이닝 시 반영.
- 실제 `jamak run` 재실행 시 hotwords 효과(오인식 감소) CER로 측정 → ADR-0004 stage3 트리거 판단.
