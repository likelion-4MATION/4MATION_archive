/* KDIC 챗봇 관리자 콘솔 — 프런트
   서버가 준 스키마(/api/schema)로 폼을 그린다. 라벨·범위·설명이 코드와 한 곳에 있어야
   UI 가 값을 창작하지 않는다(qform_config.SPEC 과 같은 원칙). */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = async (p, o) => {
  const r = await fetch(p, o ? {method: "POST", headers: {"Content-Type": "application/json"},
                                body: JSON.stringify(o)} : undefined);
  if (!r.ok && r.status !== 400 && r.status !== 409) throw new Error(`${p} → ${r.status}`);
  return r.json();
};
const toast = (msg, bad) => {
  const t = $("#toast"); t.textContent = msg; t.className = "toast on" + (bad ? " bad" : "");
  clearTimeout(t._h); t._h = setTimeout(() => t.className = "toast", 3200);
};

let SCHEMA = null, SAVED = {}, DRAFT = {}, DASH = null, GUARDS = [], ADV_UNLOCKED = false;
let PLAN = null;                 // [한 번에 실행] 이 무엇을 돌릴지 — 서버가 계산해 준다
let GOLDEN_DIFF = [];            // 기준 설정과 다른 항목
let ATT = null, ATT_DIRTY_ONLY = false, AX_KIND = 'file', AX_FILE = '';
let REP_KEY = null;              // 교체 대상 첨부의 key
let OOS_SCHEMA = null, REFERRALS = [], PHONE_GUIDE = null, REPORTS = [], SELECTED_REPORT = null;

/* ── 값 포맷 ───────────────────────────────────────────── */
const ENUM_LABEL = {
  preset: {accuracy: "정확도 우선", balanced: "균형", diverse: "다양성 우선"},
  askMode: {template: "정해진 문구", llm: "AI 생성"},
  QFORM_SCOPE: {msdr: "착오송금만", "msdr+dpin": "착오송금 + 예금보험금"},
  CARRYOVER_SCOPE: {bf_match: "기억 지움", global: "그대로 유지", off: "기억 안 함"},
  PANEL_EXPIRED: {gray: "회색으로 남김", drop: "화면에서 지움"},
  BF_MODE: {soft: "가산점(soft)", hard: "타 업무 제외(hard)"},
};
const fmt = (key, v) => {
  const p = SCHEMA.params.find(x => x.key === key);
  if (!p) return String(v);
  if (p.type === "bool") return v ? "켬" : "끔";
  if (p.type === "enum") return (ENUM_LABEL[key] || {})[v] || v;
  if (["CHUNK_SIZE", "OVERLAP", "MIN_CHUNK"].includes(key)) return v + "자";
  return String(v);
};
const val = k => (k in DRAFT ? DRAFT[k] : SAVED[k]);
/* 지표 계열 — 앵커 계열(anchor…)과 청크 계열(hit@…)은 서로 뺄 수 없다.
   재빌드 실측도 이제 앵커 판정이라 두 계열이 같아졌지만, 옛 기록에는 청크 계열이
   남아 있으므로 판별은 그대로 둔다(metric 문자열이 스스로 계열을 밝힌다). */
const fam = m => !m ? null : (String(m).startsWith("anchor") ? "anchor" : "chunk");
const changedKeys = () => Object.keys(DRAFT).filter(k => String(DRAFT[k]) !== String(SAVED[k]));

/* ── 컨트롤 렌더 ───────────────────────────────────────── */
function control(p) {
  const v = val(p.key);
  const dis = p.tier === "locked" || (p.tier === "advanced" && !ADV_UNLOCKED);
  if (p.type === "bool")
    return `<span class="sw ${v ? "on" : ""}" data-k="${p.key}" ${dis ? 'style="opacity:.4;pointer-events:none"' : ""}></span>`;
  if (p.type === "enum") {
    const L = ENUM_LABEL[p.key] || {};
    if (p.values.length <= 3 && p.key !== "QFORM_SCOPE")
      return `<span class="seg" data-k="${p.key}">${p.values.map(x =>
        `<span class="${x === v ? "on" : ""}" data-v="${x}">${L[x] || x}</span>`).join("")}</span>`;
    return `<select data-k="${p.key}" ${dis ? "disabled" : ""}>${p.values.map(x =>
      `<option value="${x}" ${x === v ? "selected" : ""}>${L[x] || x}</option>`).join("")}</select>`;
  }
  if (p.type === "text") return `<code>${v}</code>`;
  const step = p.step || (p.type === "float" ? 0.01 : 1);
  return `<input type="range" data-k="${p.key}" min="${p.min}" max="${p.max}" step="${step}"
            value="${v}" ${dis ? "disabled" : ""}><span class="val">${v}</span>`;
}

function renderForm(sel, tab) {
  const rows = SCHEMA.params.filter(p => p.tab === tab && p.key !== "preset");
  $(sel).innerHTML = rows.map(p => `
    <div class="row">
      <div class="lab"><b>${p.label}</b>
        <small class="${/끄지 마세요|늘려도|가장 큰/.test(p.help) ? "imp" : ""}">${p.help}</small>
        <small><code>${p.source}</code></small></div>
      <div class="ctl">${control(p)}</div>
    </div>`).join("");
}

function renderPresets() {
  const cur = val("preset");
  const ev = DASH?.evidence?.preset || {};
  $("#presetBox").innerHTML = Object.entries(SCHEMA.presets).map(([k, p]) => `
    <div class="preset ${k === cur ? "on" : ""}" data-preset="${k}">
      <b>${p.label}</b><small>${p.desc}</small>
      <div class="num">정확도 ${ev[k] ? ev[k].toFixed(4) : "—"}</div>
    </div>`).join("");
}

/* ── 변경 사항 패널 ────────────────────────────────────── */
async function paint() {
  const ch = changedKeys();
  const rb = ch.filter(k => SCHEMA.rebuild_keys.includes(k));

  const badge = ch.length ? `${ch.length}건 변경 · 미적용` : "변경 없음";
  const badgeCls = "badge " + (ch.length ? (rb.length ? "warn" : "ok") : "");
  $("#chgBadge").textContent = $("#resBadge").textContent = badge;
  $("#chgBadge").className = $("#resBadge").className = badgeCls;
  $("#chgSub").textContent = ch.length ? "저장하기 전 예상 결과는 위 결과창에 있습니다."
    : "설정을 바꾸면 위 결과창에 예상 지표가 표시됩니다.";
  $("#chgList").innerHTML = ch.map(k => {
    const p = SCHEMA.params.find(x => x.key === k);
    return `<div><b>${p.label}</b> <span style="color:var(--tx3)">(${p.tab}번 탭)</span><br>
      ${fmt(k, SAVED[k])} <span class="arw">→</span> <b>${fmt(k, DRAFT[k])}</b>
      ${SCHEMA.rebuild_keys.includes(k) ? '<span class="rb">재빌드 필요</span>' : ""}</div>`;
  }).join("");

  const r = await api("/api/project", {values: DRAFT});
  PLAN = r.plan;                                 // 슬라이더를 움직일 때마다 경로가 갱신된다
  const pj = r.projection, base = pj.baseline;   // 서버가 '저장된 설정' 기준으로 계산해 준다
  const GRADE = {measured: ["측정", "ok"], computed: ["계산", ""], estimated: ["추정", "warn"],
                 unmeasured: ["미측정", "bad"], mixed: ["복합", "warn"]};
  const acc = pj.accuracy, best = pj.best || {};
  const nv = v => (v === null || v === undefined) ? null : Number(v);
  const FMT = {                     // 지표마다 자릿수와 단위가 다르다 — 표기를 한 곳에 모은다
    acc: v => v.toFixed(4), calls: v => v.toFixed(2),
    latency: v => v.toFixed(1) + "초", cost: v => "₩" + v.toFixed(1),
  };
  /* 변화율은 **직전 대비**다. 좋은 방향(up)을 함께 받아야 색을 칠할 수 있다 —
     정확도는 오를수록, 콜 수·응답시간·비용은 내려갈수록 좋다. */
  const rateCell = (prev, next, up) => {
    if (prev === null || next === null || !prev) return `<span style="color:var(--tx3)">—</span>`;
    const r = (next - prev) / Math.abs(prev) * 100;
    if (Math.abs(r) < 0.005) return `<span style="color:var(--tx3)">0.00%</span>`;
    return `<span class="rate" style="color:${(r > 0) === up ? "var(--ok)" : "var(--bad)"}">${
      r > 0 ? "+" : ""}${r.toFixed(2)}%</span>`;
  };
  /* cmp=false 면 세 열이 서로 다른 잣대라 빼거나 나눌 수 없다 — 변화율도 '최고 경신'도
     내지 않는다. 숫자를 나란히 보여주는 것까지가 정직한 한계다. */
  const mrow = (name, sub, key, prev, next, grade, up, cmp = true) => {
    const [lab, cls] = GRADE[grade] || ["", ""];
    const b = best[key] || {}, bv = nv(b.value), f = FMT[key];
    // '최고 경신'은 실제 값이 있을 때만 — 미측정(?)을 경신이라고 부르지 않는다
    const beat = cmp && bv !== null && next !== null && (up ? next > bv + 1e-9 : next < bv - 1e-9);
    return `<tr>
      <td class="m">${name}${sub ? `<small>${sub}</small>` : ""}</td>
      <td class="n best">${bv === null ? "—" : f(bv)}${
        b.at ? `<br><small style="color:var(--tx3)">${String(b.at).slice(0, 10)}</small>` : ""}</td>
      <td class="n">${prev === null ? "?" : f(prev)}</td>
      <td class="n next">${next === null ? "?" : f(next)}${
        beat ? ' <span class="tag ok">최고 경신</span>' : ""}</td>
      <td class="n">${cmp ? rateCell(prev, next, up)
        : '<span class="tag warn">잣대 다름</span>'}</td>
      <td class="n"><span class="tag ${cls}">${lab}</span></td></tr>`;
  };
  // 지표 이름을 고정하지 않는다 — k 를 바꾸면 hit@3 ↔ hit@5 로 잣대 자체가 달라진다
  const accSame = !(base.acc_metric && acc.metric && base.acc_metric !== acc.metric);
  const accLab = accSame
    ? (acc.metric || base.acc_metric || "anchor hit@5") + " · 높을수록 좋음"
    : `${base.acc_metric} → ${acc.metric} · 잣대가 바뀌어 변화율을 내지 않습니다`;
  $("#projTbl").innerHTML = `
    <tr><th>지표</th><th class="n">최고</th><th class="n">직전</th>
        <th class="n">변경 후</th><th class="n">변화율</th><th class="n">근거</th></tr>
    ${mrow("정확도", accLab, "acc", nv(base.acc), nv(acc.value), acc.grade, true, accSame)}
    ${mrow("LLM 콜 / 질의", "적을수록 좋음", "calls", nv(base.calls), nv(pj.calls.value), pj.calls.grade, false)}
    ${mrow("평균 응답시간", "적을수록 좋음", "latency", nv(base.latency), nv(pj.latency.value), pj.latency.grade, false)}
    ${mrow("비용 / 질의", "적을수록 좋음 · 추정", "cost", nv(base.cost), nv(pj.cost.value), pj.cost.grade, false)}`;
  $("#bestHint").innerHTML =
    `<b>최고</b>는 항목별로 따로 고른 역대 최고값 — 정확도는 실측 ${best.n || 0}건의 최댓값,
     콜·응답시간·비용은 지나온 설정 ${best.n_ops || 0}개에서 계산한 최솟값입니다.
     <b>직전</b>은 지금 저장·적용 중인 값이고 <b>변화율</b>은 직전 대비입니다.`;

  let note = "", cls = "note";
  if (rb.length) {
    cls = "note bad";
    note = `<b>재빌드가 필요한 변경 ${rb.length}건</b>이 있습니다. 저장만 해서는 반영되지 않습니다 —
            왼쪽 <b>[한 번에 실행]</b>을 누르면 검증 → 빌드 → 재검증까지 이어서 처리합니다.
            재빌드 시 검색 프리셋과 되묻기 조합 테이블 근거가 함께 무효화됩니다.`;
  } else if (acc.grade === "mixed") {
    note = "정확도에 영향을 주는 항목을 <b>두 가지 이상</b> 동시에 바꿨습니다. 조합 효과는 곱해지지 않으므로 예측할 수 없습니다 — A/B 평가가 필요합니다.";
  } else if (acc.grade === "unmeasured") {
    note = `이 값은 <b>평가한 적이 없습니다.</b> ${acc.src}. 숫자를 추정하지 않고 비워 둡니다.`;
  } else if (fam(base.acc_metric) !== fam(acc.metric) && acc.value !== null) {
    // 앵커 지표(옛 A/B 표)와 청크 지표(재빌드 실측)는 잣대가 다르다 — 빼면 안 된다
    cls = "note bad";
    note = `'현재'는 <b>${base.acc_metric}</b>, '변경 후'는 <b>${acc.metric}</b>로
            <b>잣대가 서로 다른 수치</b>입니다. 두 값을 빼서 비교하지 마세요 —
            같은 잣대로 보려면 왼쪽 [한 번에 실행]으로 실제로 재야 합니다.`;
  } else if (acc.value !== null && base.acc != null && acc.value < base.acc - 1e-9) {
    cls = "note bad";
    note = `정확도가 <b>${base.acc.toFixed(4)} → ${acc.value.toFixed(4)}</b>로 떨어집니다.`;
  }
  const M = r.measured || {};
  $("#resMeta").innerHTML = M["hit@5"] != null
    ? `직전 실측 ${String(M.at).slice(0, 10)} · ${M.chunks ?? "—"}청크${
        M.n_evaluated ? ` · 앵커 채점 ${M.n_evaluated}문항` : ""}`
    : "재빌드 실측 기록 없음 — 왼쪽 [③ 재검증]으로 지금 인덱스를 잴 수 있습니다.";
  $("#accSrc").innerHTML = acc.src
    ? `정확도 근거: <code>${esc(acc.src)}</code>` : "";
  $("#chgNote").innerHTML = note ? `<div class="${cls}">${note}</div>` : "";
  $("#btnReset").disabled = $("#btnSave").disabled = BUSY || !ch.length;
  $("#btnSave").textContent = rb.length ? "저장 (재빌드 대기)" : "저장";
  RUN_BTNS.forEach(id => { const el = $("#" + id); if (el) el.disabled = BUSY; });
  renderPlan();

  paintTab7(acc, r.measured);
}

