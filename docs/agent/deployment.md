# 배포 가이드 — 터널 방식 (검수자 몇 명)

결정: **로컬 구조 그대로 두고, 터널로 URL 노출 + 로그인 한 겹.** (ADR-0007)
GPU STT·SQLite·파일 저장소 전부 로컬. 파이프라인(`jamak run`)도 로컬에서 실행.
검수자는 URL 접속해서 검수·내보내기만 한다.

전제: **검수 중엔 이 PC가 켜져 있어야 함.** 다중 사용자는 소수(서로 다른 영상 검수 권장).

---

## 0. 준비 (한 번)

```powershell
# 프론트 빌드 (serve가 dist를 정적으로 제공)
cd src/jamak/web/frontend; npm install; npm run build; cd ../../../..

# API 키 (없으면)
# $env:ANTHROPIC_API_KEY = (Get-ItemProperty HKCU:\Environment).ANTHROPIC_API_KEY
```

앱 자체 로그인(터널 인증과 별개, 방어 이중화). 노출 전 반드시 설정:

```powershell
$env:JAMAK_AUTH = "reviewer1:긴무작위비번1,reviewer2:긴무작위비번2"
uv run jamak serve            # http://127.0.0.1:8710
```

- `JAMAK_AUTH` 미설정 = 인증 없음(로컬 개발용). **외부 노출 시 반드시 설정.**
- 형식: `사용자:비번` 쉼표로 여러 명. 비번은 길고 무작위로.

---

## 경로 1 — Cloudflare Tunnel + Access (권장)

이메일로 검수자만 들여보냄. 무료, 고정 URL, 포트 개방 없음.

**필요:** Cloudflare에 올린 도메인 1개 (`example.com`).

```powershell
winget install --id Cloudflare.cloudflared
cloudflared tunnel login                       # 브라우저에서 도메인 선택
cloudflared tunnel create jamak
cloudflared tunnel route dns jamak jamak.example.com
```

`~/.cloudflared/config.yml`:

```yaml
tunnel: jamak
credentials-file: C:\Users\<너>\.cloudflared\<터널id>.json
ingress:
  - hostname: jamak.example.com
    service: http://127.0.0.1:8710
  - service: http_status:404
```

인증(Cloudflare Zero Trust 대시보드):
1. **Access → Applications → Add → Self-hosted**, 도메인 `jamak.example.com`.
2. **Policy: Allow**, Include = **Emails** → 검수자 이메일 나열.
3. 검수자는 접속 시 이메일 OTP(One-time PIN)로 로그인.

실행 (두 창 / 또는 서비스):

```powershell
uv run jamak serve                 # 창 1
cloudflared tunnel run jamak       # 창 2
```

검수자 → `https://jamak.example.com` → 이메일 인증 → (앱 JAMAK_AUTH까지 이중이면) 앱 로그인.

---

## 경로 2 — 도메인 없이 (Tailscale)

검수자도 Tailscale 깔면 사설망으로. 공개하려면 `tailscale funnel`.

```powershell
winget install tailscale.tailscale
tailscale up
tailscale serve https / http://127.0.0.1:8710     # tailnet 내부 공유
# 공개 URL이 필요하면: tailscale funnel 443 on
```

Funnel(공개)이면 앱 `JAMAK_AUTH`가 유일한 인증이니 **꼭 설정**.

---

## 경로 3 — 빠른 임시 데모 (도메인·설정 없이)

```powershell
$env:JAMAK_AUTH = "rev:긴비번"; uv run jamak serve      # 창 1
cloudflared tunnel --url http://127.0.0.1:8710          # 창 2 → 무작위 trycloudflare URL
```

URL이 매번 바뀌고 인증이 `JAMAK_AUTH`뿐 → 임시 확인용만.

---

## 운영 메모

- **항상 켜두기**: `serve`+터널을 Windows 서비스로. `nssm`(권장) 또는 작업 스케줄러 "로그온 시 실행". 재부팅 후 자동 기동.
- **동시성**: SQLite `busy_timeout=30s`로 소수 검수자(서로 다른 영상)는 안전. **같은 영상 구조(나누기·합치기)를 두 명이 동시 편집하면 idx 경합 위험** — 영상별로 나눠 맡기. 완전한 잠금은 이연(ADR-0007 후속, SQLite→PG 시).
- **백업**: `data/jamak.db`를 주기적으로 복사(원본 학습 데이터). `data/seeds/`도 보존.
- **비용**: 파이프라인·번역은 여전히 로컬 실행 → Claude API 영상당 과금. 검수 자체는 무API.
- **비밀**: `ANTHROPIC_API_KEY`·`JAMAK_AUTH`는 호스트 환경변수로만. 프론트 번들에 절대 넣지 않음.
- **HTTPS**: Cloudflare/Tailscale가 TLS 종단 제공 → 앱은 평문 127.0.0.1로 충분.

## 다음 단계 (규모 커지면)

검수자가 늘거나 항상 켜두기가 부담되면 **경로 B(클라우드 웹앱 + 로컬 GPU)** 로:
SQLite→Postgres, 파일→오브젝트스토리지(R2/S3), 세션 인증, per-(job,lang) 잠금.
= ADR-0007의 "future" 절 + `translate-audit` 감사가 남긴 동시성 항목.
