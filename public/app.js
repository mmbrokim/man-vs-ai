// Man vs AI 봉인 확인 페이지
// 이 파일은 일부러 압축하지 않았습니다. 누구나 읽고 확인할 수 있습니다.
// 이 페이지는 seals.json 을 읽어 오기만 하고, 입력한 내용을 어디에도 보내지 않습니다.

"use strict";

// ---------- 해시 계산 규칙 (tools/common.py 와 같아야 합니다) ----------
// 1) 앞뒤 공백 제거  2) 유니코드 NFC 정규화  3) UTF-8 바이트로 SHA-256
const TRIM = /^[ \t\n\r\v\f\u00a0\u3000\ufeff]+|[ \t\n\r\v\f\u00a0\u3000\ufeff]+$/g;

function normalize(text) {
  return text.replace(TRIM, "").normalize("NFC");
}

async function sha256Hex(text) {
  const bytes = new TextEncoder().encode(normalize(text));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// ---------- 공통 ----------
let seals = [];

const $ = (id) => document.getElementById(id);

function icon(name) {
  return `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function kickoffParts(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return null;
  const parts = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul", month: "numeric", day: "numeric", weekday: "short",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(d);
  const get = (t) => (parts.find((p) => p.type === t) || {}).value || "";
  return { date: `${get("month")}/${get("day")}(${get("weekday")})`, time: `${get("hour")}:${get("minute")}` };
}

function safeUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

// ---------- 종목 ----------
// 회차 번호(EP)는 종목과 상관없이 하나로 이어집니다. sport 칸이 없는 회차는 축구입니다.
// 축구 원문:   EP회차|홈승 또는 무 또는 원정승|랜덤
// 격투기 원문: EP회차|이긴 선수|KO/TKO 또는 서브미션 또는 판정|랜덤
//   격투기는 승자와 승리 방식을 모두 맞혀야 맞힌 것입니다. 무승부는 선택지에 없습니다.
const SPORTS = { football: "축구", mma: "격투기" };
const ANSWERS = ["홈승", "무", "원정승"]; // 축구 기록은 이 세 가지로 하고, 화면에는 팀 이름으로 보여 줍니다.
const MMA_METHODS = ["KO/TKO", "서브미션", "판정"];
// 결과에만 쓰는 값. 무승부와 무효 경기는 채점하지 않습니다.
const MMA_DRAW = "무승부";
const MMA_NO_CONTEST = "무효";

function sportOf(s) {
  return s.sport === "mma" ? "mma" : "football";
}

function teams(s) {
  const parts = s.match.split(/\s+vs\.?\s+/i);
  return parts.length === 2 ? { home: parts[0], away: parts[1] } : { home: "홈팀", away: "원정팀" };
}

function label(s, answer) {
  if (!answer) return null;
  if (sportOf(s) === "mma") {
    if (answer === MMA_DRAW) return "무승부";
    if (answer === MMA_NO_CONTEST) return "무효 경기";
    if (answer.includes("|")) return answer.replace("|", " ");
    return `${answer} 승`;
  }
  const t = teams(s);
  if (answer === "홈승") return `${t.home} 승`;
  if (answer === "원정승") return `${t.away} 승`;
  if (answer === "무") return "무승부";
  return answer;
}

// AI의 답은 공개된 원문의 두 번째 칸에서만 읽습니다. 공개 전에는 알 수 없습니다.
function aiPick(s) {
  return s.revealed_text ? s.revealed_text.split("|")[1] : null;
}

// 격투기 원문의 세 번째 칸: AI가 고른 승리 방식
function aiMethod(s) {
  if (!s.revealed_text) return null;
  const parts = s.revealed_text.split("|");
  return parts.length === 4 ? parts[2] : null;
}

// ---------- 정식 회차와 특별 경기 ----------
// 정식 회차: ep 번호 (EP1, EP2 …), 누적 스코어에 들어갑니다.
// 특별 경기: special: true, sp 번호 (SP1 …). 사람 쪽은 댓글 대신 제작자 예측이고, 누적 스코어에는 들어가지 않습니다.
function code(s) {
  return s.special ? `SP${s.sp}` : `EP${s.ep}`;
}

function findByCode(c) {
  return seals.find((s) => code(s) === c.toUpperCase()) || null;
}

// 사람 쪽 답: 정식 회차는 댓글 다수결, 특별 경기는 제작자 예측
function humanSide(s) {
  return s.special ? s.creator : s.human;
}

function humanLabel(s) {
  return s.special ? "제작자" : "사람";
}

function humanPick(s) {
  const h = humanSide(s);
  return h ? h.pick : null;
}

function humanMethod(s) {
  const h = humanSide(s);
  return h ? h.method || null : null;
}

function outcome(s) {
  return s.result ? s.result.outcome : null;
}

// 채점하는 회차인지 (격투기의 무승부, 무효 경기는 채점하지 않습니다)
function scored(s) {
  const out = outcome(s);
  return !!out && out !== MMA_NO_CONTEST && !(sportOf(s) === "mma" && out === MMA_DRAW);
}

// 맞혔는지. 격투기는 승자와 승리 방식이 모두 같아야 합니다.
function hit(s, answer, method) {
  if (!answer || !scored(s)) return false;
  if (answer !== outcome(s)) return false;
  return sportOf(s) === "football" || method === s.result.method;
}

function mark(s, answer, method) {
  if (!answer || !scored(s)) return "";
  return hit(s, answer, method) ? `<span class="ok">${icon("check")}</span>` : `<span class="ng">${icon("x")}</span>`;
}

// ---------- 누적 스코어 ----------
function renderScoreboard() {
  const box = $("scoreboard");
  if (!seals.length) { box.hidden = true; return; }
  // 누적 스코어는 종목과 상관없이 모든 회차를 합쳐서 셉니다.
  const done = seals.filter((s) => !s.special && scored(s) && aiPick(s) && humanPick(s));
  $("score-human").textContent = done.filter((s) => hit(s, humanPick(s), humanMethod(s))).length;
  $("score-ai").textContent = done.filter((s) => hit(s, aiPick(s), aiMethod(s))).length;
  $("score-sub").textContent = done.length
    ? `맞힌 경기 수 · 결과가 나온 ${done.length}경기 기준`
    : "첫 결과를 기다리고 있습니다";
  box.hidden = false;
}

// ---------- 목록 화면 ----------
function resultLine(s) {
  // 축구: 2-1 / 격투기: KO/TKO · 2R
  if (sportOf(s) === "football") return s.result.score;
  return [s.result.method, s.result.round ? `${s.result.round}R` : null].filter(Boolean).join(" · ") || "-";
}

function rightSide(s) {
  const out = outcome(s);
  if (out && !scored(s)) {
    return `<p class="r-label">${escapeHtml(label(s, out))}</p><p class="r-who">채점하지 않습니다</p>`;
  }
  if (out) {
    const ai = aiPick(s);
    const hu = humanPick(s);
    const who = [
      hu ? `${humanLabel(s)} ${hit(s, hu, humanMethod(s)) ? "✓" : "✗"}` : null,
      ai ? `AI ${hit(s, ai, aiMethod(s)) ? "✓" : "✗"}` : null,
    ].filter(Boolean).join(" · ");
    return `
      <p class="r-score${sportOf(s) === "mma" ? " small-score" : ""}">${escapeHtml(resultLine(s))}</p>
      <p class="r-label">${escapeHtml(label(s, out))}</p>
      <p class="r-who">${who}</p>`;
  }
  const started = new Date(s.kickoff) <= new Date();
  return `<p class="r-wait">${started ? "결과 대기" : "경기 전"}</p>`;
}

// ---------- 종목 탭 (목록만 거릅니다. 누적 스코어는 항상 전체) ----------
let filter = "all";

function renderTabs() {
  const tabs = $("sport-tabs");
  const present = new Set(seals.map(sportOf));
  if (present.size < 2) { tabs.hidden = true; filter = "all"; return; }
  const items = [["all", "전체"], ...Object.entries(SPORTS)];
  tabs.innerHTML = items.map(([key, name]) =>
    `<button type="button" class="tab${filter === key ? " on" : ""}" data-sport="${key}" aria-pressed="${filter === key}">${name}</button>`
  ).join("");
  tabs.hidden = false;
}

function sportChip(s) {
  const k = sportOf(s);
  return `<span class="chip ${k}">${icon(k === "mma" ? "glove" : "ball")}${SPORTS[k]}</span>`;
}

// 목록에 짧게 보여 줄 예측: 축구 '맨시티 승', 격투기 '페레이라 KO/TKO'
function pickText(s, answer, method) {
  if (sportOf(s) === "mma" && method) return `${answer.split(/\s+/).pop()} ${method}`;
  return label(s, answer);
}

function specialChip(s) {
  return s.special ? `<span class="chip special">${icon("star")}특별 경기</span>` : "";
}

function matchTitle(s) {
  return sportOf(s) === "mma" ? `${s.fighter_a} vs ${s.fighter_b}` : s.match;
}

function renderList() {
  renderScoreboard();
  renderTabs();
  const list = $("seal-list");
  const shown = seals.filter((s) => filter === "all" || sportOf(s) === filter);
  if (!shown.length) {
    list.innerHTML = `<p class="empty">아직 봉인된 회차가 없습니다.</p>`;
    return;
  }
  const sorted = [...shown].sort((a, b) => new Date(b.kickoff) - new Date(a.kickoff)); // 최신 경기가 위로
  list.innerHTML = sorted.map((s) => {
    const k = kickoffParts(s.kickoff);
    const ai = aiPick(s);
    const hu = humanPick(s);
    return `
      <a class="row card${s.special ? " special" : ""}" href="#${code(s).toLowerCase()}">
        <div class="row-left">
          <p class="row-head"><span class="ep">${code(s)}</span>${sportChip(s)}${specialChip(s)}${k ? `<span class="date">${k.date}</span>` : ""}</p>
          ${s.event ? `<p class="row-event">${escapeHtml(s.event)}</p>` : ""}
          <p class="row-match">${escapeHtml(matchTitle(s))}</p>
          <p class="row-pick"><span class="who">AI</span>${ai
            ? `<b>${escapeHtml(pickText(s, ai, aiMethod(s)))}</b>${mark(s, ai, aiMethod(s))}`
            : `<span class="muted">${icon("lock")}봉인 중</span>`}</p>
          <p class="row-pick"><span class="who">${humanLabel(s)}</span>${hu
            ? `<b>${escapeHtml(pickText(s, hu, humanMethod(s)))}</b>${mark(s, hu, humanMethod(s))}`
            : `<span class="muted">집계 전</span>`}</p>
        </div>
        <div class="row-right">${rightSide(s)}</div>
      </a>`;
  }).join("");
}

// ---------- 상세 화면 ----------
function voteRow(text, n, total, top, sub) {
  const pct = Math.round((n / total) * 100);
  return `
      <div class="vote-row${top ? " top" : ""}${sub ? " sub" : ""}">
        <span class="vote-label">${escapeHtml(text)}</span>
        <span class="vote-bar"><span class="vote-fill" style="width:${pct}%"></span></span>
        <span class="vote-num">${n.toLocaleString("ko-KR")}표 · ${pct}%</span>
      </div>`;
}

function renderVotes(s) {
  const h = s.human;
  if (!h || !h.total) return `<p class="muted small">경기 시작 직후 댓글을 집계해 올립니다.</p>`;
  let rows;
  if (sportOf(s) === "mma") {
    // 선수별 합계 → 그 아래 승리 방식별 표
    rows = [s.fighter_a, s.fighter_b].map((f) => {
      const per = MMA_METHODS.map((m) => [m, h.votes[`${f}|${m}`] || 0]);
      const sum = per.reduce((acc, [, n]) => acc + n, 0);
      return voteRow(`${f} 승`, sum, h.total, f === h.pick, false) +
        per.map(([m, n]) => voteRow(m, n, h.total, f === h.pick && m === h.method, true)).join("");
    }).join("");
  } else {
    rows = ANSWERS.map((a) => voteRow(label(s, a), h.votes[a] || 0, h.total, a === h.pick, false)).join("");
  }
  const file = h.votes_file
    ? ` · <a href="${escapeHtml(h.votes_file)}" download>${icon("file")}집계 댓글 목록</a>`
    : "";
  return `
    <p class="block-sub">총 ${h.total.toLocaleString("ko-KR")}표 · 경기 시작 전 댓글 기준${file}</p>
    ${rows}`;
}

function pickBox(s, who, iconName, answer, waitText, method) {
  if (!answer) {
    return `<div class="pick wait"><span class="who-s">${icon(iconName)}${who}</span><span class="ans">${waitText}</span></div>`;
  }
  const state = !scored(s) ? "" : hit(s, answer, method) ? " hit" : " miss";
  const how = method ? `<span class="how">${escapeHtml(method)}</span>` : "";
  return `<div class="pick${state}"><span class="who-s">${icon(iconName)}${who}</span><span class="ans">${escapeHtml(label(s, answer))}${mark(s, answer, method)}</span>${how}</div>`;
}

function finalLine(s) {
  const out = outcome(s);
  if (!out) return "";
  if (sportOf(s) === "football") {
    return `<p class="final">경기 결과 <b>${escapeHtml(s.result.score)}</b> · ${escapeHtml(label(s, out))}</p>`;
  }
  if (!scored(s)) return `<p class="final">경기 결과 <b>${escapeHtml(label(s, out))}</b> · 채점하지 않습니다</p>`;
  return `<p class="final">경기 결과 <b>${escapeHtml(label(s, out))}</b> · ${escapeHtml(resultLine(s))}</p>`;
}

function renderDetail(s) {
  const k = kickoffParts(s.kickoff);
  const open = !!s.revealed_text;
  const video = s.video && safeUrl(s.video);
  $("detail-card").innerHTML = `
    <article class="card detail">
      <div class="seal-head">
        <div>
          <p class="ep-big">${code(s)} ${sportChip(s)}${specialChip(s)}</p>
          ${s.event ? `<p class="row-event">${escapeHtml(s.event)}</p>` : ""}
          <p class="seal-title">${escapeHtml(matchTitle(s))}</p>
        </div>
        ${open
          ? `<span class="badge open">${icon("mail-open")}공개됨</span>`
          : `<span class="badge sealed">${icon("lock")}봉인 중</span>`}
      </div>
      <p class="seal-meta">${k ? `${k.date} ${k.time} ${sportOf(s) === "mma" ? "시작 예정" : "킥오프"}` : ""}</p>

      ${finalLine(s)}
      <div class="picks">
        ${pickBox(s, humanLabel(s), "users", humanPick(s), "집계 전", humanMethod(s))}
        ${pickBox(s, "AI", "cpu", aiPick(s), "봉인 중", aiMethod(s))}
      </div>

      ${s.special
        ? `<div class="block"><p class="block-title">${icon("star")}특별 경기</p>
            <p class="muted small">이번 경기는 댓글 대신 제작자의 예측과 AI의 예측을 비교합니다. 누적 스코어에는 들어가지 않습니다.</p></div>`
        : `<div class="block">
        <p class="block-title">${icon("users")}사람들의 선택</p>
        ${renderVotes(s)}
      </div>`}

      <div class="block">
        <p class="block-title">${icon("lock")}AI 답 봉인</p>
        <p class="label">봉인값 (영상 화면의 값과 같아야 합니다)</p>
        <p class="hash mono">${escapeHtml(s.hash)}</p>
        ${open
          ? `<p class="label">공개된 원문</p><p class="revealed mono">${escapeHtml(s.revealed_text)}</p>`
          : `<p class="muted small">원문은 결과 편에서 공개합니다.</p>`}
        <div class="actions">
          <button class="btn" type="button" data-copy="${escapeHtml(s.hash)}">${icon("copy")}봉인값 복사</button>
          ${open ? `<button class="btn" type="button" data-fill="${code(s)}">${icon("down")}원문 채우기</button>` : ""}
          ${video ? `<a class="btn" href="${escapeHtml(video)}" target="_blank" rel="noopener">${icon("play")}영상 보기</a>` : ""}
        </div>
      </div>
    </article>`;
}

// ---------- 화면 전환 (#ep1, #sp1 이면 상세, 아니면 목록) ----------
function route() {
  const m = location.hash.match(/^#((?:ep|sp)\d+)$/i);
  const s = m ? findByCode(m[1]) : null;
  if (s) {
    renderDetail(s);
    $("result").hidden = true;
    $("text-input").value = "";
    $("hash-input").value = "";
    $("text-input").placeholder = sportOf(s) === "mma"
      ? "예) EP0|선수이름|판정|ExampleOnly12345"
      : "예) EP0|무|ExampleOnly12345";
    $("view-list").hidden = true;
    $("view-detail").hidden = false;
    document.title = `${code(s)} ${matchTitle(s)} · Man vs AI`;
  } else {
    renderList();
    $("view-detail").hidden = true;
    $("view-list").hidden = false;
    document.title = "Man vs AI · AI 답 봉인 확인";
  }
  window.scrollTo(0, 0);
}

// ---------- 원문 확인 ----------
function verdict(kind, html) {
  const name = kind === "ok" ? "check" : kind === "ng" ? "x" : "mail";
  return `<div class="verdict ${kind}">${icon(name)}<span>${html}</span></div>`;
}

async function verify() {
  const text = $("text-input").value;
  if (!normalize(text)) {
    $("result").hidden = false;
    $("result-hash").textContent = "";
    $("result-verdicts").innerHTML = verdict("ng", "원문을 먼저 입력해 주세요.");
    return;
  }

  let hash;
  try {
    hash = await sha256Hex(text);
  } catch {
    $("result").hidden = false;
    $("result-verdicts").innerHTML = verdict("ng", "이 브라우저에서는 해시를 계산할 수 없습니다. 최신 브라우저에서 열어 주세요.");
    return;
  }

  const out = [];
  const m = normalize(text).match(/^((?:EP|SP)\d+)\|/);
  const ep = m ? m[1] : null;
  const seal = ep !== null ? findByCode(ep) : null;

  if (seal) {
    out.push(hash === seal.hash
      ? verdict("ok", `<b>일치합니다.</b> ${ep} 봉인값과 같습니다.`)
      : verdict("ng", `<b>일치하지 않습니다.</b> ${ep} 봉인값과 다릅니다. 원문을 한 글자도 빠짐없이 입력했는지 확인해 주세요.`));
  } else {
    const any = seals.find((s) => s.hash === hash);
    out.push(any
      ? verdict("ok", `<b>일치합니다.</b> ${code(any)} 봉인값과 같습니다.`)
      : verdict("ng", ep !== null
        ? `${ep} 회차를 목록에서 찾지 못했습니다.`
        : `<b>일치하는 회차가 없습니다.</b> 원문은 EP 또는 SP로 시작합니다.`));
  }

  const videoHash = $("hash-input").value.trim().toLowerCase();
  if (videoHash) {
    out.push(videoHash === hash
      ? verdict("ok", "<b>영상 속 봉인값과도 일치합니다.</b>")
      : verdict("ng", "<b>영상 속 봉인값과 다릅니다.</b> 입력한 봉인값을 다시 확인해 주세요."));
  }

  $("result-hash").textContent = hash;
  $("result-verdicts").innerHTML = out.join("");
  $("result").hidden = false;
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 1600);
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  toast("봉인값을 복사했습니다");
}

// ---------- 이벤트 ----------
$("detail-card").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  if (btn.dataset.copy) copy(btn.dataset.copy);
  if (btn.dataset.fill) {
    const s = findByCode(btn.dataset.fill);
    if (!s || !s.revealed_text) return;
    $("text-input").value = s.revealed_text;
    $("verify").scrollIntoView({ behavior: "smooth", block: "start" });
    verify();
  }
});

$("sport-tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-sport]");
  if (!btn) return;
  filter = btn.dataset.sport;
  renderList();
});

$("verify-btn").addEventListener("click", verify);
$("text-input").addEventListener("keydown", (e) => { if (e.key === "Enter") verify(); });
$("hash-input").addEventListener("keydown", (e) => { if (e.key === "Enter") verify(); });
window.addEventListener("hashchange", route);

// ---------- 시작 ----------
fetch("seals.json", { cache: "no-store" })
  .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
  .then((data) => { seals = Array.isArray(data) ? data : []; route(); })
  .catch(() => { $("seal-list").innerHTML = `<p class="empty">회차 목록을 불러오지 못했습니다. 잠시 후 다시 열어 주세요.</p>`; });
