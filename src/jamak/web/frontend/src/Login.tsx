import { useState } from "react";
import { login, type Me } from "./api";

/** Styled in-app login (replaces the browser's Basic-auth popup): name + shared
 *  password with a show/hide eye toggle. */
export function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !pw || busy) return;
    setBusy(true);
    setError("");
    try {
      onLogin(await login(name.trim(), pw));
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <div className="login-head">
          <span className="login-logo">자막</span>
          <div>
            <h1>자막 검수</h1>
            <p>이름과 비밀번호를 입력하세요</p>
          </div>
        </div>

        <label className="login-field">
          <span>이름</span>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="예: 홍길동"
            autoComplete="username"
          />
        </label>

        <label className="login-field">
          <span>비밀번호</span>
          <div className="login-pw">
            <input
              type={show ? "text" : "password"}
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              placeholder="비밀번호"
              autoComplete="current-password"
            />
            <button
              type="button"
              className="login-eye"
              onClick={() => setShow((s) => !s)}
              title={show ? "숨기기" : "보기"}
              aria-label={show ? "비밀번호 숨기기" : "비밀번호 보기"}
            >
              {show ? "🙈" : "👁"}
            </button>
          </div>
        </label>

        {error && <div className="login-error">{error}</div>}

        <button className="login-submit" type="submit" disabled={busy || !name.trim() || !pw}>
          {busy ? "확인 중..." : "들어가기"}
        </button>
      </form>
    </div>
  );
}