/* ── ⑦ 탭 비교 패널 ─────────────────────────────────────
   '현재' 열은 서버가 준 evidence.current 에서 온다 — 예전처럼 "800|100|1" 을
   상수로 박아 두면 재빌드로 코퍼스가 바뀌어도 화면이 옛 조합을 현재라고 우긴다. */
function paintTab7(acc, measured) {
  const ev = DASH?.evidence?.chunk || {};
  const cur = DASH?.evidence?.current || {};
  const key = `${+val("CHUNK_SIZE")}|${+val("OVERLAP")}|${val("TABLE_KEEP") ? 1 : 0}`;
  const same = key === cur.key;
  const tgt = same ? cur : (ev[key] || null);          // 변경 후 지점 (없으면 미측정)
  const ch = changedKeys();
  const touched = ["CHUNK_SIZE", "OVERLAP", "MIN_CHUNK", "TABLE_KEEP", "TABLE_GAP_MAX"]
    .some(k => ch.includes(k));

  const num = v => (v === null || v === undefined) ? null : Number(v);
  const cell = v => v === null ? '<span style="color:var(--warn)">미측정</span>'
    : (Number.isInteger(v) ? v : v.toFixed(4));
  const diff = (a, b) => {
    if (a === null || b === null) return "—";
    const x = b - a;
    if (Math.abs(x) < 1e-9) return "—";
    const c = x > 0 ? "var(--ok)" : "var(--bad)";
    const s = Number.isInteger(a) && Number.isInteger(b) ? x : x.toFixed(4);
    return `<span style="color:${c}">${x > 0 ? "+" : ""}${s}</span>`;
  };
  const row = (label, a, b) => `<tr><td>${label}</td><td class="n">${cell(a)}</td>
    <td class="n">${cell(b)}</td><td class="n">${diff(a, b)}</td></tr>`;
  const g = k => tgt ? num(tgt[k]) : null;

  $("#evTag").textContent = same ? "현재 설정" : tgt ? "측정된 조합" : "미측정 조합";
  $("#evTag").className = "badge " + (same ? "" : tgt ? "ok" : "warn");

  $("#cmpTbl").innerHTML =
    `<tr><th>항목</th><th class="n">현재</th><th class="n">변경 후</th><th class="n">차이</th></tr>
     ${row("조각 수", num(cur.chunks), g("chunks"))}
     ${row("앵커 정확도(전체)", num(cur.all), g("all"))}
     ${row("단일 조건 질문", num(cur.single), g("single"))}
     ${row("복합 조건 질문", num(cur.and), g("and"))}
     ${cur.chunk_hit5 != null ? `<tr><td>청크 hit@5 <span class="hint">(참고 · 판정 미사용)</span></td>
        <td class="n">${Number(cur.chunk_hit5).toFixed(4)}</td>
        <td class="n">—</td><td class="n">—</td></tr>` : ""}`;

  const a = num(cur.all), b = g("all");
  if (!touched) {
    $("#evNote").innerHTML = cur.grade === "unmeasured"
      ? `<div class="note">지금 조합은 <b>측정 기록이 없습니다.</b> 왼쪽 [③ 재검증]을 누르면 현재 인덱스를 그대로 재 실측치를 채웁니다.</div>`
      : "";
  } else if (!tgt) {
    $("#evNote").innerHTML = `<div class="note">이 조합은 <b>아직 평가한 적이 없습니다.</b>
      왼쪽 [① 테스트셋 검증]으로 실제 수치를 확인한 뒤 적용하세요. 검색만 다시 돌리므로 LLM 비용은 들지 않습니다.</div>`;
  } else if (a !== null && b !== null && b < a - 1e-9) {
    $("#evNote").innerHTML = `<div class="note bad">이 조합은 <b>현재보다 나쁩니다.</b>
      앵커 정확도 ${a.toFixed(4)} → ${b.toFixed(4)}` +
      (num(cur.and) !== null && g("and") !== null && g("and") < num(cur.and)
        ? `, 복합 조건 질문은 ${cur.and} → <b>${tgt.and}</b>로 떨어집니다.` : ".") + `</div>`;
  } else if (a !== null && b !== null) {
    $("#evNote").innerHTML = `<div class="note ok">이 조합은 현재보다 나은 결과를 보였습니다.</div>`;
  } else {
    $("#evNote").innerHTML = `<div class="note">두 지점의 측정 지표가 서로 달라 <b>차이를 계산하지 않습니다.</b>
      직접 비교하려면 왼쪽 [① 테스트셋 검증]을 실행하세요.</div>`;
  }

  $("#evSrc").innerHTML =
    `현재 근거: <code>${esc(cur.src || "—")}</code>` +
    (tgt && !same ? `<br>변경 후 근거: <code>${esc(tgt.src || "—")}</code>` : "") +
    (cur.grade === "measured" && cur.single === null
      ? `<br><small>재빌드 실측은 전체 앵커 정확도만 냅니다 — 단일/복합 분해는 A/B 표에만 있습니다.</small>` : "");

  $("#crawlHint").innerHTML =
    '이 탭의 값을 바꾸면 <b>다시 잘라야</b> 합니다 — 왼쪽 [한 번에 실행]이 알아서 재청킹까지 합니다.<br>' +
    '홈페이지에서 원문을 새로 받아오는 것은 <b>별개</b>입니다. 왼쪽 <b>[원문 재수집]</b> 버튼만 접속합니다.';
}

/* ── 실행 잡 — 좌측 사이드 패널(버튼) + 상단 결과창(진행 상황) ──────
   버튼은 왼쪽 사이드에, 진행 상황과 결과는 상단 고정 결과창에 둔다. 어느 탭에서 무엇을
   바꾸든 누르는 자리와 읽는 자리가 각각 하나로 고정된다. */
let jobTimer = null, WATCHED = null, BUSY = false, JOB_SHOWN = null;

