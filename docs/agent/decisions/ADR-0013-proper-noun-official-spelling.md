# ADR-0013 — 고유명사 표기: 단체 공식 표기 우선, 없으면 음역

- Status: Accepted
- Date: 2026-07-17
- Area: translate / glossary
- Decision Owners: User (3단 규칙 확정) + Agent (웹 근거 조사·구현)

## Context

번역 트랙에서 고유명사가 매번 다르게 나온다. 사용자 문제 제기의 원안은
"교리 고유명사는 **음역**하자 (하늘궁 → Haneulgung)"였다.

**조사 결과 그 전제가 절반만 맞았다.** 웹 근거:

| 용어 | 실제 통용/공식 | 로마자 표기법 기계 적용값 |
|---|---|---|
| 허경영 | **Huh Kyung-young** — [위키피디아 표제어](https://en.wikipedia.org/wiki/Huh_Kyung-young) · 코리아타임스 · 코리아헤럴드 · 위키데이터 · 본인 단체(국가혁명당 영상, 순례단 사이트 `Huh Kyung Young`) | ~~Heo Gyeong-yeong~~ (아무도 안 씀. 위키에 "이론상" 병기만) |
| 하늘궁 | **Heaven Palace** — 단체·위키피디아·매체 공통 | ~~Haneulgung~~ (학술 논문에서만 쓰임) |
| 불로유 | **Boolloyu** — 단체 표기(음역) | ~~Bulloyu~~ |
| 백궁 | **White Heaven** — 단체 표기 | ~~Baekgung~~ |

두 가지가 드러났다:
1. **로마자 표기법을 규칙으로 적용하면 오히려 틀린다.** 허경영의 표기법값은
   아무도 쓰지 않는다. 실존 인물·실존 단체에는 **본인들이 쓰는 표기**가 있다.
2. **"전부 음역"도 틀린다.** 단체는 용어마다 방식이 다르다 — 하늘궁은 **번역**
   (Heaven Palace), 불로유는 **음역**(Boolloyu). 우리가 하늘궁을 Haneulgung으로
   바꾸면 **당사자가 쓰는 표기를 우리가 어기는 꼴**이 된다.

기존 번역 프롬프트 규칙 3은 정확히 이 함정에 빠져 있었다:
> "고유명사(허경영, 하늘궁 등)는 **표준 로마자/현지 표기**로 일관되게 옮기고"

"규칙"을 시켰을 뿐 **정답 목록**을 준 적이 없다 → 매번 흔들린다.

## Decision

**3단 우선순위** (사용자 확정):

1. **1순위 — 단체 공식 표기.** 정해진 게 있으면 그대로. 로마자 표기법을 다시
   적용하지 않는다 (목록이 이미 정답).
   현재: 허경영=`Huh Kyung-young` · 하늘궁=`Heaven Palace` · 불로유=`Boolloyu` · 백궁=`White Heaven`
2. **2순위 — 공식 표기가 없는 고유명사만 음역** (로마자 표기법 기준). 첫 등장 시
   괄호로 짧은 설명 **1회** 허용.
3. **금지 — 의역.** 백궁 → "100 Palaces", 불로유 → "immortality milk",
   하늘궁 → "Sky Palace" 따위 금지.

**구현**: 규칙을 코드/프롬프트에 하드코딩하지 않는다 (ADR-0002 — 학습 데이터는 DB가 원본).
`GlossaryTerm.official`(JSON `{lang: 표기}`)에 담고 `glossary.official_names_block(lang)`이
번역 프롬프트에 주입한다. 언어가 늘어도 스키마는 그대로.

## Consequences

- **en만 채워져 있다.** ja/zh는 공식 표기가 없으므로 2순위(음역)가 맡는다 —
  일본어·중국어권 공식 표기가 확인되면 같은 필드에 채우면 된다.
- 표기가 바뀌거나 새 용어가 생기면 **DB만 고치면 된다.** 배포 불필요.
- **기존 번역은 자동으로 안 고쳐진다.** 이미 저장된 번역에 "Sky Palace"가 있으면
  재번역하거나 번역 검수에서 고쳐야 한다. (번역 *검수*는 검수자에게 열려 있음)
- 프롬프트가 길어져 첫 청크 입력 토큰이 소폭 증가 (ephemeral 캐시라 이후 청크는 무료).

## 확인/미확인

- **백궁 = `White Heaven` 확정** (사용자 확인 2026-07-17). `White Heaven Palace`(ANU/IJOR
  논문 제목)는 채택하지 않는다.
- 공식 사이트 `hkyworld.org` / `huhkyungyoungworld.org`는 **이 환경에서 DNS가 안 잡혀
  본문을 직접 못 봤다.** 나머지 표기는 **검색 결과 제목·스니펫과 위키피디아** 기반이며,
  사용자 확인으로 백궁은 해소됐다.
- `Sky Palace`라는 제3의 표기도 존재한다 (`huhkyungyoungworld.org` = "SkyPalaceV2").
  현재 결정은 다수·본인 단체 기준으로 **Heaven Palace**.

## Revisit Trigger

- 공식 사이트 본문 확인으로 표기가 다르게 밝혀지면 → `official` 필드만 교체.
- ja/zh 공식 표기 확보 시 → 같은 필드에 추가.
- 단체가 표기를 바꾸면 → DB 갱신 + 기존 번역 재검수 범위 판단.

## Sources

- https://en.wikipedia.org/wiki/Huh_Kyung-young
- https://www.koreatimes.co.kr/amp/southkorea/20250517/flamboyant-cult-like-korean-politician-huh-kyung-young-gets-prison-sentence
- https://www.koreaherald.com/article/3351773
- https://www.wikidata.org/wiki/Q246375
- https://www.scmp.com/week-asia/politics/article/3150877/south-koreas-next-president-meet-heo-kyung-young-levitating (Heo 표기 소수 사례)
- https://www.hkyworld.org/- (순례단 사이트 — 제목에서 `Huh Kyung Young Boolloyu White Heaven` 확인, 본문 미확인)
