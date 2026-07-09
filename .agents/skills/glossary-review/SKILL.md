---
name: glossary-review
description: 자동 추출된 용어사전 후보를 검토·승인하는 대화형 세션. 미승인(approved=False) 용어를 분류하고 사람이 확정한다. "용어 정리하자", "용어사전 검토", "/glossary-review" 할 때 사용.
---

# glossary-review

미승인 용어 후보 → 사람 승인 → 프롬프트 주입 대상 승격.

## 절차

1. DB에서 미승인 후보 조회:
   ```
   uv run python -c "from jamak.db import *; from sqlmodel import select; s=get_session(); [print(t.term, t.note) for t in s.exec(select(GlossaryTerm).where(GlossaryTerm.approved==False)).all()]"
   ```
2. 후보를 스스로 1차 분류해서 제시:
   - **승인 추천**: 허경영 고유어휘(신인, 축지법, 공중부양, 하늘궁...), 종교 용어(불교/유교/기독교), 한자어, 자주 나오는 사투리 표현
   - **삭제 추천**: 일반 명사, 추출 노이즈
3. AskUserQuestion으로 묶어서 확인 (한 번에 10~20개씩, multiSelect).
4. 승인된 항목: `approved=True` + `category` 태그 + 알려진 오인식 변형이 있으면 `variants`에 기록.
   삭제 항목: DB에서 delete.
5. 최종 승인 용어 수 보고. 다음 `jamak run`부터 whisper prompt + Codex 교정에 자동 반영됨을 안내.

## 주의

- 용어는 DB가 원본 (AGENTS.md 규칙 4). 마크다운 목록 만들어 관리하지 말 것.
- variants(오인식 변형)는 교정 정확도에 직결 — 사용자가 아는 오인식 사례를 적극 수집.