/* ── 상단 결과창 접기 ───────────────────────────────────
   접으면 **정확도 한 줄**만 남는다. 나머지 지표·근거·실행 진행 상황은 숨긴다.
   선택은 브라우저에 기억시켜 새로고침해도 유지한다(읽기 실패해도 펼친 상태로 뜬다). */
const RB_KEY = "kdic.admin.resultbar.compact";
function setResultCompact(on, remember = true) {
  $("#resultBar").classList.toggle("compact", on);
  $("#rbToggle").textContent = on ? "펼치기" : "접기";
  $("#rbToggle").title = on ? "지표 전체와 실행 진행 상황을 다시 봅니다" : "정확도 한 줄만 남깁니다";
  if (remember) { try { localStorage.setItem(RB_KEY, on ? "1" : "0"); } catch (e) { /* 무시 */ } }
}
const KIND_LABEL = {eval: "테스트셋 검증", rebuild: "재청킹·재빌드",
                    verify: "현재 인덱스 재검증", chain: "한 번에 실행",
                    recrawl: "원문 재수집 + 재빌드", files: "첨부 파일 다시 받기"};
const RUN_STATE = {running: ["실행 중", ""], awaiting: ["확인 대기", "warn"],
                   done: ["완료", "ok"], failed: ["실패", "bad"], aborted: ["중단됨", "warn"]};
const hit5 = m => (m && m["hit@5"] != null) ? Number(m["hit@5"]).toFixed(4) : "—";

function stageBlock(s) {
  const done = s.steps.filter(x => x.status === "done").length;
  const pct = Math.round(done / (s.steps.length || 1) * 100);
  const right = s.metrics && s.metrics["hit@5"] != null ? "앵커 hit@5 " + hit5(s.metrics)
    : s.status === "running" ? pct + "%" : s.status === "skipped" ? "건너뜀" : "";
  return `<div class="stage ${s.status}">
    <div class="stagehead">
      <span>${s.status === "running" ? '<span class="spin"></span>' : ""}${esc(s.label)}</span>
      <span class="n">${right}${s.seconds ? " · " + s.seconds + "s" : ""}</span></div>
    ${s.status === "running" ? `<div class="bar"><i style="width:${pct}%"></i></div>
      <div class="steps">${s.steps.map(x =>
        `<span class="${x.status}">${esc(x.name)}</span>`).join("")}</div>` : ""}
    ${s.status === "done" && s.metrics && !s.metrics.error
      ? `<div style="font-size:11px;color:var(--tx3);margin-top:5px">앵커 hit@1 ${s.metrics["hit@1"]}
         · hit@3 ${s.metrics["hit@3"]} · MRR ${s.metrics["mrr@10"]} · ${s.chunks ?? "—"}청크${s.metrics["n_evaluated"] ? ` · 채점 ${s.metrics["n_evaluated"]}문항` : ""}</div>` : ""}
    ${s.error ? `<div class="note bad" style="margin-top:8px">${esc(s.error)}</div>` : ""}
  </div>`;
}

function gateBlock(j) {
  return `<div class="gate">
    <b>계속 진행할까요?</b>
    <div style="font-size:12px;color:var(--tx2);margin-top:4px">${esc(j.gate.text)}</div>
    <div style="font-size:11px;color:var(--tx3);margin-top:6px">
      계속하면 서비스 인덱스를 이 설정으로 교체합니다. 중단하면 <b>지금 인덱스가 그대로</b> 유지됩니다.
      30분 안에 고르지 않으면 자동 중단됩니다.</div>
    <div style="margin-top:10px;display:flex;gap:8px">
      <button class="btn sm" data-go="${j.id}">계속 진행</button>
      <button class="btn sm ghost" data-stop="${j.id}">중단</button></div></div>`;
}

function cmpBlock(j) {
  const b = j.baseline && j.baseline["hit@5"] != null ? j.baseline : null;
  const rows = (j.stages || []).filter(s => s.metrics && !s.metrics.error);
  if (rows.length < 2) return "";
  const d = x => {
    if (!b) return "—";
    const v = x - Number(b["hit@5"]);
    const c = v > 1e-9 ? "var(--ok)" : v < -1e-9 ? "var(--bad)" : "var(--tx3)";
    return `<span style="color:${c}">${v > 0 ? "+" : ""}${v.toFixed(4)}</span>`;
  };
  return `<table style="margin-top:10px">
    <tr><th>단계</th><th class="n">앵커 hit@5</th><th class="n">청크</th><th class="n">실행 전 대비</th></tr>
    ${b ? `<tr><td style="color:var(--tx3)">실행 전</td>
        <td class="n">${Number(b["hit@5"]).toFixed(4)}</td>
        <td class="n">${b.chunks ?? "—"}</td><td class="n">—</td></tr>` : ""}
    ${rows.map(s => `<tr><td>${esc(s.label)}</td><td class="n"><b>${hit5(s.metrics)}</b></td>
      <td class="n">${s.chunks ?? "—"}</td>
      <td class="n">${d(Number(s.metrics["hit@5"]))}</td></tr>`).join("")}</table>
    <div class="hint">①은 샌드박스 측정(서비스 무손상), ③은 <b>실제 서비스 인덱스</b> 측정입니다.
      ②와 ③의 수치가 다르면 인덱스가 제대로 반영되지 않은 것입니다.</div>`;
}

const RUN_BTNS = ["btnEval", "btnApply", "btnVerify", "btnChain", "btnCrawl", "btnFetchFiles"];

function renderPlan() {
  const p = PLAN;
  if (!p) { $("#planNote").innerHTML = ""; return; }
  const mm = Math.max(1, Math.round(p.eta_seconds / 60));
  $("#planNote").className = "note" + (p.skipped ? " ok" : "");
  const why = (p.changed || []).map(k =>
    (SCHEMA.params.find(x => x.key === k) || {}).label || k).join(" · ");
  $("#planNote").innerHTML = p.skipped
    ? `[한 번에 실행] → <b>재검증만</b> (약 ${p.eta_seconds}초).
       청크 설정이 지금 코퍼스와 같아 <b>다시 자르지 않습니다.</b>
       검색 파라미터 변경은 재검증만으로 수치에 잡힙니다.`
    : `[한 번에 실행] → <b>${p.stages.length}단계</b> (약 ${mm}분).`
      + (why ? `<br>다시 잘라야 하는 항목: <b>${why}</b>` : "")
      + (p.dirty ? `<br><b style="color:var(--warn)">${esc(p.dirty)}</b>` : "");
}

function setRunUI(j) {
  BUSY = !!(j && (j.status === "running" || j.status === "awaiting"));
  const ch = changedKeys().length;
  RUN_BTNS.forEach(id => { const el = $("#" + id); if (el) el.disabled = BUSY; });
  $("#btnSave").disabled = $("#btnReset").disabled = BUSY || !ch;
  $("#btnGolden").disabled = BUSY || !GOLDEN_DIFF.length;
  const [lab, cls] = j ? (RUN_STATE[j.status] || ["", ""]) : ["대기", ""];
  $("#runBadge").textContent = lab;
  $("#runBadge").className = "badge " + cls;
  $("#runSub").textContent = BUSY
    ? (j.status === "awaiting" ? "판정 대기 중입니다 — 아래에서 고르세요."
       : "실행 중입니다. 챗봇은 기존 인덱스로 계속 정상 동작합니다.")
    : ch ? `저장하지 않은 변경 ${ch}건은 실행 직전에 자동 저장됩니다.`
         : "저장된 설정으로 실행합니다.";
  $("#runHint").innerHTML =
    '[원문 재수집] 만 KDIC 홈페이지에 접속합니다. 나머지는 저장된 원문(<code>data/raw</code>)만 씁니다.';
  renderPlan();
}

/* 끝난 잡은 한 줄로 접는다 — 결과창은 상단 고정이라 여기서 자리를 다 먹으면
   아래 설정 화면이 그만큼 밀린다. 돌고 있는 잡은 접지 않는다. */
function jobSummary(j) {
  const last = [...(j.stages || [])].reverse()
    .find(s => s.metrics && !s.metrics.error && s.metrics["hit@5"] != null);
  const [lab] = RUN_STATE[j.status] || ["", ""];
  return `${lab}${last ? ` · 앵커 hit@5 ${hit5(last.metrics)}${
    last.chunks ? ` · ${last.chunks}청크` : ""}` : ""}`;
}

function renderJob(j, pre) {
  const box = $("#jobBox");
  if (pre?.length && $("#preflight")) $("#preflight").innerHTML =
    `<div class="note">${pre.map(w => "· " + esc(w)).join("<br>")}</div>`;
  if (!j) { box.innerHTML = ""; setRunUI(null); return; }
  // 새 잡이 돌기 시작하면 접혀 있어도 펼친다 — 진행 상황을 접힌 채로 숨기지 않는다.
  // 저장된 선택은 건드리지 않아 잡이 끝난 뒤 새로고침하면 원래 상태로 돌아온다.
  if ((j.status === "running" || j.status === "awaiting") && JOB_SHOWN !== j.id) {
    JOB_SHOWN = j.id;
    setResultCompact(false, false);
  }
  const head = `${esc(KIND_LABEL[j.kind] || j.kind)} · ${
    String(j.started_at || "").slice(11, 16)} 시작`;
  const detail = `
    ${(j.stages || []).map(stageBlock).join("")}
    ${j.status === "awaiting" && j.gate ? gateBlock(j) : ""}
    ${j.status === "failed" ? `<div class="note bad">${esc(j.error || "")}${
        j.restored ? "<br><b>이전 상태로 자동 복원됐습니다.</b> 서비스는 정상입니다."
        : j.note ? "<br>" + esc(j.note) : ""}</div>` : ""}
    ${j.status === "aborted" ? `<div class="note">${esc(j.note || j.error || "중단됐습니다.")}</div>` : ""}
    ${j.status === "done" && j.result?.files ? `<div class="note ok">
      첨부 <b>${j.result.files.ok}건</b> 확보${j.result.files.failed
        ? ` · <b style="color:var(--bad)">실패 ${j.result.files.failed}건</b>` : ""}
      · ${Math.round((j.result.files.bytes || 0) / 1024)}KB<br>
      <b>청크에 반영하려면 [한 번에 실행]</b>으로 다시 잘라야 합니다.</div>` : ""}
    ${j.status === "done" ? cmpBlock(j) : ""}`;
  const folded = j.status === "done" || j.status === "aborted";
  box.innerHTML = folded
    ? `<details class="jobwrap"><summary>${head} · ${jobSummary(j)}</summary>${detail}</details>`
    : `<div class="jobwrap"><div class="jobhead-line">${head}</div>${detail}</div>`;
  setRunUI(j);
}

