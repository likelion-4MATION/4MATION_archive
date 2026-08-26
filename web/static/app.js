"use strict";

const ui = {
  sessionId: null,
  snapshot: null,
  busy: false,
  activeTab: "recommendations",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function element(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = options.text;
  if (options.attrs) Object.entries(options.attrs).forEach(([key, value]) => node.setAttribute(key, value));
  for (const child of children) node.append(child);
  return node;
}

function button(label, onClick, className = "button secondary") {
  const node = element("button", { className, text: label, attrs: { type: "button" } });
  node.disabled = ui.busy;
  node.addEventListener("click", onClick);
  return node;
}

function safeExternalUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch (_) {
    return null;
  }
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "요청을 처리하지 못했습니다.");
  return data;
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 3200);
}

async function run(action, loadingMessage = "답변을 생성하고 있습니다…") {
  if (ui.busy) return;
  ui.busy = true;
  $("#loading strong").textContent = loadingMessage;
  render();
  try {
    ui.snapshot = await action();
  } catch (error) {
    toast(error.message);
  } finally {
    ui.busy = false;
    render();
  }
}

async function createSession() {
  ui.snapshot = await request("/api/sessions", { method: "POST", body: "{}" });
  ui.sessionId = ui.snapshot.session_id;
  localStorage.setItem("kdic-session-id", ui.sessionId);
}

async function bootstrap() {
  const saved = localStorage.getItem("kdic-session-id");
  if (saved) {
    try {
      ui.snapshot = await request(`/api/sessions/${saved}`);
      ui.sessionId = saved;
    } catch (_) {
      localStorage.removeItem("kdic-session-id");
    }
  }
  if (!ui.snapshot) await createSession();
  bindStaticEvents();
  render();
}

async function newChat() {
  if (ui.sessionId) await request(`/api/sessions/${ui.sessionId}`, { method: "DELETE" }).catch(() => null);
  await createSession();
  return ui.snapshot;
}

function sendQuestion(text, newTopic = false) {
  const value = text.trim();
  if (!value) return;
  $("#question").value = "";
  resizeComposer();
  run(() => request(`/api/sessions/${ui.sessionId}/messages`, {
    method: "POST", body: JSON.stringify({ text: value, new_topic: newTopic }),
  }), newTopic ? "새 질문을 확인하고 있습니다…" : "답변을 생성하고 있습니다…");
}

function performAction(payload, label) {
  run(() => request(`/api/sessions/${ui.sessionId}/actions`, {
    method: "POST", body: JSON.stringify(payload),
  }), label || "선택하신 조건을 반영하고 있습니다…");
}

function updateSettings(patch) {
  run(() => request(`/api/sessions/${ui.sessionId}/settings`, {
    method: "PATCH", body: JSON.stringify(patch),
  }), "설정을 반영하고 있습니다…");
}

function renderLanding() {
  const root = $("#landing");
  root.replaceChildren();
  if (!ui.snapshot || ui.snapshot.history.length) return;
  root.append(element("h2", { className: "landing-title", text: "자주 찾는 업무" }));
  const grid = element("div", { className: "landing-grid" });
  for (const item of ui.snapshot.recommendations.landing) {
    const card = element("article", { className: "landing-card" });
    card.append(
      element("span", { className: "category", text: item.label }),
      element("strong", { text: item.question }),
      button("바로 물어보기  →", () => sendQuestion(item.question, true), ""),
    );
    grid.append(card);
  }
  root.append(grid);
}

