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

// 기록은 홈승/무/원정승으로 하지만, 화면에는 팀 이름으로 보여 줍니다.
const ANSWERS = ["홈승", "무", "원정승"];

function teams(s) {
  const parts = s.match.split(/\s+vs\.?\s+/i);
  return parts.length === 2 ? { home: parts[0], away: parts[1] } : { home: "홈팀", away: "원정팀" };
}

function label(s, answer) {
  if (!answer) return null;
  const t = teams(s);
  if (answer === "홈승") return `${t.home} 승`;
  if (answer === "원정승") return `${t.away} 승`;
  if (answer === "무") return "무승부";
  return answer;
}

// AI의 답은 공개된 원문(EP회차|답|랜덤 문자열)의 두 번째 칸에서만 읽습니다. 공개 전에는 알 수 없습니다.
function aiPick(s) {
  return s.revealed_text ? s.revealed_text.split("|")[1] : null;
}

function humanPick(s) {
  return s.human ? s.human.pick : null;
}

function outcome(s) {
  return s.result ? s.result.outcome : null;
}

function mark(answer, out) {
  if (!answer || !out) return "";
  return answer === out ? `<span class="ok">${icon("check")}</span>` : `<span class="ng">${icon("x")}</span>`;
}

// ---------- 누적 스코어 ----------
function renderScoreboard() {
  const box = $("scoreboard");
  if (!seals.length) { box.hidden = true; return; }
  const done = seals.filter((s) => outcome(s) && aiPick(s) && humanPick(s));
  $("score-human").textContent = done.filter((s) => humanPick(s) === outcome(s)).length;
  $("score-ai").textContent = done.filter((s) => aiPick(s) === outcome(s)).length;
  $("score-sub").textContent = done.length
    ? `맞힌 경기 수 · 결과가 나온 ${done.length}경기 기준`
    : "첫 결과를 기다리고 있습니다";
  box.hidden = false;
}

// ---------- 목록 화면 ----------
function rightSide(s) {
  const out = outcome(s);
  if (out) {
    const ai = aiPick(s);
    const hu = humanPick(s);
    const who = [
      hu ? `사람 ${hu === out ? "✓" : "✗"}` : null,
      ai ? `AI ${ai === out ? "✓" : "✗"}` : null,
    ].filter(Boolean).join(" · ");
    return `
      <p class="r-score">${escapeHtml(s.result.score)}</p>
      <p class="r-label">${escapeHtml(label(s, out))}</p>
      <p class="r-who">${who}</p>`;
  }
  const started = new Date(s.kickoff) <= new Date();
  return `<p class="r-wait">${started ? "결과 대기" : "경기 전"}</p>`;
}

function renderList() {
  renderScoreboard();
  const list = $("seal-list");
  if (!seals.length) {
    list.innerHTML = `<p class="empty">아직 봉인된 회차가 없습니다.</p>`;
    return;
  }
  const sorted = [...seals].sort((a, b) => b.ep - a.ep); // 최신 회차가 위로
  list.innerHTML = sorted.map((s) => {
    const k = kickoffParts(s.kickoff);
    const out = outcome(s);
    const ai = aiPick(s);
    const hu = humanPick(s);
    return `
      <a class="row card" href="#ep${s.ep}">
        <div class="row-left">
          <p class="row-head"><span class="ep">EP${s.ep}</span>${k ? `<span class="date">${k.date}</span>` : ""}</p>
          <p class="row-match">${escapeHtml(s.match)}</p>
          <p class="row-pick"><span class="who">AI</span>${ai
            ? `<b>${escapeHtml(label(s, ai))}</b>${mark(ai, out)}`
            : `<span class="muted">${icon("lock")}봉인 중</span>`}</p>
          <p class="row-pick"><span class="who">사람</span>${hu
            ? `<b>${escapeHtml(label(s, hu))}</b>${mark(hu, out)}`
            : `<span class="muted">집계 전</span>`}</p>
        </div>
        <div class="row-right">${rightSide(s)}</div>
      </a>`;
  }).join("");
}

// ---------- 상세 화면 ----------
function renderVotes(s) {
  const h = s.human;
  if (!h || !h.total) return `<p class="muted small">킥오프 직후 댓글을 집계해 올립니다.</p>`;
  const rows = ANSWERS.map((a) => {
    const n = h.votes[a] || 0;
    const pct = Math.round((n / h.total) * 100);
    return `
      <div class="vote-row${a === h.pick ? " top" : ""}">
        <span class="vote-label">${escapeHtml(label(s, a))}</span>
        <span class="vote-bar"><span class="vote-fill" style="width:${pct}%"></span></span>
        <span class="vote-num">${n.toLocaleString("ko-KR")}표 · ${pct}%</span>
      </div>`;
  }).join("");
  const file = h.votes_file
    ? ` · <a href="${escapeHtml(h.votes_file)}" download>${icon("file")}집계 댓글 목록</a>`
    : "";
  return `
    <p class="block-sub">총 ${h.total.toLocaleString("ko-KR")}표 · 킥오프 전 댓글 기준${file}</p>
    ${rows}`;
}

