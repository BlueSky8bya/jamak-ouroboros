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

앱 자체 로그인 — **스타일된 인앱 로그인 폼**(크롬 기본 팝업 아님) + 서명 세션 쿠키. 눈모양 토글로 비번 보기. **역할은 어느 비번이 맞는지로 결정**(이름은 표시용):

```powershell
setx JAMAK_ADMIN_PASSWORD "<관리자-비번>"    # 이 비번 = 관리자(파이프라인 실행 권한)
setx JAMAK_PASSWORD "<검수자-비번>"          # 이 비번 = 검수자(검수/번역/내보내기만)
setx JAMAK_SECRET "<임의 64자리 hex>"       # 쿠키 서명키(재시작 후에도 로그인 유지)
uv run jamak serve --port 8711
```
- **관리자 비번** 입력 → 관리자, **검수자 비번** → 검수자, 둘 다 아니면 입장 불가. 이름은 "누가 접속 중" 칩용(선택).
- **관리자 전용**: 유튜브 링크→자막 만들기, 음성인식 다시/복구(로컬 GPU 파이프라인). 검수자는 검수·번역·내보내기만.
- **검수자 추가 = 검수자 비번만 알려주면 끝** (이름 등록·재시작 불필요). 특정인 차단은 검수자 비번 교체로 전체 재발급.
- 레거시 개별비번 `JAMAK_AUTH="user:pw,..."`도 폴백(이름이 `JAMAK_ADMINS`에 있으면 관리자, 아니면 검수자). 아무 비번도 미설정 = 무인증(로컬).
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

---

# 경로 B — 클라우드 웹앱 + 로컬 GPU (Railway + 전용 Postgres) — ADR-0008

**검수자는 관리자 PC가 꺼져 있어도 접속.** 검수 웹앱을 Railway에 상시 호스팅하고 데이터는
Railway Postgres 하나로 통일한다. 유튜브→자막 생성만 로컬 GPU(관리자 PC)에서 돈다.

아키텍처: 로컬 파이프라인과 클라우드 앱이 **같은 Postgres 하나**를 본다. stt.json은
`SttBlob` 테이블로 DB에 들어가 워드맵·타이밍다듬기가 클라우드에서 동작한다. `audio.wav`는
로컬에만(안 올림).

## 코드 스위치 (이미 반영됨)
- `DATABASE_URL` 있으면 Postgres, 없으면 기존 SQLite(로컬·터널 방식 100% 그대로).
- `Dockerfile`(node로 프론트 빌드 → python serve), `railway.json`(헬스체크 `/api/me`).
- `jamak migrate-to-cloud` 이관 명령.

## 0. Railway 프로젝트 + Postgres
1. https://railway.app 가입(GitHub 로그인). 이 저장소를 GitHub에 push 해 둔다.
2. **New Project → Deploy from GitHub repo** → 이 레포 선택. Railway가 `Dockerfile`을 자동 감지·빌드.
3. 같은 프로젝트에서 **New → Database → Add PostgreSQL**. 생성되면 Postgres 서비스의
   **Variables** 탭에 `DATABASE_URL`(내부용)·`DATABASE_PUBLIC_URL`(외부용)이 뜬다.

## 1. 웹앱 서비스 환경변수 (Variables 탭)
```
DATABASE_URL           = ${{Postgres.DATABASE_URL}}   # Railway 변수 참조(내부 네트워크)
JAMAK_ADMIN_PASSWORD   = <관리자-비번>                # 이 비번 = 관리자
JAMAK_PASSWORD         = <검수자-비번>                # 이 비번 = 검수자
JAMAK_SECRET           = <임의 64자리 hex>            # 쿠키 서명키(재배포에도 로그인 유지)
ANTHROPIC_API_KEY      = <검수 중 번역 버튼 쓸 거면>   # 검수만이면 불필요
```
- 역할은 **비번으로 결정** — 검수자 추가 = 검수자 비번만 공유(Railway 편집 불필요). `JAMAK_ADMINS`/`JAMAK_NAMES`는 인증에 불필요(있어도 무시).
- `${{Postgres.DATABASE_URL}}` = Railway의 서비스 간 변수 참조(같은 프로젝트 내부망, 무료 트래픽).
- 앱은 `postgres://`/`postgresql://` 어느 형태든 psycopg용으로 자동 정규화.
- 저장하면 Railway가 자동 재배포. 도메인은 **Settings → Networking → Generate Domain**.