async function pollJob() {
  const r = await api("/api/job");
  const j = r.running || r.latest;
  renderJob(j, r.preflight);
  clearTimeout(jobTimer);
  if (j && (j.status === "running" || j.status === "awaiting")) {
    WATCHED = j.id;
    jobTimer = setTimeout(pollJob, 1500);
  } else if (j && WATCHED === j.id) {
    WATCHED = null;                            // 관측하던 잡이 끝났다 — 한 번만 새로고침
    if (j.status === "done" &&
        (j.stages || []).some(s => s.kind === "rebuild" || s.kind === "files")) await reload();
  }
}

/* ── 가드 ──────────────────────────────────────────────── */
function renderGuards() {
  const s = DASH?.guards || {};
  $("#guardTbl").innerHTML = `<tr><th>제목</th><th>유형</th><th>정정</th><th class="n">발동</th><th>상태</th><th></th></tr>` +
    GUARDS.map(g => `<tr>
      <td><b>${g.title}</b><br><small style="color:var(--tx3)">${g.statement}</small></td>
      <td>${({override: "정정", append: "보충", block: "금지"})[g.kind]}</td>
      <td class="n">${g.old_value ? `${g.old_value} → ${g.new_value}` : "—"}</td>
      <td class="n">${g.fired || 0}회</td>
      <td><span class="dot ${g.active ? "ok" : g.expired ? "bad" : "warn"}"></span>${
        g.expired ? "만료" : g.status === "approved" ? "승인됨" : "초안"}${
        g.days_left !== null && g.days_left !== undefined && g.days_left >= 0 && g.days_left <= 7
          ? `<br><small style="color:var(--warn)">${g.days_left}일 후 만료</small>` : ""}</td>
      <td><button class="btn sm ghost" data-ge="${g.id}">수정</button>
          <button class="btn sm ${g.status === "approved" ? "ghost" : ""}" data-gs="${g.id}"
            data-to="${g.status === "approved" ? "draft" : "approved"}">${
            g.status === "approved" ? "초안으로" : "승인"}</button>
          <button class="btn sm danger" data-gd="${g.id}">삭제</button></td></tr>`).join("");
  const never = GUARDS.filter(g => g.active && !g.fired).length;
  $("#guardHint").innerHTML = `활성 ${s.active || 0}건 · 초안 ${s.draft || 0}건 · 안내문 합계 ${
    s.total_chars || 0}/${s.max_chars}자` + (never ?
    ` — <b style="color:var(--warn)">발동 0회 ${never}건</b>은 발동 조건 키워드가 잘못 설정됐을 가능성이 높습니다.` : "");
  $("#guardStat").innerHTML = `
    <div class="row"><div class="lab"><b>활성 가드</b><small>만료 임박 ${s.expiring || 0}건</small></div>
      <div class="ctl"><span class="val">${s.active || 0}건</span></div></div>
    <div class="row"><div class="lab"><b>초안 대기</b><small>승인 전 — 서비스 미반영</small></div>
      <div class="ctl"><span class="val">${s.draft || 0}건</span></div></div>
    <div class="row"><div class="lab"><b>안내문 합계</b><small>상한 ${s.max_chars}자</small></div>
      <div class="ctl"><span class="val">${s.total_chars || 0}자</span></div></div>
    <div class="bar"><i style="width:${Math.min(100, (s.total_chars || 0) / s.max_chars * 100)}%"></i></div>`;
}

function guardForm(g) {
  $("#gId").value = g?.id || "";
  $("#gTitle").value = g?.title || "";
  $("#gTriggers").value = (g?.triggers || []).join(", ");
  $("#gOld").value = g?.old_value || ""; $("#gNew").value = g?.new_value || "";
  $("#gStmt").value = g?.statement || ""; $("#gSrc").value = g?.source || "";
  $("#gStart").value = g?.start || ""; $("#gEnd").value = g?.end || "";
  $("#gFormTitle").textContent = g ? "가드 수정" : "가드 추가";
  $("#gLen").textContent = ($("#gStmt").value || "").length;
  const kind = g?.kind || "override";
  $("#gKind").innerHTML = SCHEMA.guard_kinds.map(k =>
    `<span class="${k.key === kind ? "on" : ""}" data-v="${k.key}">${k.label}</span>`).join("");
  const biz = g?.business || [];
  $("#gBiz").innerHTML = SCHEMA.business.map(b =>
    `<span class="chip ${biz.includes(b) ? "on" : ""}" data-b="${b}">${b}</span>`).join("");
  $("#gErr").innerHTML = ""; $("#gPrev").innerHTML = "";
  $("#gValRow").style.display = kind === "override" ? "" : "none";
}
const collectGuard = () => ({
  id: $("#gId").value || undefined,
  title: $("#gTitle").value.trim(),
  kind: $("#gKind .on")?.dataset.v || "override",
  triggers: $("#gTriggers").value.split(",").map(s => s.trim()).filter(Boolean),
  business: $$("#gBiz .chip.on").map(e => e.dataset.b),
  old_value: $("#gOld").value.trim(), new_value: $("#gNew").value.trim(),
  statement: $("#gStmt").value.trim(), source: $("#gSrc").value.trim(),
  start: $("#gStart").value, end: $("#gEnd").value, priority: 50,
});

/* ── 대시보드 ──────────────────────────────────────────── */
function renderDash() {
  const c = DASH.corpus, f = DASH.freshness, h = DASH.health, a = DASH.attachments;
  $("#bCorpus").textContent = c.available ? `코퍼스 ${c.chunks}청크 / ${c.docs}문서` : "코퍼스 없음";
  $("#bRepo").textContent = h.repo;
  $("#bInsured").style.display = f.insured_list_indexed ? "none" : "";
  $("#corpusKpi").innerHTML = c.available ? `
    <div class="k"><div class="t">조각 수</div><div class="v">${c.chunks}</div><div class="d">문서 ${c.docs}개</div></div>
    <div class="k"><div class="t">평균 길이</div><div class="v">${c.avg}<span style="font-size:12px">자</span></div><div class="d">중앙값 ${c.median}자</div></div>
    <div class="k"><div class="t">최대 길이</div><div class="v">${c.max.toLocaleString()}<span style="font-size:12px">자</span></div><div class="d">표 유지 규칙 적용분</div></div>
    <div class="k"><div class="t">최소 길이</div><div class="v">${c.min}<span style="font-size:12px">자</span></div><div class="d">상한 초과 ${c.over_limit}개</div></div>`
    : `<div class="k"><div class="t">코퍼스</div><div class="v">—</div><div class="d">chunks.jsonl 없음</div></div>`;

  $("#fresh").innerHTML = `
    <div class="row"><div class="lab"><b>마지막 크롤링</b></div><div class="ctl"><span class="badge ${f.last_crawl ? "ok" : "warn"}">${(f.last_crawl || "미확인").slice(0, 10)}</span></div></div>
    <div class="row"><div class="lab"><b>부보금융회사 명단</b><small>분기 갱신 · ${f.insured_list_indexed ? "색인됨" : "본문 미색인"}</small></div><div class="ctl"><span class="badge warn">${f.insured_list_quarter}</span></div></div>
    <div class="row"><div class="lab"><b>공시이율 기준</b></div><div class="ctl"><span class="badge">${f.rate_month}</span></div></div>
    <div class="row"><div class="lab"><b>코퍼스 버전</b><small>조각 ${val("CHUNK_SIZE")}자 · 겹침 ${val("OVERLAP")}자 · 표 ${val("TABLE_KEEP") ? "유지" : "분할"}</small></div><div class="ctl"><span class="badge ok">${f.corpus}</span></div></div>`;

  $("#health").innerHTML = `
    <div class="row"><div class="lab"><b>검색 인덱스</b><small>${(h.index_mtime || "").slice(0, 16) || "—"}</small></div><div class="ctl"><span class="dot ${h.index_ok ? "ok" : "bad"}"></span>${h.index_ok ? "정상" : "없음"}</div></div>
    <div class="row"><div class="lab"><b>업무 분류 모델</b><small>실패 시 키워드 방식으로 자동 전환</small></div><div class="ctl"><span class="dot ${h.router_ok ? "ok" : "warn"}"></span>${h.router_ok ? "정상" : "폴백"}</div></div>`;

  const tot = DASH.business.reduce((s, b) => s + b.n, 0);
  $("#bizTbl").innerHTML = DASH.business.map(b =>
    `<tr><td>${b.name}</td><td class="n">${b.pct}%</td></tr>`).join("");
  $("#bizHint").innerHTML = `평가셋 ${tot}문항 기준. 되묻기 적용 업무: <b>${fmt("QFORM_SCOPE", val("QFORM_SCOPE"))}</b>`;


  const ev = DASH.evidence.chunk;
  $("#evOv").innerHTML = `<tr><th>겹침</th><th class="n">조각</th><th class="n">정확도</th><th>판정</th></tr>` +
    [["100자", "800|100|0", "최고"], ["200자", "800|200|0", "−0.5%p"], ["300자", "800|300|0", "−1.4%p"]]
      .map(([l, k, j]) => `<tr><td>${l}</td><td class="n">${ev[k].chunks}</td>
        <td class="n" style="color:${k === "800|100|0" ? "var(--ok)" : k === "800|300|0" ? "var(--bad)" : ""}">${ev[k].single}</td><td>${j}</td></tr>`).join("");
  $("#evTbl").innerHTML = `<tr><th>설정</th><th class="n">조각</th><th class="n">단일</th><th class="n">복합</th></tr>
    <tr><td>표 쪼갬</td><td class="n">${ev["800|100|0"].chunks}</td><td class="n">${ev["800|100|0"].single}</td><td class="n" style="color:var(--bad)">${ev["800|100|0"].and}</td></tr>
    <tr><td><b>표 유지 (권장)</b></td><td class="n">${ev["800|100|1"].chunks}</td><td class="n" style="color:var(--ok)">${ev["800|100|1"].single}</td><td class="n" style="color:var(--ok)"><b>${ev["800|100|1"].and}</b></td></tr>`;

  const cp = DASH.evidence.current || {};
  $("#evLive").innerHTML = `지금 서비스 중인 조합은 <b>${esc(cp.key || "—")}</b>
    (조각 ${cp.chunks ?? "—"}개) — ` + (cp.grade === "measured"
      ? `근거 <code>${esc(cp.src || "")}</code>`
      : `<b style="color:var(--warn)">측정 기록 없음</b>. 위 두 표는 겹침 100·표 처리 A/B 당시(215/181조각)의 기록이라 지금 조합과 다릅니다.`);

  // 조기차단은 확정 정책이라 토글이 없다 — 여기서 "끄면"이라고 쓰면 없는 스위치를 안내하게 된다
  $("#latNote").innerHTML = `경로별 실측 — 소관 밖 <b>약 1.3초</b>(1콜) / 일반 답변 <b>약 5.0초</b>(2콜).
    소관 밖 조기차단은 <b>확정 정책이라 끄고 켜지 않습니다</b>. 질의의 약 28%가 이 경로로 빠져
    평균이 4초대로 내려옵니다.<br>
    이 숫자를 실제로 움직이는 것은 <b>답변 길이 상한</b>(①탭)과 <b>되묻기 문구 생성 방식</b>(아래),
    <b>되묻기 횟수·적용 업무</b>(③탭)입니다.`;
}

