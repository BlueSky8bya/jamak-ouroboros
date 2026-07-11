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

앱 자체 로그인 — **스타일된 인앱 로그인 폼**(크롬 기본 팝업 아님) + 서명 세션 쿠키. 이름+비번, 눈모양 토글로 비번 보기. 역할별로 비번이 다름:

```powershell
setx JAMAK_ADMINS "임상택"                 # 관리자 이름(파이프라인 실행 권한)
setx JAMAK_ADMIN_PASSWORD "hky2312"        # 관리자 비번
setx JAMAK_NAMES "조기호,다른검수자"        # 검수자 이름들
setx JAMAK_PASSWORD "hky1004"              # 검수자 공용 비번
setx JAMAK_SECRET "<임의 64자리 hex>"       # 쿠키 서명키(재시작 후에도 로그인 유지)
uv run jamak serve --port 8711
```
- 관리자는 자기 이름 + 관리자비번, 검수자는 자기 이름 + 검수자비번으로 로그인.
- **관리자 전용**: 유튜브 링크→자막 만들기, 음성인식 다시/복구(로컬 GPU 파이프라인). 검수자는 검수·번역·내보내기만.
- 검수자 추가 = `setx JAMAK_NAMES "...,새사람"` → `deploy\restart-serve.cmd`. (새 검수자는 검수자 공용비번 사용)
- 레거시 개별비번 `JAMAK_AUTH="user:pw,..."`도 폴백으로 동작. 아무것도 미설정 = 무인증(로컬).
- 코드(Python) 수정은 **웹앱 재시작**해야 반영(`restart-serve.cmd`); 프론트 수정은 `npm run build` 후 새로고침. (push 자동배포는 경로 B에서.)

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

- **항상 켜두기 (관리자 없이)**: `deploy\start-serve.cmd`(웹앱)·`deploy\start-tunnel.cmd`(터널)를 실행하는 런처를 **시작프로그램 폴더**(`shell:startup` = `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`)에 두면 로그인 시 자동 기동. `JAMAK_AUTH`는 `setx JAMAK_AUTH "user:pw"`로 사용자 환경변수에 영구 저장(새 프로세스가 읽음). → 이게 이 인스턴스 세팅 방식.
- **더 견고하게 (관리자, 로그인 없이도)**: 관리자 PowerShell에서 `& "C:\Program Files (x86)\cloudflared\cloudflared.exe" service install` → 터널이 부팅 시(로그인 전에도) 자동. 웹앱은 nssm으로 서비스화.
- **비번 바꾸기**: `setx JAMAK_AUTH "reviewer1:새비번,reviewer2:다른비번"` 후 웹앱 재시작.
- **동시성**: SQLite `busy_timeout=30s`로 소수 검수자(서로 다른 영상)는 안전. **같은 영상 구조(나누기·합치기)를 두 명이 동시 편집하면 idx 경합 위험** — 영상별로 나눠 맡기. 완전한 잠금은 이연(ADR-0007 후속, SQLite→PG 시).
- **백업(내장)**: `serve`가 시작 시 + `--backup-hours`(기본 24h)마다 `data/backups/jamak-<시각>.db`로 자동 백업(최근 30개 유지, SQLite 온라인 백업 = 라이브 중 안전). 수동은 `uv run jamak backup`. `data/seeds/`도 보존. 더 안전하게: `data/backups/`를 OneDrive/구글드라이브 폴더로 두면 오프사이트.
- **디스크(audio)**: `jamak run`은 기본으로 STT 후 `audio.wav`(~112MB/시간)를 지움(검수·단어맵·다듬기는 stt.json만 필요, 재전사 시 재다운로드). 원본 오디오를 남기려면 `--keep-audio`. → 몇백 개 1~2시간 영상도 디스크 안 참.
- **비용**: 파이프라인·번역은 여전히 로컬 실행 → Claude API 영상당 과금. 검수 자체는 무API.
- **비밀**: `ANTHROPIC_API_KEY`·`JAMAK_AUTH`는 호스트 환경변수로만. 프론트 번들에 절대 넣지 않음.
- **HTTPS**: Cloudflare/Tailscale가 TLS 종단 제공 → 앱은 평문 127.0.0.1로 충분.

## 다음 단계 (규모 커지면)

검수자가 늘거나 항상 켜두기가 부담되면 **경로 B(클라우드 웹앱 + 로컬 GPU)** 로:
SQLite→Postgres, 파일→오브젝트스토리지(R2/S3), 세션 인증, per-(job,lang) 잠금.
= ADR-0007의 "future" 절 + `translate-audit` 감사가 남긴 동시성 항목.