function pickBox(s, who, iconName, answer, waitText) {
  const out = outcome(s);
  if (!answer) {
    return `<div class="pick wait"><span class="who-s">${icon(iconName)}${who}</span><span class="ans">${waitText}</span></div>`;
  }
  const state = !out ? "" : answer === out ? " hit" : " miss";
  return `<div class="pick${state}"><span class="who-s">${icon(iconName)}${who}</span><span class="ans">${escapeHtml(label(s, answer))}${mark(answer, out)}</span></div>`;
}

function renderDetail(s) {
  const k = kickoffParts(s.kickoff);
  const open = !!s.revealed_text;
  const video = s.video && safeUrl(s.video);
  const out = outcome(s);
  $("detail-card").innerHTML = `
    <article class="card detail">
      <div class="seal-head">
        <div>
          <p class="ep-big">EP${s.ep}</p>
          <p class="seal-title">${escapeHtml(s.match)}</p>
        </div>
        ${open
          ? `<span class="badge open">${icon("mail-open")}공개됨</span>`
          : `<span class="badge sealed">${icon("lock")}봉인 중</span>`}
      </div>
      <p class="seal-meta">${k ? `${k.date} ${k.time} 킥오프` : ""}</p>

      ${out ? `<p class="final">경기 결과 <b>${escapeHtml(s.result.score)}</b> · ${escapeHtml(label(s, out))}</p>` : ""}
      <div class="picks">
        ${pickBox(s, "사람", "users", humanPick(s), "집계 전")}
        ${pickBox(s, "AI", "cpu", aiPick(s), "봉인 중")}
      </div>

      <div class="block">
        <p class="block-title">${icon("users")}사람들의 선택</p>
        ${renderVotes(s)}
      </div>

      <div class="block">
        <p class="block-title">${icon("lock")}AI 답 봉인</p>
        <p class="label">봉인값 (영상 화면의 값과 같아야 합니다)</p>
        <p class="hash mono">${escapeHtml(s.hash)}</p>
        ${open
          ? `<p class="label">공개된 원문</p><p class="revealed mono">${escapeHtml(s.revealed_text)}</p>`
          : `<p class="muted small">원문은 결과 편에서 공개합니다.</p>`}
        <div class="actions">
          <button class="btn" type="button" data-copy="${escapeHtml(s.hash)}">${icon("copy")}봉인값 복사</button>
          ${open ? `<button class="btn" type="button" data-fill="${s.ep}">${icon("down")}원문 채우기</button>` : ""}
          ${video ? `<a class="btn" href="${escapeHtml(video)}" target="_blank" rel="noopener">${icon("play")}영상 보기</a>` : ""}
        </div>
      </div>
    </article>`;
}

// ---------- 화면 전환 (#ep1 이면 상세, 아니면 목록) ----------
function route() {
  const m = location.hash.match(/^#ep(\d+)$/);
  const s = m ? seals.find((x) => x.ep === Number(m[1])) : null;
  if (s) {
    renderDetail(s);
    $("result").hidden = true;
    $("text-input").value = "";
    $("hash-input").value = "";
    $("view-list").hidden = true;
    $("view-detail").hidden = false;
    document.title = `EP${s.ep} ${s.match} · Man vs AI`;
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
  const m = normalize(text).match(/^EP(\d+)\|/);
  const ep = m ? Number(m[1]) : null;
  const seal = ep !== null ? seals.find((s) => s.ep === ep) : null;

  if (seal) {
    out.push(hash === seal.hash
      ? verdict("ok", `<b>일치합니다.</b> EP${ep} 봉인값과 같습니다.`)
      : verdict("ng", `<b>일치하지 않습니다.</b> EP${ep} 봉인값과 다릅니다. 원문을 한 글자도 빠짐없이 입력했는지 확인해 주세요.`));
  } else {
    const any = seals.find((s) => s.hash === hash);
    out.push(any
      ? verdict("ok", `<b>일치합니다.</b> EP${any.ep} 봉인값과 같습니다.`)
      : verdict("ng", ep !== null
        ? `EP${ep} 회차를 목록에서 찾지 못했습니다.`
        : `<b>일치하는 회차가 없습니다.</b> 원문은 EP로 시작합니다.`));
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
    const s = seals.find((x) => x.ep === Number(btn.dataset.fill));
    if (!s || !s.revealed_text) return;
    $("text-input").value = s.revealed_text;
    $("verify").scrollIntoView({ behavior: "smooth", block: "start" });
    verify();
  }
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
