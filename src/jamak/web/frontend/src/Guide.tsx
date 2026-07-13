/** 어르신 검수자용 사용법 화면 (in-app tutorial).
 *
 *  Big text, plain language, scenario-based (이럴 때 → 이렇게), with tiny
 *  looping CSS demos so a reviewer sees the motion, not just reads about it.
 *  Self-paced: opens as a full-screen overlay, closes with a big button, can be
 *  reopened any time from the landing header. No backend — pure presentation.
 */

function Key({ children }: { children: React.ReactNode }) {
  return <kbd className="g-key">{children}</kbd>;
}

/** one "이럴 때 → 이렇게" card with an optional mini demo on the left */
function Scene({
  when,
  doThis,
  keys,
  demo,
}: {
  when: string;
  doThis: React.ReactNode;
  keys?: React.ReactNode;
  demo?: React.ReactNode;
}) {
  return (
    <div className="g-scene">
      {demo && <div className="g-demo">{demo}</div>}
      <div className="g-scene-body">
        <div className="g-when">
          <span className="g-when-tag">이럴 때</span> {when}
        </div>
        <div className="g-do">
          <span className="g-do-tag">이렇게</span>
          <span>{doThis}</span>
        </div>
        {keys && <div className="g-keys">{keys}</div>}
      </div>
    </div>
  );
}