function renderHistory(hist) {
  $("#histTbl").innerHTML = hist.length ? hist.slice(0, 8).map((h, i) => `<tr>
    <td><small style="color:var(--tx3)">${h.at.slice(5, 16).replace("T", " ")}</small><br>
      ${h.changes.map(c => {const p = SCHEMA.params.find(x => x.key === c.key);
        return `${p ? p.label : c.key} → <b>${p ? fmt(c.key, c.to) : c.to}</b>`;}).join("<br>")}
      ${h.note ? `<br><small style="color:var(--tx3)">${h.note}</small>` : ""}</td>
    <td class="n"><button class="btn sm ghost" data-rb="${i}">되돌리기</button></td></tr>`).join("")
    : `<tr><td><small style="color:var(--tx3)">변경 이력이 없습니다.</small></td></tr>`;
}

/* ── 기준 설정 되돌리기 (초기화) ─────────────────────────
   "지금까지 나온 가장 좋은 조합"으로 되돌린다. 곧바로 실행하지 않고 **초안으로만** 채워
   변경 목록에 보여 준다 — 무엇이 바뀌는지 보고 나서 저장·실행하게. */
function renderGolden(diff) {
  GOLDEN_DIFF = diff || [];
  const g = SCHEMA?.golden;
  const n = GOLDEN_DIFF.length;
  $("#btnGolden").disabled = BUSY || !n;
  $("#btnGolden").textContent = n
    ? `기준 설정으로 되돌리기 (${n}개 항목)` : "기준 설정과 동일합니다";
  $("#goldenHint").innerHTML = n
    ? `${GOLDEN_DIFF.map(d => `<b>${esc(d.label)}</b> ${esc(String(d.from))}→${esc(String(d.to))}`).join(" · ")}
       <br>${esc(g?.src || "")}`
    : `현재 설정이 기준 설정(${esc(g?.label || "")})과 같습니다.`;
}

/* ── 로드 / 저장 ───────────────────────────────────────── */
async function reload() {
  const [st, dash, gs] = await Promise.all([
    api("/api/state"), api("/api/dashboard"), api("/api/guards")]);
  SAVED = st.values; DRAFT = {}; DASH = dash; GUARDS = gs.guards;
  renderGolden(st.golden_diff);
  DASH.guards = gs.stats;
  $("#bPreset").textContent = st.custom_search ? "검증된 프리셋 아님" : "검증된 프리셋 사용 중";
  $("#bPreset").className = "badge " + (st.custom_search ? "bad" : "ok");
  $("#bGuard").textContent = `최신성 가드 ${gs.stats.active}건 적용 중`;
  $("#bGuard").className = "badge " + (gs.stats.active ? "ok" : "");
  if (Object.keys(st.pending).length)
    toast(`재빌드 대기 중인 변경 ${Object.keys(st.pending).length}건이 있습니다.`);
  renderPresets(); [1, 2, 3, 4, 6, 7].forEach(t => {
    const el = $("#f" + t); if (el) renderForm("#f" + t, t);});
  renderDash(); renderGuards(); renderHistory(st.history);
  await loadAtt();
  guardForm(null);
  await paint(); await pollJob();
}

/* ── 이벤트 ────────────────────────────────────────────── */
document.addEventListener("click", async e => {
  const t = e.target;
  if (t.closest("#rbToggle")) {
    setResultCompact(!$("#resultBar").classList.contains("compact")); return;
  }
  const tab = t.closest(".tab");
  if (tab) {$$(".tab").forEach(x => x.classList.remove("on")); $$(".pane").forEach(x => x.classList.remove("on"));
    tab.classList.add("on"); $("#" + tab.dataset.p).classList.add("on"); return;}

  const pre = t.closest("[data-preset]");
  if (pre) {DRAFT.preset = pre.dataset.preset; renderPresets(); paint(); return;}

  const sw = t.closest(".sw[data-k]");
  if (sw) {sw.classList.toggle("on"); DRAFT[sw.dataset.k] = sw.classList.contains("on"); paint(); return;}

  const segSpan = t.closest(".seg[data-k] span");
  if (segSpan) {const g = segSpan.closest(".seg");
    $$("span", g).forEach(x => x.classList.remove("on")); segSpan.classList.add("on");
    DRAFT[g.dataset.k] = segSpan.dataset.v; paint(); return;}

  const gk = t.closest("#gKind span");
  if (gk) {$$("#gKind span").forEach(x => x.classList.remove("on")); gk.classList.add("on");
    $("#gValRow").style.display = gk.dataset.v === "override" ? "" : "none"; return;}
  const gb = t.closest("#gBiz .chip");
  if (gb) {gb.classList.toggle("on"); return;}

  if (t.dataset.ge) {guardForm(GUARDS.find(g => g.id === t.dataset.ge));
    $("#gFormTitle").scrollIntoView({behavior: "smooth", block: "center"}); return;}
  if (t.dataset.gs) {const r = await api(`/api/guards/${t.dataset.gs}/status/${t.dataset.to}`);
    if (r.ok) {toast("상태가 바뀌었습니다."); await reload();}
    else toast(r.errors.join(" "), true); return;}
  if (t.dataset.gd) {if (!confirm("이 가드를 삭제할까요?")) return;
    await fetch(`/api/guards/${t.dataset.gd}`, {method: "DELETE"}); toast("삭제됐습니다."); await reload(); return;}
  if (t.dataset.rb !== undefined) {if (!confirm("이 변경을 되돌릴까요?")) return;
    await api(`/api/rollback/${t.dataset.rb}`, {}); toast("되돌렸습니다."); await reload(); return;}

  if (t.dataset.go || t.dataset.stop) {          // 체인 판정 게이트
    const id = t.dataset.go || t.dataset.stop, go = !!t.dataset.go;
    if (!go && !confirm("여기서 중단하면 서비스 인덱스는 지금 상태 그대로 유지됩니다.\n\n중단할까요?")) return;
    const r = await api(`/api/job/${id}/resume`, {go});
    if (!r.ok) toast(r.error, true);
    else toast(go ? "재빌드를 계속 진행합니다." : "중단했습니다. 인덱스는 그대로입니다.");
    pollJob(); return;
  }

  if (t.id === "advToggle") {ADV_UNLOCKED = !ADV_UNLOCKED;
    if (ADV_UNLOCKED && !confirm("검색 5축을 직접 바꾸면 검증되지 않은 조합이 됩니다.\n계속할까요?"))
      {ADV_UNLOCKED = false; return;}
    $("#advLock").textContent = ADV_UNLOCKED ? "해제됨" : "잠김";
    $("#advToggle").textContent = ADV_UNLOCKED ? "다시 잠금" : "잠금 해제";
    renderForm("#f6", 6); return;}
});

document.addEventListener("input", e => {
  const el = e.target;
  if (el.matches('input[type=range][data-k]')) {
    const p = SCHEMA.params.find(x => x.key === el.dataset.k);
    DRAFT[el.dataset.k] = p.type === "float" ? parseFloat(el.value) : parseInt(el.value, 10);
    el.nextElementSibling.textContent = el.value; paint();
  }
  if (el.id === "gStmt") $("#gLen").textContent = el.value.length;
});
document.addEventListener("change", e => {
  const el = e.target;
  if (el.matches("select[data-k]")) {DRAFT[el.dataset.k] = el.value; paint();}
});

$("#btnGolden").onclick = async () => {
  const g = SCHEMA.golden;
  if (!GOLDEN_DIFF.length) { toast("이미 기준 설정입니다."); return; }
  const rb = GOLDEN_DIFF.filter(d => d.rebuild);
  if (!confirm(
    `기준 설정으로 되돌립니다 — ${g.label}\n\n` +
    GOLDEN_DIFF.map(d => `· ${d.label}: ${d.from} → ${d.to}`).join("\n") + "\n\n" +
    (rb.length ? `이 중 ${rb.length}개는 재빌드가 필요합니다.\n` : "") +
    `근거: ${g.src}\n\n` +
    `⚠ ${g.caveat}\n\n` +
    "지금은 초안으로만 채웁니다. 저장하거나 [한 번에 실행]을 눌러야 반영됩니다.\n\n계속할까요?"
  )) return;
  GOLDEN_DIFF.forEach(d => { DRAFT[d.key] = d.to; });
  renderPresets();
  [1, 2, 3, 4, 6, 7].forEach(t => { if ($("#f" + t)) renderForm("#f" + t, t); });
  await paint();
  toast(`${GOLDEN_DIFF.length}개 항목을 기준 설정으로 채웠습니다. 저장하거나 바로 실행하세요.`);
};

$("#btnReset").onclick = () => reload();
$("#btnSave").onclick = async () => {
  const r = await api("/api/save", {changes: DRAFT});
  if (r.invalid?.length) toast(r.invalid.map(i => `${i.key}: ${i.why}`).join(", "), true);
  else if (Object.keys(r.pending || {}).length)
    toast("저장됐습니다. 재빌드가 필요한 항목은 ⑦ 탭에서 A/B 평가 후 적용하세요.");
  else toast("저장됐습니다. 다음 질의부터 반영됩니다.");
  await reload();
};