## 2. 기존 데이터 1회 이관 (로컬에서 실행)
로컬 SQLite(+ 기존 stt.json)를 클라우드로 복사. **소스는 읽기전용**, PK id 보존.
Railway Postgres의 **공개 URL**(`DATABASE_PUBLIC_URL`, `...proxy.rlwy.net:port`)을 쓴다:
```powershell
uv run jamak migrate-to-cloud --to "postgresql://postgres:<pw>@<host>.proxy.rlwy.net:<port>/railway"
# 대상에 이미 job이 있으면 중단(중복 방지). 다시 밀어야 하면 --force.
```
`copied N job/segment/...` 로그 후 `migration complete`. 클라우드 URL 접속 → 3영상·세그먼트·
번역·timing_done 그대로 보이면 성공.

## 3. 새 영상 만들기 (로컬 GPU, 클라우드 DB에 직접 기록)
관리자 PC에서 `DATABASE_URL`을 **클라우드 공개 URL**로 지정하고 파이프라인 실행:
```powershell
$env:DATABASE_URL = "postgresql://postgres:<pw>@<host>.proxy.rlwy.net:<port>/railway"
uv run jamak run <youtube-url>      # STT는 로컬 GPU, 세그먼트+stt.json은 클라우드 DB로
```
- 끝나면 검수자가 클라우드 URL에서 바로 그 영상 검수 가능(PC 꺼도 됨).
- `audio.wav`는 로컬에만 생겼다가 STT 후 기본 삭제. 클라우드로 안 올라감.
- 영속 설정하려면 `setx DATABASE_URL "..."`(단, **로컬 SQLite로 돌아가려면 이 변수를 지워야** 함).

## 4. 자동배포
GitHub `main`에 push하면 Railway가 자동 재빌드·재배포. (경로 A의 "코드 고치면 재시작" 수작업 불필요.)

## 5. 백업 (권장) — 클라우드 DB → 로컬 오프사이트 스냅샷
`jamak backup-cloud` 이 클라우드 Postgres를 **로컬 gzip SQLite 파일**로 스냅샷(pg_dump 불필요).
DB는 텍스트 전용(오디오/영상 없음)이라 수백 개 영상도 <1GB, gzip ~5~10× → 스냅샷 수백 KB~수십 MB.
복구: gunzip 후 `data/jamak.db`로 쓰거나 `migrate-to-cloud --to <새 PG> --force`.

```powershell
# 1회 설정 (영구): 클라우드 URL + 백업 폴더(구글드라이브 동기 폴더 권장)
setx DATABASE_URL "postgresql://postgres:...@tokaido.proxy.rlwy.net:15053/railway"
setx JAMAK_BACKUP_DIR "G:\내 드라이브\jamak-backups"
# 수동 실행
uv run jamak backup-cloud                 # DATABASE_URL·JAMAK_BACKUP_DIR 사용, 최근 12개 유지
```
자동(주간): `deploy\backup-cloud.cmd` 을 Windows 작업 스케줄러에 주 1회 등록(`schtasks /Create
/TN jamak-backup-cloud /TR "...backup-cloud.cmd" /SC WEEKLY /D SUN /ST 03:00 /F`). 위 두 env가
설정돼 있어야 태스크가 동작. 런처는 시크릿 없음(URL은 env에서 읽음).

주의: `setx DATABASE_URL`을 영구 설정하면 **로컬 `jamak` 전 명령이 클라우드를 봄**(로컬 SQLite
아님) — 새 영상 `jamak run`도 자동으로 클라우드에 씀. 이게 경로 B의 정상 상태. 로컬 SQLite로
되돌리려면 이 변수를 지운다.

## 주의 / 이연
- **retranscribe·repair는 클라우드에서 GPU 없음.** 재인식이 필요하면 관리자가 **로컬에서**
  `DATABASE_URL` 지정 후 `jamak run <url> --fresh`. (클라우드 버튼 가드는 후속 항목.)
- 클라우드는 `--backup-hours 0`(SQLite 온라인백업은 PG에 무의미) — DB 백업은 Railway가 담당.
- 동시 편집 잠금(per-(job,lang) idx)은 여전히 이연(translate-audit 항목).
- 다른 호스트(Neon/Render)로 옮기려면 `DATABASE_URL`만 교체 — 코드 변경 0.