function renderHistory() {
  const root = $("#history");
  root.replaceChildren();
  if (!ui.snapshot) return;
  const history = ui.snapshot.history;
  const lastAnswer = [...history].reverse().find((turn) => turn.role === "answer");
  for (const turn of history) {
    if (turn.role === "user") {
      root.append(element("section", { className: "turn user" }, [element("h2", { text: turn.text })]));
      continue;
    }
    if (turn.role === "ask") {
      const box = element("section", { className: "turn assistant ask-box" });
      box.append(element("p", { text: turn.prompt }));
      const row = element("div", { className: "button-row" });
      const options = ui.snapshot.state.pending?.options || turn.options || [];
      for (const option of options) {
        row.append(button(option, () => performAction({ type: "choose", value: option })));
      }
      if (ui.snapshot.state.pending) {
        row.append(
          button("잘 모르겠어요 — 이대로 답변받기", () => performAction({ type: "skip" }, "답변을 생성하고 있습니다…")),
          button("이건 넘어갈게요", () => performAction({ type: "pass" })),
        );
      }
      box.append(row);
      root.append(box);
      continue;
    }

    const section = element("section", { className: "turn assistant" });
    if (turn.text === null) section.append(element("div", { className: "answer-error", text: turn.error_text }));
    else section.append(element("div", { className: "answer-text", text: turn.text || "" }));

    const filled = Object.entries(turn.slots || {}).filter(([, value]) => value);
    if (filled.length) {
      const slots = element("div", { className: "slot-list", attrs: { "aria-label": "확정된 조건" } });
      for (const [field, value] of filled) {
        const chip = element("span", { className: "slot" });
        chip.append(element("span", { text: `${slotLabel(field)} · ${value}` }));
        if (lastAnswer?.message_id === turn.message_id && !ui.snapshot.state.pending) {
          chip.append(button("×", () => performAction({ type: "edit", field, value: null }), ""));
        }
        slots.append(chip);
      }
      section.append(slots);
    }

    const meta = [turn.route_label];
    if (typeof turn.confidence === "number") meta.push(`관련 문서 유사도 ${turn.confidence.toFixed(2)}`);
    if (turn.latency_ms) meta.push(`${turn.latency_ms}ms`);
    section.append(element("div", { className: "answer-meta", text: meta.filter(Boolean).join(" · ") }));

    if (turn.attachments?.length) {
      const details = element("details");
      details.append(element("summary", { text: `관련 서식·첨부파일 (${turn.attachments.length}건)` }));
      for (const attachment of turn.attachments) {
        const row = element("p");
        if (attachment.available) {
          const link = element("a", { text: attachment.label, attrs: { href: attachment.download_url } });
          row.append(link);
        } else if (safeExternalUrl(attachment.source_url)) {
          row.append(element("a", { text: attachment.label, attrs: { href: safeExternalUrl(attachment.source_url), target: "_blank", rel: "noopener" } }));
        } else row.textContent = attachment.label;
        details.append(row);
      }
      section.append(details);
    }

    if (turn.referral) {
      const referral = element("div", { className: "regen-box" });
      referral.append(element("strong", { text: `안내처 · ${turn.referral.org || ""}` }));
      if (safeExternalUrl(turn.referral.url)) referral.append(element("a", { text: "공식 안내 페이지", attrs: { href: safeExternalUrl(turn.referral.url), target: "_blank", rel: "noopener" } }));
      if (turn.referral.phone) referral.append(element("p", { text: `전화: ${turn.referral.phone}` }));
      section.append(referral);
    }

    if (turn.followups?.length && lastAnswer?.message_id === turn.message_id) {
      const row = element("div", { className: "button-row" });
      for (const item of turn.followups) {
        row.append(button(`${slotLabel(item.field)} · ${item.value}`, () => performAction({ type: "edit", field: item.field, value: item.value })));
      }
      section.append(row);
    }
    root.append(section);
  }
}

function slotLabel(field) {
  return { party: "역할", sub_task: "세부주제", qualification: "자격", subject: "주체", method: "접수수단" }[field] || field;
}

function memoryValue(item) {
  if (item.passed) return "다시 묻지 않도록 건너뜀";
  if (Array.isArray(item.value)) return item.value.filter(Boolean).join(", ");
  if (item.value && typeof item.value === "object") return Object.values(item.value).filter(Boolean).join(", ");
  return item.value === null || item.value === undefined ? "" : String(item.value);
}

function runMemoryAction(item, op) {
  const payload = { type: "memory", op };
  if (item.field) payload.field = item.field;
  if (item.index !== undefined) payload.index = item.index;
  if (op === "edit") {
    const value = window.prompt(`${item.label || item.field} 값을 입력해 주세요.`, memoryValue(item));
    if (value === null || !value.trim()) return;
    payload.value = value.trim();
  }
  performAction(payload);
}