/* ── 실행 버튼 ─────────────────────────────────────────────
   잡은 **저장된 값**(override + pending)만 읽는다. 화면에서 슬라이더만 움직인 값은
   잡에 전달되지 않으므로, 실행 직전에 초안을 먼저 저장한다. */
async function saveDraftIfAny() {
  const ch = changedKeys();
  if (!ch.length) return true;
  const r = await api("/api/save", {changes: DRAFT});
  if (r.invalid?.length) {
    toast(r.invalid.map(i => `${i.key}: ${i.why}`).join(", "), true);
    return false;
  }
  SAVED = r.state.values; DRAFT = {};
  toast(`변경 ${ch.length}건을 저장하고 실행합니다.`);
  return true;
}

async function startJob(kind, confirmMsg, recrawl) {
  const ch = changedKeys().length;
  const head = ch ? `저장하지 않은 변경 ${ch}건을 먼저 저장한 뒤 실행합니다.\n\n` : "";
  if (confirmMsg && !confirm(head + confirmMsg)) return;
  if (!(await saveDraftIfAny())) return;
  const r = await api("/api/job",
    {kind, guard: $("#chkGuard").checked, recrawl: !!recrawl});
  if (!r.ok) { toast(r.error, true); return; }
  await paint(); pollJob();
}

$("#btnEval").onclick = () => startJob("eval");
$("#btnVerify").onclick = () => startJob("verify");
$("#btnApply").onclick = () => startJob("rebuild",
  "저장된 원문으로 문서를 다시 자르고 전체를 재계산합니다. 예상 2분.\n\n" +
  "진행 중에도 챗봇은 기존 인덱스로 정상 동작합니다.\n\n계속할까요?");

$("#btnChain").onclick = () => {
  const p = PLAN;
  const msg = p?.skipped
    ? "청크 설정이 지금 코퍼스와 같아 다시 자르지 않습니다.\n\n" +
      "현재 서비스 인덱스를 그대로 재검증만 합니다 (약 35초).\n" +
      "저장된 검색 설정으로 측정하므로 프리셋·고급 값 변경 효과가 여기서 잡힙니다.\n\n계속할까요?"
    : "세 단계를 연달아 실행합니다.\n\n" +
      "① 샌드박스에서 테스트셋 검증 (서비스 무손상)\n" +
      "② 저장된 원문으로 재청킹 · 인덱스 교체\n" +
      "③ 교체된 실제 인덱스로 재검증\n\n" +
      `다시 잘라야 하는 항목: ${(p?.changed || []).join(", ") || "—"}\n` +
      `예상 ${Math.max(1, Math.round((p?.eta_seconds || 175) / 60))}분. ` +
      "홈페이지에는 접속하지 않습니다.\n\n" +
      ($("#chkGuard").checked
        ? "①이 현재보다 나쁘면 ② 앞에서 멈추고 확인을 요청합니다.\n\n"
        : "검증 결과와 무관하게 끝까지 진행합니다.\n\n") +
      "계속할까요?";
  startJob("chain", msg);
};

$("#btnCrawl").onclick = () => startJob("recrawl",
  "⚠ KDIC 홈페이지에 실제로 접속해 원문을 다시 받아옵니다.\n\n" +
  "· 폴라이트 수집이라 10분 안팎 걸립니다\n" +
  "· 받아온 원문으로 곧바로 인덱스를 교체하고 재검증합니다\n" +
  "· 원문이 바뀌면 최신성 가드의 '기존 값'과 되묻기 조합 테이블의 근거 연결이\n" +
  "  어긋날 수 있습니다 — 끝난 뒤 ④·③ 탭을 확인하세요\n" +
  "· 이 설정은 저장되지 않습니다. 이번 한 번만 수집합니다\n\n" +
  "계속할까요?", true);

$("#gPreview").onclick = async () => {
  const r = await api("/api/guards/preview", {guard: collectGuard()});
  $("#gErr").innerHTML = r.errors.length
    ? `<div class="note bad">${r.errors.map(x => "· " + x).join("<br>")}</div>` : "";
  $("#gPrev").innerHTML = r.errors.length ? "" : `
    <div class="note ok"><b>프롬프트에 이렇게 들어갑니다</b>
      <pre class="log">${r.prompt_block.replace(/[<>]/g, c => ({"<": "&lt;", ">": "&gt;"}[c]))}</pre>
      <b>검증기 허용 수치</b>: ${r.whitelist.length ? r.whitelist.join(", ") : "없음"}<br>
      <small>이 값들이 자동 등록되지 않으면 가드를 켜는 순간 수치 경고가 전건 발생합니다.</small></div>`;
};
$("#gSave").onclick = async () => {
  const r = await api("/api/guards", {guard: collectGuard()});
  if (!r.ok) {$("#gErr").innerHTML = `<div class="note bad">${r.errors.map(x => "· " + x).join("<br>")}</div>`;
    toast("저장하지 못했습니다.", true); return;}
  toast("초안으로 저장했습니다. 승인해야 서비스에 반영됩니다."); await reload();
};
$("#gClear").onclick = () => guardForm(null);


/* ── ⑤ 첨부문서 · 링크 ─────────────────────────────────── */
const esc = t => String(t ?? "").replace(/[<>&"]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;",'"':"&quot;"}[c]));
const kst = value => {
  if (!value) return "—";
  const d = new Date(value); if (Number.isNaN(d.getTime())) return String(value);
  return new Intl.DateTimeFormat("ko-KR", {timeZone:"Asia/Seoul", dateStyle:"medium", timeStyle:"medium"}).format(d);
};

