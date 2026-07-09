---
name: jamak-eval
description: 기계 초안 대비 검수 완료본의 CER(문자 오류율)을 측정해 우로보로스 루프가 실제로 정확도를 올리고 있는지 숫자로 검증한다. "정확도 확인", "eval 돌려", "/jamak-eval" 할 때 사용.
---

# jamak-eval

우로보로스가 작동하는지 = CER이 회차별로 내려가는지.

## 절차

1. DB에서 `text_final`(검수 완료)이 있는 job들을 찾는다.
2. 각 job에 대해 jiwer로 CER 계산:
   - `text_whisper` vs `text_final` → STT 원시 오류율
   - `text_llm` vs `text_final` → LLM 교정 후 오류율 (교정 효과 = 두 값의 차)
3. job 생성일 순으로 정렬해 추이 테이블 출력:
   | 영상 | 날짜 | STT CER | 교정후 CER | 개선폭 |
4. 해석 보고:
   - 교정후 CER이 회차별 하락 → 루프 작동 중
   - 정체/상승 → 원인 분석 (용어사전 미승인 적체? few-shot 품질? whisper prompt 한계?)
5. 측정 코드가 아직 없으면 `src/jamak/evaluate.py`에 구현 후 실행 (jiwer 이미 의존성에 있음).

## 주의

- 비교 전 텍스트 정규화: 공백/문장부호 통일 (jiwer transforms 사용).
- 검수본 없는 job은 측정 불가 — 표본 수도 함께 보고.