function renderConversationActions() {
  const root = $("#conversation-actions");
  root.replaceChildren();
  if (!ui.snapshot) return;
  if (ui.snapshot.state.needs_regen) {
    const box = element("section", { className: "regen-box" });
    box.append(
      element("p", { text: "조건이 바뀌었습니다. 이 조건으로 답변을 다시 받으시겠어요?" }),
      button("이 조건으로 다시 답변받기", () => performAction({ type: "regenerate" }, "답변을 생성하고 있습니다…"), "button primary"),
    );
    root.append(box);
  }
  if (ui.snapshot.state.queue_size && !ui.snapshot.state.pending) {
    const box = element("section", { className: "queue-box" });
    box.append(
      element("p", { text: `대기 중인 용건이 ${ui.snapshot.state.queue_size}개 있습니다.` }),
      button("다음 용건 처리", () => performAction({ type: "next_unit" }, "다음 용건을 처리하고 있습니다…"), "button primary"),
    );
    root.append(box);
  }
}

function renderSidebar() {
  if (!ui.snapshot) return;
  const questions = ui.snapshot.history.filter((turn) => turn.role === "user");
  const list = $("#question-history");
  list.replaceChildren();
  if (!questions.length) list.append(element("li", { className: "empty", text: "아직 질문이 없습니다." }));
  else questions.forEach((turn) => list.append(element("li", { text: turn.text })));

  const memory = ui.snapshot.state.memory;
  const memoryRoot = $("#memory");
  memoryRoot.replaceChildren();
  const zoneNotes = {
    "적용 중": "현재 답변에 반영되는 조건",
    "기억만 함": "다음 질문에 이어지는 정보",
    "대기 중인 용건": "이어서 처리할 질문",
  };
  const zones = (memory?.zones || []).map((zone) => ({
    ...zone,
    items: (zone.items || []).filter((item) => Boolean(memoryValue(item))),
  })).filter((zone) => zone.items.length);
  const memoryCount = zones.reduce((count, zone) => count + zone.items.length, 0);
  $("#memory-section").hidden = memoryCount === 0;
  $("#memory-count").textContent = `${memoryCount}개`;
  for (const zone of zones) {
    const zoneNode = element("section", { className: "memory-zone" });
    const zoneName = zone.label || zone.name || "기억";
    zoneNode.append(
      element("h3", { text: zoneName }),
      element("p", { className: "memory-zone-note", text: zoneNotes[zoneName] || "저장된 대화 정보" }),
    );
    for (const item of zone.items) {
      const itemNode = element("div", { className: "memory-item" });
      const head = element("div", { className: "memory-item-head" });
      head.append(element("strong", { text: item.headline || item.label || item.field || "항목" }));
      if (item.status && item.status !== "적용") head.append(element("span", { className: "memory-status", text: item.status }));
      itemNode.append(head, element("span", { className: "memory-value", text: memoryValue(item) }));
      if (item.actionable && item.ops?.length) {
        const actions = element("div", { className: "memory-actions" });
        for (const op of item.ops) {
          const labels = { edit: "수정", clear: "해제", pass: "건너뛰기", move: "위로", drop: "삭제" };
          actions.append(button(labels[op] || op, () => runMemoryAction(item, op), ""));
        }
        itemNode.append(actions);
      }
      zoneNode.append(itemNode);
    }
    memoryRoot.append(zoneNode);
  }

  const settings = ui.snapshot.state.settings;
  $("#ask-mode").value = settings.ask_mode;
  $("#boost").checked = settings.boost;
  $("#qform-scope").value = settings.qform_scope;
  $("#show-trace").checked = settings.show_trace;

  const calls = ui.snapshot.state.calls;
  const budget = $("#call-budget");
  budget.className = `budget ${calls.remaining <= 0 ? "empty" : calls.remaining <= 10 ? "low" : ""}`;
  budget.textContent = `모델 호출 ${calls.used} / ${calls.budget}`;
}

function renderRecommendations() {
  const root = $("#recommendations");
  root.replaceChildren();
  if (!ui.snapshot) return;
  const recs = ui.snapshot.recommendations;
  root.append(element("h2", { className: "rail-title", text: recs.context_title }));
  for (const question of recs.context) {
    root.append(button(question, () => sendQuestion(question, true), "rail-question"));
  }
  root.append(element("h2", { className: "rail-title", text: "업무별 추천 검색어" }));
  for (const domain of recs.domains) {
    const details = element("details", { className: "domain" });
    details.append(element("summary", { text: domain.label }));
    for (const question of domain.questions) {
      details.append(button(question, () => sendQuestion(question, true), "rail-question"));
    }
    root.append(details);
  }
}