function renderAtt() {
  if (!ATT) return;
  const st = ATT.stats;
  $("#attSub").innerHTML = `문서 ${st.docs}개 · 항목 ${st.items}건 · 고친 표시명 ${st.edited}건`
    + (st.extra ? ` · 직접 추가 ${st.extra}건` : "")
    + (st.replaced ? ` · <b style="color:var(--ok)">교체 ${st.replaced}건</b>` : "")
    + ` · 내려받아 둔 원본 ${st.files ?? 0}건`;
  $("#attNote").innerHTML = st.dirty
    ? `<div class="note">표 파싱 잔여물이 섞인 표시명 <b>${st.dirty}건</b>이 남아 있습니다. 사용자 화면에 그대로 나가면 깨져 보입니다.</div>`
    : `<div class="note ok">정제가 필요한 표시명이 없습니다.</div>`;
  $("#attToggleDirty").textContent = ATT_DIRTY_ONLY ? "전체 보기" : "정제 필요만 보기";
  const missing = st.items - (st.files ?? 0) - (st.extra ?? 0);
  $("#attFetchNote").innerHTML = !st.files
    ? `<div class="note bad">첨부 실파일을 <b>아직 받지 않았습니다.</b> 크롤링(재수집)은 첨부 파일을
       받아오지 않습니다 — 위 <b>[첨부 파일 다시 받기]</b>를 눌러야 내려받기가 가능해집니다.</div>`
    : missing > 0
      ? `<div class="note">목록 ${st.items}건 중 <b>${missing}건은 실파일이 없습니다.</b>
         [첨부 파일 다시 받기]로 채울 수 있습니다.</div>`
      : `<div class="note ok">첨부 실파일 <b>${st.files}건</b>을 모두 확보했습니다 — 행마다 내려받아 확인할 수 있습니다.</div>`;

  $("#attTbl").innerHTML = ATT.docs.map(d => {
    const items = ATT_DIRTY_ONLY ? d.items.filter(i => i.dirty) : d.items;
    if (!items.length) return "";
    return `<div style="margin-bottom:14px">
      <div style="font-size:12px;color:var(--tx3);margin-bottom:4px"><code>${esc(d.doc_id).replace("kdic-","")}</code> · ${d.count}건</div>
      <table>${items.map(i => `<tr>
        <td style="width:46%">
          <input type="text" class="attLbl" data-key="${i.key}" value="${esc(i.label)}" style="width:100%">
          ${i.dirty ? `<small style="color:var(--warn)">원본: ${esc(i.original).slice(0,60)}…</small>` : ""}
          ${i.edited && i.source === "crawl" && !i.dirty ? `<small style="color:var(--tx3)">원본: ${esc(i.original).slice(0,50)}</small>` : ""}
          ${i.orig_filename ? `<small style="color:var(--tx3)">${esc(i.orig_filename)} · ${
              Math.round((i.size_bytes||0)/1024)}KB · sha ${esc(i.sha256||"")}</small>` : ""}
          ${i.replaced ? `<small style="color:var(--ok)">교체본: ${esc((i.replace_filename||"").split("_").slice(1).join("_"))}
              ${i.replace_note ? " · " + esc(i.replace_note) : ""} · ${String(i.replace_at||"").slice(0,10)}</small>` : ""}
        </td>
        <td class="n" style="white-space:nowrap">${i.file_type || "—"}</td>
        <td class="n">${i.replaced ? '<span class="tag ok">교체됨</span>'
            : i.dirty ? '<span class="tag warn">정제 필요</span>'
            : i.source === "admin" ? '<span class="tag ok">직접 추가</span>'
            : i.edited ? '<span class="tag">수정됨</span>' : ""}
          ${i.source === "crawl" && !i.has_file ? '<span class="tag bad">원본 없음</span>' : ""}</td>
        <td class="n" style="white-space:nowrap">
          ${i.replaced
            ? `<a class="btn sm" href="${esc(i.replace_download)}" download>새 파일</a>
               <button class="btn sm ghost" data-unrep="${i.key}">교체 취소</button>`
            : i.download ? `<a class="btn sm ghost" href="${esc(i.download)}" download>내려받기</a>` : ""}
          ${i.source === "crawl" ? `<button class="btn sm ghost" data-rep="${i.key}">${
              i.replaced ? "다시 교체" : "교체"}</button>` : ""}
          ${i.page_url ? `<a class="btn sm ghost" href="${esc(i.page_url)}" target="_blank">원문</a>` : ""}
          ${i.dirty && i.suggestion ? `<button class="btn sm ghost" data-fix="${i.key}" data-v="${esc(i.suggestion)}">제안 적용</button>` : ""}
          ${i.edited && i.source === "crawl" ? `<button class="btn sm ghost" data-reset="${i.key}">이름 원복</button>` : ""}
          ${i.source === "admin" ? `<button class="btn sm danger" data-axdel="${i.id}">삭제</button>` : ""}
        </td></tr>`).join("")}</table></div>`;
  }).join("") || `<div class="hint">표시할 항목이 없습니다.</div>`;

  $("#axDoc").innerHTML = `<option value="">(관리자 추가)</option>` +
    ATT.docs.filter(d => d.doc_id !== "(관리자 추가)")
      .map(d => `<option value="${esc(d.doc_id)}">${esc(d.doc_id).replace("kdic-","")}</option>`).join("");

  $("#linkTbl").innerHTML = `<tr><th>기관·제도</th><th>연락처</th><th>발동 키워드</th><th></th></tr>` +
    (ATT.links.length ? ATT.links.map(l => `<tr>
      <td><b>${esc(l.title)}</b>${l.org ? `<br><small style="color:var(--tx3)">${esc(l.org)}</small>` : ""}</td>
      <td><small>${l.url ? `<a href="${esc(l.url)}" target="_blank" style="color:var(--ac)">${esc(l.url).replace(/^https?:\/\//,"")}</a><br>` : ""}${esc(l.phone || "")}</small></td>
      <td><small>${(l.keywords || []).map(esc).join(", ")}</small>${
        (l.business||[]).length ? `<br><small style="color:var(--tx3)">${l.business.map(esc).join(" · ")}</small>` : ""}</td>
      <td class="n" style="white-space:nowrap"><button class="btn sm ghost" data-lke="${l.id}">수정</button>
        <button class="btn sm danger" data-lkd="${l.id}">삭제</button></td></tr>`).join("")
      : `<tr><td colspan="4"><small style="color:var(--tx3)">등록된 안내처가 없습니다.</small></td></tr>`);

  $("#lkBiz").innerHTML = SCHEMA.business.map(b =>
    `<span class="chip" data-lb="${b}">${b}</span>`).join("");
}

function linkForm(l) {
  $("#lkId").value = l?.id || ""; $("#lkTitle").value = l?.title || "";
  $("#lkOrg").value = l?.org || ""; $("#lkUrl").value = l?.url || "";
  $("#lkPhone").value = l?.phone || ""; $("#lkKw").value = (l?.keywords || []).join(", ");
  $("#lkNote").value = l?.note || ""; $("#lkErr").innerHTML = "";
  const biz = l?.business || [];
  $$("#lkBiz .chip").forEach(c => c.classList.toggle("on", biz.includes(c.dataset.lb)));
}

async function loadAtt() { ATT = await api("/api/attachments"); renderAtt(); }

document.addEventListener("click", async e => {
  const t = e.target;
  if (t.dataset.fix) {
    await api("/api/attachments/label", {key: t.dataset.fix, label: t.dataset.v});
    toast("표시명을 정리했습니다."); await loadAtt(); return;
  }
  if (t.dataset.reset) {
    await api("/api/attachments/label", {key: t.dataset.reset, label: ""});
    toast("원본으로 되돌렸습니다."); await loadAtt(); return;
  }
  if (t.dataset.rep) {                       // 구 문서 → 새 파일 교체
    REP_KEY = t.dataset.rep;
    $("#repFile").value = "";
    $("#repFile").click(); return;
  }
  if (t.dataset.unrep) {
    if (!confirm("교체를 취소하고 크롤링 원본으로 되돌립니다.\n올렸던 새 파일은 삭제됩니다.\n\n계속할까요?")) return;
    await api("/api/attachments/replace", {key: t.dataset.unrep, filename: ""});
    toast("원본으로 되돌렸습니다."); await loadAtt(); return;
  }
  if (t.dataset.axdel) {
    if (!confirm("이 항목을 삭제할까요? 업로드한 파일도 함께 지워집니다.")) return;
    await fetch(`/api/attachments/extra/${t.dataset.axdel}`, {method: "DELETE"});
    toast("삭제했습니다."); await loadAtt(); return;
  }
  if (t.dataset.lke) { linkForm(ATT.links.find(l => l.id === t.dataset.lke));
    $("#lkTitle").scrollIntoView({behavior: "smooth", block: "center"}); return; }
  if (t.dataset.lkd) {
    if (!confirm("이 안내처를 삭제할까요? 해당 주제 질문은 일반 거절 문구로 내려갑니다.")) return;
    await fetch(`/api/links/${t.dataset.lkd}`, {method: "DELETE"});
    toast("삭제했습니다."); await loadAtt(); return;
  }
  const lb = t.closest("#lkBiz .chip"); if (lb) { lb.classList.toggle("on"); return; }
  const ak = t.closest("#axKind span");
  if (ak) { $$("#axKind span").forEach(x => x.classList.remove("on")); ak.classList.add("on");
    AX_KIND = ak.dataset.v;
    $("#axFileRow").style.display = AX_KIND === "file" ? "" : "none";
    $("#axUrlRow").style.display = AX_KIND === "url" ? "" : "none"; return; }

  if (t.id === "btnFetchFiles") {
    startJob("files",
      "⚠ KDIC 홈페이지에 접속해 첨부 서식 파일을 전부 다시 내려받습니다.\n\n" +
      "· 폴라이트 수집이라 2분 안팎 걸립니다 (건당 1.5~2.2초)\n" +
      "· 받은 파일은 crawler/data/files/ 에 저장되고 목록이 갱신됩니다\n" +
      "· 연결 정보가 data/parsed 에 기록되므로, 챗봇 답변의 첨부에 반영하려면\n" +
      "  끝난 뒤 [한 번에 실행]으로 재청킹해야 합니다 (자동으로 안내합니다)\n" +
      "· 관리자가 교체해 둔 파일은 그대로 유지됩니다\n\n" +
      "계속할까요?");
    return;
  }
  if (t.id === "attToggleDirty") { ATT_DIRTY_ONLY = !ATT_DIRTY_ONLY; renderAtt(); return; }
  if (t.id === "attClean") {
    if (!confirm("정제가 필요한 표시명에 제안값을 일괄 적용합니다.\n항목별로 다시 고칠 수 있습니다.\n\n계속할까요?")) return;
    const r = await api("/api/attachments/clean", {});
    toast(`${r.count}건을 정리했습니다.`); await loadAtt(); return;
  }
  if (t.id === "axSave") {
    const body = {doc_id: $("#axDoc").value, label: $("#axLabel").value,
                  kind: AX_KIND, url: $("#axUrl").value, filename: AX_FILE,
                  note: $("#axNote").value};
    const r = await api("/api/attachments/extra", body);
    if (!r.ok) { $("#axErr").innerHTML = `<div class="note bad">${r.errors.map(x => "· " + x).join("<br>")}</div>`; return; }
    $("#axErr").innerHTML = ""; $("#axLabel").value = ""; $("#axUrl").value = "";
    $("#axNote").value = ""; $("#axFile").value = ""; $("#axUp").innerHTML = ""; AX_FILE = "";
    toast("첨부를 추가했습니다."); await loadAtt(); return;
  }
  if (t.id === "lkSave") {
    const body = {id: $("#lkId").value || undefined, title: $("#lkTitle").value,
      org: $("#lkOrg").value, url: $("#lkUrl").value, phone: $("#lkPhone").value,
      keywords: $("#lkKw").value.split(",").map(x => x.trim()).filter(Boolean),
      business: $$("#lkBiz .chip.on").map(x => x.dataset.lb), note: $("#lkNote").value};
    const r = await api("/api/links", {link: body});
    if (!r.ok) { $("#lkErr").innerHTML = `<div class="note bad">${r.errors.map(x => "· " + x).join("<br>")}</div>`; return; }
    toast("안내처를 저장했습니다."); linkForm(null); await loadAtt(); return;
  }
  if (t.id === "lkClear") { linkForm(null); return; }
});

async function uploadFile(f) {
  const fd = new FormData(); fd.append("file", f);
  return (await fetch("/api/attachments/upload", {method: "POST", body: fd})).json();
}

document.addEventListener("change", async e => {
  if (e.target.id === "repFile") {                 // 교체용 새 파일
    const f = e.target.files[0]; if (!f || !REP_KEY) return;
    toast("업로드 중…");
    const r = await uploadFile(f);
    if (!r.ok) { toast(r.errors.join(" "), true); return; }
    const note = prompt("교체 사유를 남겨 두세요 (선택, 100자)", "") || "";
    const res = await api("/api/attachments/replace",
                          {key: REP_KEY, filename: r.filename, note});
    if (!res.ok) { toast((res.errors || ["교체 실패"]).join(" "), true); return; }
    REP_KEY = null;
    toast("교체했습니다. 원본 파일은 그대로 보존됩니다."); await loadAtt(); return;
  }
  if (e.target.id !== "axFile") return;
  const f = e.target.files[0]; if (!f) return;
  $("#axUp").innerHTML = `<small style="color:var(--tx3)">업로드 중…</small>`;
  const r = await uploadFile(f);
  if (!r.ok) { $("#axUp").innerHTML = `<div class="note bad">${r.errors.join("<br>")}</div>`; AX_FILE = ""; return; }
  AX_FILE = r.filename;
  $("#axUp").innerHTML = `<small style="color:var(--ok)">업로드 완료 · ${(r.size/1024).toFixed(0)}KB</small>`;
});

document.addEventListener("blur", async e => {
  const el = e.target;
  if (!el.classList || !el.classList.contains("attLbl")) return;
  const key = el.dataset.key, label = el.value.trim();
  const cur = ATT.docs.flatMap(d => d.items).find(i => i.key === key);
  if (!cur || cur.label === label) return;
  const r = await api("/api/attachments/label", {key, label});
  if (!r.ok) { toast(r.errors.join(" "), true); el.value = cur.label; return; }
  toast("표시명을 저장했습니다."); await loadAtt();
}, true);

/* ── ⑧ OOS 안내처 ───────────────────────────────────────── */
const csvVals = s => String(s || "").split(",").map(x => x.trim()).filter(Boolean);
const lineVals = s => String(s || "").split("\n").map(x => x.trim()).filter(Boolean);

function collectReferral() {
  return {row_id: $("#rfId").value.trim(), title: $("#rfName").value.trim(),
    org: $("#rfOrg").value.trim(), status: $("#rfStatus").value, active: $("#rfActive").checked,
    required_triggers: csvVals($("#rfRequired").value), excluded_triggers: csvVals($("#rfExcluded").value),
    positive_examples: lineVals($("#rfPositive").value), negative_examples: lineVals($("#rfNegative").value),
    message: $("#rfMessage").value.trim(), url: $("#rfUrl").value.trim(),
    phone: $("#rfPhone").value.trim(), hours: $("#rfHours").value.trim(),
    evidence: $("#rfEvidence").value.trim(), last_verified_at: $("#rfVerified").value,
    link_state: $("#rfLinkState").value};
}

function referralForm(r) {
  $("#rfTitle").textContent = r ? `안내처 수정 · v${r.version}` : "안내처 작성";
  $("#rfId").value = r?.row_id || ""; $("#rfId").disabled = !!r;
  $("#rfName").value = r?.title || ""; $("#rfOrg").value = r?.org || "";
  $("#rfStatus").value = r?.status || "draft"; $("#rfActive").checked = !!r?.active;
  $("#rfRequired").value = (r?.required_triggers || []).join(", ");
  $("#rfExcluded").value = (r?.excluded_triggers || []).join(", ");
  $("#rfPositive").value = (r?.positive_examples || []).join("\n");
  $("#rfNegative").value = (r?.negative_examples || []).join("\n");
  $("#rfMessage").value = r?.message || ""; $("#rfUrl").value = r?.url || "";
  $("#rfPhone").value = r?.phone || ""; $("#rfHours").value = r?.hours || "";
  $("#rfEvidence").value = r?.evidence || ""; $("#rfVerified").value = (r?.last_verified_at || "").slice(0,10);
  $("#rfLinkState").value = r?.link_state || "unknown"; $("#rfErr").innerHTML = ""; $("#rfPreview").innerHTML = "";
}

function renderReferrals() {
  $("#rfTbl").innerHTML = `<tr><th>row_id / 안내처</th><th>트리거</th><th>상태</th><th></th></tr>` +
    (REFERRALS.length ? REFERRALS.map(r => `<tr><td><code>${esc(r.row_id)}</code><br><b>${esc(r.title)}</b><br><small>${esc(r.org)}</small></td>
      <td><small>${r.required_triggers.map(esc).join(" + ")}${r.excluded_triggers.length ? `<br>제외: ${r.excluded_triggers.map(esc).join(", ")}` : ""}</small></td>
      <td><span class="tag ${r.status === "published" && r.active ? "ok" : r.status === "disabled" ? "bad" : "warn"}">${esc(r.status)}</span>
        <br><small>v${r.version} · ${esc(kst(r.updated_at))}</small></td>
      <td class="n"><button class="btn sm ghost" data-rfe="${esc(r.row_id)}">수정</button></td></tr>`).join("")
      : `<tr><td colspan="4"><small>등록된 안내처가 없습니다.</small></td></tr>`);
}

function phoneForm(p) {
  $("#pgMessage").value = p?.message || ""; $("#pgPhone").value = p?.phone || "";
  $("#pgHours").value = p?.hours || ""; $("#pgEvidence").value = p?.evidence || "";
  $("#pgVerified").value = (p?.last_verified_at || "").slice(0,10);
  $("#pgStatus").value = p?.status || "draft"; $("#pgActive").checked = !!p?.active;
}

async function loadOOS() {
  const [schema, refs, phone] = await Promise.all([api("/api/oos/schema"), api("/api/oos/referrals"), api("/api/oos/phone-guide")]);
  OOS_SCHEMA = schema; REFERRALS = refs.referrals; PHONE_GUIDE = phone.phone_guide;
  renderReferrals(); phoneForm(PHONE_GUIDE);
  $("#rpFilter").innerHTML = `<option value="">전체</option>` + schema.report_statuses.map(s => `<option>${esc(s)}</option>`).join("");
  $("#rpStatus").innerHTML = schema.report_statuses.map(s => `<option>${esc(s)}</option>`).join("");
  await loadReports();
}

document.addEventListener("click", async e => {
  const t = e.target;
  if (t.dataset.rfe) { referralForm(REFERRALS.find(r => r.row_id === t.dataset.rfe)); $("#rfTitle").scrollIntoView({behavior:"smooth"}); return; }
  if (t.id === "rfClear") { referralForm(null); return; }
  if (t.id === "rfPreviewBtn") {
    const r = await api("/api/oos/referrals/preview", {referral: collectReferral()});
    $("#rfErr").innerHTML = r.errors.length ? `<div class="note bad">${r.errors.map(esc).join("<br>")}</div>` : "";
    $("#rfPreview").innerHTML = !r.errors.length ? `<div class="note ok">정상 예시 ${r.positive.filter(x=>x.matched).length}/${r.positive.length} 발동 · 반례 ${r.negative.filter(x=>!x.matched).length}/${r.negative.length} 미발동</div>
      <div class="note"><b>사용자에게 보일 고정 응답</b><br>${esc(r.response.message)}<br><b>${esc(r.response.org)}</b>${r.response.url ? `<br>${esc(r.response.url)}` : ""}${r.response.phone ? `<br>전화 ${esc(r.response.phone)}` : ""}${r.response.hours ? `<br>운영시간 ${esc(r.response.hours)}` : ""}</div>` : ""; return;
  }
  if (t.id === "rfSave") {
    const r = await api("/api/oos/referrals", {referral: collectReferral()});
    if (!r.ok) { $("#rfErr").innerHTML = `<div class="note bad">${r.errors.map(esc).join("<br>")}</div>`; return; }
    toast("안내처를 저장했습니다."); referralForm(null); await loadOOS(); return;
  }
  if (t.id === "pgSave") {
    const phone_guide = {message: $("#pgMessage").value, phone: $("#pgPhone").value,
      hours: $("#pgHours").value, evidence: $("#pgEvidence").value,
      last_verified_at: $("#pgVerified").value, status: $("#pgStatus").value,
      active: $("#pgActive").checked};
    const r = await api("/api/oos/phone-guide", {phone_guide});
    if (!r.ok) { $("#pgErr").innerHTML = `<div class="note bad">${r.errors.map(esc).join("<br>")}</div>`; return; }
    $("#pgErr").innerHTML = ""; toast("유선 상담 안내를 저장했습니다."); await loadOOS(); return;
  }
});

/* ── ⑨ 오류 신고함 ───────────────────────────────────────── */
async function loadReports() {
  const qs = new URLSearchParams();
  if ($("#rpFilter")?.value) qs.set("status", $("#rpFilter").value);
  if ($("#rpQuery")?.value) qs.set("q", $("#rpQuery").value);
  const r = await api("/api/oos/reports?" + qs.toString()); REPORTS = r.reports;
  $("#rpTbl").innerHTML = `<tr><th>신고</th><th>경로</th><th>상태</th><th>삭제 예정</th></tr>` +
    (REPORTS.length ? REPORTS.map(x => `<tr data-rpid="${esc(x.report_id)}" style="cursor:pointer"><td><code>${esc(x.report_id)}</code><br><small>${esc(kst(x.created_at))}</small></td>
      <td>${esc(x.report_path)}</td><td><span class="tag">${esc(x.status)}</span>${x.assigned_to ? `<br><small>${esc(x.assigned_to)}</small>` : ""}${x.duplicate_of ? `<br><small>↳ ${esc(x.duplicate_of)}</small>` : ""}</td>
      <td><small>${esc(kst(x.expires_at))}</small></td></tr>`).join("") : `<tr><td colspan="4"><small>신고가 없습니다.</small></td></tr>`);
}

async function openReport(id) {
  SELECTED_REPORT = await api(`/api/oos/reports/${encodeURIComponent(id)}`);
  $("#rpDetail").style.display = "block"; $("#rpId").textContent = SELECTED_REPORT.report_id;
  $("#rpMeta").textContent = `세션 ${SELECTED_REPORT.session_id} · ${SELECTED_REPORT.report_path} · 생성 ${kst(SELECTED_REPORT.created_at)} · 삭제 예정 ${kst(SELECTED_REPORT.expires_at)}`;
  $("#rpStatus").value = SELECTED_REPORT.status; $("#rpAssignee").value = SELECTED_REPORT.assigned_to || "";
  $("#rpDuplicate").value = SELECTED_REPORT.duplicate_of || ""; $("#rpNote").value = "";
  $("#rpPayload").textContent = JSON.stringify(SELECTED_REPORT.payload, null, 2);
  $("#rpNotes").innerHTML = SELECTED_REPORT.notes.length ? SELECTED_REPORT.notes.map(n => `<div class="note"><b>${esc(n.actor)}</b> · ${esc(kst(n.created_at))}<br>${esc(n.body)}</div>`).join("") : `<small>메모가 없습니다.</small>`;
  $("#rpDetail").scrollIntoView({behavior:"smooth", block:"start"});
}

document.addEventListener("click", async e => {
  const row = e.target.closest("[data-rpid]"); if (row) { await openReport(row.dataset.rpid); return; }
  if (e.target.id === "rpSearch") { await loadReports(); return; }
  if (e.target.id === "rpSave" && SELECTED_REPORT) {
    const r = await api(`/api/oos/reports/${encodeURIComponent(SELECTED_REPORT.report_id)}`,
      {status: $("#rpStatus").value, assigned_to: $("#rpAssignee").value,
       duplicate_of: $("#rpDuplicate").value, note: $("#rpNote").value});
    if (!r.ok) { toast((r.errors || ["저장 실패"]).join(" "), true); return; }
    toast("신고 처리 내용을 저장했습니다."); await loadReports(); await openReport(SELECTED_REPORT.report_id);
  }
});

/* ── 시작 ──────────────────────────────────────────────── */
(async () => {
  let saved = null;
  try { saved = localStorage.getItem(RB_KEY); } catch (e) { /* 무시 */ }
  setResultCompact(saved === "1", false);
  SCHEMA = await api("/api/schema");
  await Promise.all([reload(), loadOOS()]);
})().catch(e => toast("초기화 실패: " + e.message, true));