export function Guide({ onClose }: { onClose: () => void }) {
  return (
    <div className="g-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="g-panel" role="dialog" aria-label="사용법">
        <div className="g-head">
          <h2>📖 자막 검수, 이렇게 하시면 돼요</h2>
          <button className="g-close" onClick={onClose}>
            ✕ 닫기
          </button>
        </div>
        <p className="g-lead">
          천천히 보셔도 괜찮아요. 이 화면은 언제든 다시 열 수 있어요. 무엇을 눌러도
          <b> 되돌리기(↶)</b>가 되니 마음 편히 해보세요.
        </p>

        {/* ── 큰 흐름 ── */}
        <section className="g-sec">
          <h3>큰 순서는 딱 세 가지예요</h3>
          <ol className="g-flow">
            <li>
              <span className="g-flow-n">1</span>
              <span>
                영상을 <b>틀어놓고</b>, 지금 나오는 자막이 <b>말과 맞는지</b> 귀로 들어요.
                지금 말하는 낱말이 <b className="g-hl">노랗게</b> 따라오니 눈으로 짚기 쉬워요.
              </span>
            </li>
            <li>
              <span className="g-flow-n">2</span>
              <span>
                맞으면 <Key>Enter</Key> (확인하고 다음으로). 틀렸으면 그 자막을 눌러
                <b> 고치고</b> 다시 <Key>Enter</Key>.
              </span>
            </li>
            <li>
              <span className="g-flow-n">3</span>
              <span>
                다 끝나면 아래 <b>자막 받기</b>를 눌러요. 받기 전에 빠진 곳이 있으면
                알려드려요.
              </span>
            </li>
          </ol>
        </section>

        {/* ── 시나리오 ── */}
        <section className="g-sec">
          <h3>이럴 때는 이렇게 하세요</h3>
          <div className="g-scenes">
            <Scene
              when="자막이 말과 맞아요"
              doThis={
                <>
                  <b>Enter</b> 한 번. 확인 표시가 되고 다음 자막으로 넘어가요.
                </>
              }
              keys={<Key>Enter</Key>}
              demo={
                <div className="demo-confirm" aria-hidden>
                  <div className="dc-row">
                    <span className="dc-text">안녕하세요 여러분</span>
                    <span className="dc-check">✓</span>
                  </div>
                </div>
              }
            />

            <Scene
              when="글자가 틀렸어요"
              doThis={
                <>
                  그 자막 칸을 <b>누르고</b> 틀린 글자를 고친 뒤 <b>Enter</b>.
                </>
              }
              keys={
                <>
                  <Key>클릭</Key> <span className="g-then">→ 고치기 →</span> <Key>Enter</Key>
                </>
              }
            />

            <Scene
              when="지금 어디를 듣고 있는지 눈에 안 들어와요"
              doThis={
                <>
                  영상을 틀어두면 <b>지금 말하는 낱말</b>이 자막 안에서 노랗게 움직여요.
                </>
              }
              demo={
                <div className="demo-karaoke" aria-hidden>
                  <span>양산</span> <span>안</span> <span>쓰면</span> <span>피부에</span>{" "}
                  <span>안 좋아요</span>
                </div>
              }
            />

            <Scene
              when="문장 중간의 한 낱말만 다시 듣고 싶어요"
              doThis={
                <>
                  그 <b>낱말을 누르세요</b>. 그 지점부터 다시 들려드려요.
                </>
              }
              keys={<Key>낱말 클릭</Key>}
            />

            <Scene
              when="잘 안 들려서 지금은 못 정하겠어요"
              doThis={
                <>
                  <b>🙉 잘 안 들림</b>을 누르세요. 건너뛰고, 마지막에 <b>느리게(0.75배)</b>{" "}
                  다시 들려드려요. 억지로 지금 안 정해도 돼요.
                </>
              }
              keys={<Key>Alt</Key>}
            />

            <Scene
              when="실수했어요 / 방금 걸 되돌리고 싶어요"
              doThis={
                <>
                  <b>Alt + Z</b> (또는 아래 <b>↶</b> 버튼). 한 번에 하나씩 되돌아가요.
                </>
              }
              keys={
                <>
                  <Key>Alt</Key> + <Key>Z</Key>
                </>
              }
            />

            <Scene
              when="글씨가 작아서 잘 안 보여요"
              doThis={
                <>
                  왼쪽 위 <b>글씨 크게</b> 버튼을 누르세요. 자막·버튼이 커져요.
                </>
              }
              keys={<Key>글씨 크게</Key>}
            />

            <Scene
              when="자막이 뜨고 사라지는 '시간'은 언제 맞추나요?"
              doThis={
                <>
                  <b>내용(글자)부터</b> 다 보시고, 그 다음 <b>② 타이밍</b> 탭으로 가세요.
                  거기서 <b>✨ 타이밍 자동 정리</b>를 누르면 기계가 먼저 맞춰줘요. 내용 볼
                  때는 시간은 신경 안 쓰셔도 돼요.
                </>
              }
              keys={<Key>② 타이밍 탭</Key>}
            />
          </div>
        </section>

        {/* ── 물 흐르듯 하는 요령 ── */}
        <section className="g-sec">
          <h3>물 흐르듯 하는 요령</h3>
          <ul className="g-tips">
            <li>
              <b>손을 키보드에 두세요.</b> <Key>Tab</Key>으로 재생/멈춤, <Key>Enter</Key>로
              확인+다음. 마우스 없이도 척척 넘어가요.
            </li>
            <li>
              <b>완벽하게 하려고 멈추지 마세요.</b> 애매하면 <b>🙉 잘 안 들림</b>으로
              넘기고 계속 가세요. 남은 건 마지막에 모아서 다시 들어요.
            </li>
            <li>
              <b>‘안심’ 자막은 한 번에.</b> 기계 둘이 똑같이 들은 쉬운 자막은{" "}
              <b>✅ 안심 확인</b>으로 한꺼번에 넘기고, 어려운 것만 보세요.
            </li>
            <li>
              <b>다시 듣기.</b> 방금 그 자막을 처음부터 또 듣고 싶으면 <Key>Ctrl</Key> +{" "}
              <Key>\</Key> (또는 ⏮ 구간처음).
            </li>
          </ul>
        </section>

        {/* ── 단축키 요약 ── */}
        <section className="g-sec">
          <h3>자주 쓰는 단축키 (이것만 알아도 충분해요)</h3>
          <div className="g-keytable">
            {[
              [<Key key="e">Enter</Key>, "확인하고 다음 자막으로"],
              [<Key key="t">Tab</Key>, "재생 / 멈춤"],
              [
                <span key="s">
                  <Key>Ctrl</Key> + <Key>←</Key> / <Key>→</Key>
                </span>,
                "3초 뒤로 / 앞으로",
              ],
              [
                <span key="z">
                  <Key>Alt</Key> + <Key>Z</Key>
                </span>,
                "방금 한 것 되돌리기",
              ],
              [
                <span key="h">
                  <Key>Alt</Key> + <Key>H</Key>
                </span>,
                "잘 안 들림 (나중에 다시)",
              ],
              [
                <span key="r">
                  <Key>Ctrl</Key> + <Key>\</Key>
                </span>,
                "이 자막 처음부터 다시 듣기",
              ],
            ].map(([k, d], i) => (
              <div className="g-krow" key={i}>
                <span className="g-kcol">{k}</span>
                <span className="g-dcol">{d}</span>
              </div>
            ))}
          </div>
        </section>

        <div className="g-foot">
          <button className="g-close big" onClick={onClose}>
            알겠어요, 시작할게요
          </button>
        </div>
      </div>
    </div>
  );
}