function renderEvidence() {
  const root = $("#evidence");
  root.replaceChildren();
  if (!ui.snapshot) return;
  const answer = [...ui.snapshot.history].reverse().find((turn) => turn.role === "answer");
  if (!answer) {
    root.append(element("p", { text: "답변을 받으면 근거 문서와 근거 조각이 표시됩니다." }));
    return;
  }
  root.append(element("h2", { className: "rail-title", text: "참고 문헌·출처" }));
  for (const source of answer.sources || []) {
    const card = element("article", { className: "evidence-card" });
    const url = safeExternalUrl(source.url);
    if (url) card.append(element("a", { text: source.title || "출처", attrs: { href: url, target: "_blank", rel: "noopener" } }));
    else card.append(element("span", { text: source.title || "출처" }));
    root.append(card);
  }
  root.append(element("h2", { className: "rail-title", text: "근거 조각" }));
  for (const hit of answer.retrieval || []) {
    const card = element("article", { className: "evidence-card" });
    const score = typeof hit.score === "number" ? ` · 유사도 ${hit.score.toFixed(2)}` : "";
    card.append(
      element("strong", { text: `${hit.rank || ""}. ${hit.title || hit.doc_id || "문서"}${score}` }),
      element("p", { text: hit.text_excerpt || "본문 없음" }),
    );
    const url = safeExternalUrl(hit.url);
    if (url) card.append(element("a", { text: "원문 페이지 열기", attrs: { href: url, target: "_blank", rel: "noopener" } }));
    root.append(card);
  }
  if (answer.checks && !answer.checks.ok) {
    root.append(element("h2", { className: "rail-title", text: "검증 플래그 · 차단 아님" }));
    for (const flag of answer.checks.flags || []) root.append(element("p", { text: flag }));
  }
}

function render() {
  if (!ui.snapshot) return;
  renderLanding();
  renderHistory();
  renderConversationActions();
  renderSidebar();
  renderRecommendations();
  renderEvidence();
  $("#loading").hidden = !ui.busy;
  $("#composer button").disabled = ui.busy;
  $("#question").disabled = ui.busy;
  $("#new-chat").disabled = ui.busy;
  const history = $("#history");
  if (ui.busy) $("#loading").scrollIntoView({ behavior: "smooth", block: "nearest" });
  else if (history.lastElementChild) history.lastElementChild.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function resizeComposer() {
  const textarea = $("#question");
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`;
}

function bindStaticEvents() {
  $("#new-chat").addEventListener("click", () => run(newChat, "새 대화를 준비하고 있습니다…"));
  $("#composer").addEventListener("submit", (event) => {
    event.preventDefault();
    sendQuestion($("#question").value);
  });
  $("#question").addEventListener("input", resizeComposer);
  $("#question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("#composer").requestSubmit();
    }
  });
  $("#report-error").addEventListener("click", () => run(async () => {
    const result = await request(`/api/sessions/${ui.sessionId}/reports`, { method: "POST", body: "{}" });
    toast(`오류 신고가 접수되었습니다 (${result.report_id}).`);
    return ui.snapshot;
  }, "오류 신고를 접수하고 있습니다…"));
  $("#ask-mode").addEventListener("change", (event) => updateSettings({ ask_mode: event.target.value }));
  $("#boost").addEventListener("change", (event) => updateSettings({ boost: event.target.checked }));
  $("#qform-scope").addEventListener("change", (event) => updateSettings({ qform_scope: event.target.value }));
  $("#show-trace").addEventListener("change", (event) => updateSettings({ show_trace: event.target.checked }));
  $$(".tab").forEach((tab) => tab.addEventListener("click", () => {
    ui.activeTab = tab.dataset.tab;
    $$(".tab").forEach((item) => {
      const active = item.dataset.tab === ui.activeTab;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", String(active));
    });
    $("#recommendations").hidden = ui.activeTab !== "recommendations";
    $("#evidence").hidden = ui.activeTab !== "evidence";
  }));
}

bootstrap().catch((error) => {
  document.body.replaceChildren(element("main", { className: "app-shell" }, [
    element("h1", { text: "서비스를 시작하지 못했습니다." }),
    element("p", { text: error.message }),
  ]));
});
