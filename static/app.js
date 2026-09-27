/* AI-location 前端逻辑 */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const state = {
  shots: [],          // {id, kind:'text'|'image', text, caption, dataUrl}
  lastData: null,     // 最近一次检测返回
};
const SETTINGS_KEY = "ai_location_settings";
const settings = Object.assign(
  { base_url: "", model: "gpt-4o", api_key: "" },
  JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}")
);

const PALETTE = ["#6366f1", "#0ea5e9", "#f59e0b", "#10b981", "#ef4444", "#a855f7", "#ec4899", "#14b8a6"];
const SIDE_CN = { left: "画面左侧", center: "画面中央", right: "画面右侧", unknown: "位置未知" };
const FACING_CN = {
  left: "面朝左 ←", right: "面朝右 →",
  toward_camera: "面向镜头", away: "背对镜头", unknown: "朝向未知",
};
const SEV_CN = { high: "严重", medium: "中等", low: "轻微" };

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (m) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}
function uid() {
  return "s-" + Math.random().toString(36).slice(2, 9) + Date.now().toString(36).slice(-4);
}
function colorFor(name) {
  let h = 0;
  for (const ch of name || "?") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
function initial(name) {
  name = (name || "?").trim();
  return name.length <= 2 ? name : name.slice(-2);
}
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => (t.hidden = true), 2200);
}

/* ---------------- 镜头列表 ---------------- */
function renderShots() {
  const list = $("#shotList");
  $("#shotCount").textContent = state.shots.length;
  $("#emptyHint").hidden = state.shots.length > 0;
  $("#runBtn").disabled = state.shots.length === 0;

  const flagged = new Map(); // shot index(1-based) -> severity
  (state.lastData?.issues || []).forEach((iss) => {
    iss.shots.forEach((n) => {
      const rank = { high: 3, medium: 2, low: 1 };
      if ((rank[iss.severity] || 0) > (rank[flagged.get(n)] || 0)) flagged.set(n, iss.severity);
    });
  });

  list.innerHTML = state.shots.map((s, i) => {
    const no = i + 1;
    const flag = flagged.get(no);
    const media = s.kind === "image"
      ? `<img class="shot-thumb" src="${s.dataUrl}" alt="分镜图" />
         <input class="shot-caption" data-id="${s.id}" placeholder="图片补充说明（可选，会一并交给 AI）"
                value="${esc(s.caption || "")}" />`
      : `<textarea class="shot-text" rows="2" data-id="${s.id}">${esc(s.text || "")}</textarea>`;
    return `
    <li class="shot-item ${flag ? "has-issue" : ""}">
      <div class="shot-idx">${no}</div>
      <div class="shot-body">
        <span class="shot-tag ${s.kind}">${s.kind === "image" ? "🖼 图片镜头" : "📝 文本镜头"}</span>
        ${media}
      </div>
      <div class="shot-ops">
        <button class="icon-btn" data-op="up" data-id="${s.id}" title="上移" ${i === 0 ? "disabled" : ""}>↑</button>
        <button class="icon-btn" data-op="down" data-id="${s.id}" title="下移" ${i === state.shots.length - 1 ? "disabled" : ""}>↓</button>
        <button class="icon-btn" data-op="del" data-id="${s.id}" title="删除">✕</button>
      </div>
    </li>`;
  }).join("");
}

$("#shotList").addEventListener("input", (e) => {
  const el = e.target;
  const id = el.dataset.id;
  const shot = state.shots.find((s) => s.id === id);
  if (!shot) return;
  if (el.classList.contains("shot-text")) shot.text = el.value;
  if (el.classList.contains("shot-caption")) shot.caption = el.value;
});

$("#shotList").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-op]");
  if (!btn) return;
  const id = btn.dataset.id;
  const i = state.shots.findIndex((s) => s.id === id);
  if (i < 0) return;
  if (btn.dataset.op === "del") {
    state.shots.splice(i, 1);
    renderShots();
  } else if (btn.dataset.op === "up" && i > 0) {
    [state.shots[i - 1], state.shots[i]] = [state.shots[i], state.shots[i - 1]];
    renderShots();
  } else if (btn.dataset.op === "down" && i < state.shots.length - 1) {
    [state.shots[i + 1], state.shots[i]] = [state.shots[i], state.shots[i + 1]];
    renderShots();
  }
});

$("#addTextBtn").addEventListener("click", () => {
  const ta = $("#promptInput");
  const text = ta.value.trim();
  if (!text) { toast("请先粘贴 prompt 文本"); ta.focus(); return; }
  state.shots.push({ id: uid(), kind: "text", text, caption: "", dataUrl: null });
  ta.value = "";
  renderShots();
});

$("#addImgBtn").addEventListener("click", () => $("#imgInput").click());
$("#imgInput").addEventListener("change", async (e) => {
  const files = Array.from(e.target.files || []);
  for (const file of files) {
    const dataUrl = await readFile(file);
    state.shots.push({ id: uid(), kind: "image", text: "", caption: "", dataUrl });
  }
  e.target.value = "";
  renderShots();
});
function readFile(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

$("#clearBtn").addEventListener("click", () => {
  if (!state.shots.length) return;
  if (!confirm("确定清空所有镜头吗？")) return;
  state.shots = [];
  state.lastData = null;
  $("#report").hidden = true;
  $("#reportEmpty").hidden = false;
  renderShots();
});

/* ---------------- API 设置 ---------------- */
function syncApiStatus() {
  const el = $("#apiStatus");
  const ok = !!settings.api_key;
  el.textContent = ok ? `已配置：${settings.model || "默认模型"}` : "未配置 API";
  el.classList.toggle("ok", ok);
}
function openSettings() {
  $("#cfgBaseUrl").value = settings.base_url || "";
  $("#cfgModel").value = settings.model || "";
  $("#cfgApiKey").value = settings.api_key || "";
  $("#settingsModal").hidden = false;
}
$("#settingsBtn").addEventListener("click", openSettings);
$("#cfgCancel").addEventListener("click", () => ($("#settingsModal").hidden = true));
$(".modal-mask").addEventListener("click", () => ($("#settingsModal").hidden = true));
$("#cfgSave").addEventListener("click", () => {
  settings.base_url = $("#cfgBaseUrl").value.trim();
  settings.model = $("#cfgModel").value.trim();
  settings.api_key = $("#cfgApiKey").value.trim();
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  $("#settingsModal").hidden = true;
  syncApiStatus();
  toast("已保存 API 设置");
});
$$(".preset").forEach((b) => b.addEventListener("click", () => {
  $("#cfgBaseUrl").value = b.dataset.base;
  $("#cfgModel").value = b.dataset.model;
}));

/* ---------------- 检测 ---------------- */
function setLoading(on, text) {
  const loading = $("#loading");
  if (loading) loading.hidden = !on;
  const loadingText = $("#loadingText");
  if (loadingText) loadingText.textContent = text || "正在分析镜头…";
}

$("#demoBtn").addEventListener("click", async () => {
  setLoading(true, "正在载入示例…");
  try {
    const resp = await fetch("/api/demo", { method: "POST" });
    const data = await resp.json();
    state.shots = data.shots.map((s) => ({
      id: s.id, kind: s.kind, text: s.text || "", caption: s.caption || "", dataUrl: null,
    }));
    state.lastData = data;
    renderShots();
    renderReport(data);
    toast("已载入 4 个示例镜头（含 1 处越轴 + 1 处动作断裂）");
  } catch (err) {
    toast("示例载入失败：" + err.message);
  } finally {
    setLoading(false);
  }
});

$("#runBtn").addEventListener("click", async () => {
  if (!state.shots.length) return;
  if (!settings.api_key) {
    if (confirm("还没有配置 API Key，无法调用多模态模型。\n点“确定”去配置（支持 OpenAI / 通义千问 VL 等兼容接口），点“取消”先看内置示例。")) {
      openSettings();
    }
    return;
  }
  setLoading(true, `正在分析 ${state.shots.length} 个镜头，请稍候…`);
  try {
    const resp = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shots: state.shots.map((s) => ({
          id: s.id, kind: s.kind, text: s.text, caption: s.caption,
          image_data_url: s.dataUrl || null,
        })),
        api_key: settings.api_key,
        base_url: settings.base_url,
        model: settings.model,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      alert("检测失败：" + (data.detail || resp.statusText));
      return;
    }
    state.lastData = data;
    renderShots();
    renderReport(data);
    toast("检测完成");
  } catch (err) {
    alert("请求失败：" + err.message);
  } finally {
    setLoading(false);
  }
});

/* ---------------- 报告渲染 ---------------- */
function renderReport(data) {
  $("#reportEmpty").hidden = true;
  $("#report").hidden = false;
  renderStats(data);
  renderIssues(data);
  renderDiagram(data);
  renderShotDetails(data);
}

function renderStats(data) {
  const sev = { high: 0, medium: 0, low: 0 };
  data.issues.forEach((i) => { sev[i.severity] = (sev[i.severity] || 0) + 1; });
  $("#stats").innerHTML = `
    <div class="stat"><div class="num">${data.shots.length}</div><div class="lbl">镜头总数</div></div>
    <div class="stat s-high"><div class="num">${sev.high}</div><div class="lbl">严重（越轴/断裂）</div></div>
    <div class="stat s-medium"><div class="num">${sev.medium}</div><div class="lbl">中等问题</div></div>
    <div class="stat s-low"><div class="num">${sev.low}</div><div class="lbl">轻微问题</div></div>
    <div class="stat s-ok"><div class="num">${data.issues.length ? "—" : "✓"}</div><div class="lbl">${data.issues.length ? "需处理" : "连续性通过"}</div></div>`;
}

function renderIssues(data) {
  const box = $("#issues");
  if (!data.issues.length) {
    box.innerHTML = `<div class="all-clear">✅ 未发现站位、越轴与动作衔接问题，镜头连续性通过</div>`;
    return;
  }
  const order = ["越轴", "视线匹配", "人物站位", "道具连续性", "动作衔接", "服装连续性", "连续性"];
  const groups = new Map();
  data.issues.forEach((iss) => {
    const key = order.includes(iss.type) ? iss.type : "连续性";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(iss);
  });
  const keys = [...order.filter((k) => groups.has(k)), ...[...groups.keys()].filter((k) => !order.includes(k))];

  box.innerHTML = keys.map((key) => {
    const items = groups.get(key).map((iss) => `
      <div class="issue ${iss.severity}">
        <div class="issue-top">
          <span class="issue-type">${esc(key)}</span>
          <span class="badge ${iss.severity}">${SEV_CN[iss.severity] || iss.severity}</span>
          ${iss.shots.map((n) => `<span class="badge shot">镜头 ${n}</span>`).join("")}
        </div>
        <p>${esc(iss.problem)}</p>
        ${iss.suggestion ? `<p class="sug">💡 ${esc(iss.suggestion)}</p>` : ""}
        ${iss.suggested_prompt ? `
          <div class="suggested">
            <span>✏️ 修正 prompt：${esc(iss.suggested_prompt)}</span>
            <button class="copy-btn" data-copy="${encodeURIComponent(iss.suggested_prompt)}">复制</button>
          </div>` : ""}
      </div>`).join("");
    return `<div style="margin-bottom:14px"><div style="font-size:13px;font-weight:700;margin-bottom:7px;color:var(--text-2)">${esc(key)}（${groups.get(key).length}）</div>${items}</div>`;
  }).join("");

  $$(".copy-btn").forEach((b) => b.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(decodeURIComponent(b.dataset.copy));
      toast("已复制到剪贴板");
    } catch {
      toast("复制失败，请手动选择文本");
    }
  }));
}

function renderDiagram(data) {
  const pair = data.main_pair || [];
  const xFor = { left: 58, center: 160, right: 262, unknown: 160 };
  const y = 70;

  const flagOf = new Map();
  data.issues.forEach((iss) => iss.shots.forEach((n) => {
    const rank = { high: 3, medium: 2, low: 1 };
    if ((rank[iss.severity] || 0) > (rank[flagOf.get(n)] || 0)) flagOf.set(n, iss.severity);
  }));

  $("#diagram").innerHTML = data.shots.map((shot, i) => {
    const no = i + 1;
    const an = shot.analysis;
    const flag = flagOf.get(no) || "";
    if (!an) {
      return `<div class="dg-card ${flag}"><div class="dg-title"><span class="tag-no">镜头 ${no}</span></div>
        <div style="height:130px;display:flex;align-items:center;justify-content:center;color:var(--text-3);font-size:12px">无解析结果</div></div>`;
    }
    const byName = {};
    an.characters.forEach((c) => (byName[c.name] = c));

    // 多人场景：为每一对“分居画面左右”的角色绘制关系轴线；
    // 全片同框最多的主角对用靛蓝色高亮，其余轴线用灰色。
    let axis = "";
    const horiz = an.characters.filter((c) => ["left", "right"].includes(c.screen_side));
    for (let p = 0; p < horiz.length; p++) {
      for (let q = p + 1; q < horiz.length; q++) {
        const a = horiz[p], b = horiz[q];
        if (a.screen_side === b.screen_side) continue;
        const x1 = xFor[a.screen_side], x2 = xFor[b.screen_side];
        const isMain = pair.length === 2 &&
          ((a.name === pair[0] && b.name === pair[1]) || (a.name === pair[1] && b.name === pair[0]));
        axis += `<line x1="${Math.min(x1, x2)}" y1="${y}" x2="${Math.max(x1, x2)}" y2="${y}"
                  stroke="${isMain ? "#6366f1" : "#94a3b8"}" stroke-width="${isMain ? 2.2 : 1.3}"
                  stroke-dasharray="6 4" opacity="${isMain ? 1 : 0.7}"/>`;
        if (isMain) {
          axis += `<text x="${(x1 + x2) / 2}" y="${y - 10}" text-anchor="middle" font-size="9.5"
                    font-weight="700" fill="#4f46e5">关系轴线</text>`;
        }
      }
    }

    const people = an.characters.map((c) => {
      const x = xFor[c.screen_side] || 160;
      const color = colorFor(c.name);
      let face = "";
      if (c.facing === "left") {
        face = `<polygon points="${x - 30},${y - 28} ${x - 18},${y - 35} ${x - 18},${y - 21}" fill="#334155"/>`;
      } else if (c.facing === "right") {
        face = `<polygon points="${x + 30},${y - 28} ${x + 18},${y - 35} ${x + 18},${y - 21}" fill="#334155"/>`;
      } else if (c.facing === "toward_camera") {
        face = `<text x="${x}" y="${y - 24}" text-anchor="middle" font-size="13" fill="#334155">⊙</text>`;
      } else if (c.facing === "away") {
        face = `<text x="${x}" y="${y - 24}" text-anchor="middle" font-size="13" fill="#94a3b8">⊗</text>`;
      }
      return `
        ${face}
        <circle cx="${x}" cy="${y}" r="21" fill="${color}" opacity="0.92"/>
        <text x="${x}" y="${y + 4.5}" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">${esc(initial(c.name))}</text>
        <text x="${x}" y="${y + 36}" text-anchor="middle" font-size="10.5" fill="#475569">${esc(c.name)}</text>`;
    }).join("");

    return `
      <div class="dg-card ${flag}">
        <div class="dg-title"><span class="tag-no">镜头 ${no}</span><span>${esc(an.shot_size || "")} ${esc(an.camera_angle || "")}</span></div>
        <svg viewBox="0 0 320 126" xmlns="http://www.w3.org/2000/svg">
          <rect x="2" y="2" width="316" height="122" rx="9" fill="#f8fafc" stroke="#dbe2ee"/>
          <line x1="160" y1="6" x2="160" y2="120" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="3 4"/>
          ${axis}
          ${people}
        </svg>
        <div class="dg-summary">${esc(an.summary || "")}</div>
      </div>`;
  }).join("");
}

function renderShotDetails(data) {
  const localMap = Object.fromEntries(state.shots.map((s) => [s.id, s]));
  $("#shotDetails").innerHTML = data.shots.map((shot, i) => {
    const an = shot.analysis;
    const local = localMap[shot.id];
    const no = i + 1;
    if (!an) return "";
    const media = shot.kind === "image" && local?.dataUrl
      ? `<img class="detail-media" src="${local.dataUrl}" alt="镜头${no}" />`
      : "";
    const promptText = shot.caption || shot.text;
    const props = (an.props || []).filter((p) => p.name).map((p) => {
      const holder = p.holder && p.holder !== "环境" ? `持有者：${esc(p.holder)}` : "在环境中";
      return `<span class="tag gray">📦 ${esc(p.name)}（${holder}${p.location ? " · " + esc(p.location) : ""}）</span>`;
    }).join("");
    const propsBlock = props
      ? `<div class="char-tags" style="margin-top:8px;padding-top:8px;border-top:1px dashed var(--border)">${props}</div>`
      : "";

    const chars = an.characters.map((c) => `
      <div class="char-item">
        <div class="char-name"><span class="char-dot" style="background:${colorFor(c.name)}"></span>${esc(c.name)}</div>
        <div class="char-tags">
          <span class="tag">${SIDE_CN[c.screen_side] || c.screen_side}</span>
          <span class="tag">${FACING_CN[c.facing] || c.facing}</span>
          ${c.pose ? `<span class="tag gray">${esc(c.pose)}</span>` : ""}
          ${c.wardrobe ? `<span class="tag gray">👕 ${esc(c.wardrobe)}</span>` : ""}
        </div>
        ${c.action ? `<div style="font-size:12.5px;line-height:1.6">动作：${esc(c.action)}</div>` : ""}
        ${c.start_state || c.end_state ? `
          <div class="state-flow">
            <span>起：${esc(c.start_state || "—")}</span>
            <span class="flow-arrow">→</span>
            <span>止：${esc(c.end_state || "—")}</span>
          </div>` : ""}
      </div>`).join("") || `<div style="font-size:12px;color:var(--text-3);padding:6px 0">未识别到人物信息</div>`;

    return `
      <div class="detail-card">
        <div class="detail-head">
          <span>镜头 ${no}</span>
          <span class="meta">${esc(an.shot_size || "景别未知")} · ${esc(an.camera_angle || "角度未知")}</span>
        </div>
        <div class="detail-body">
          ${media}
          ${promptText ? `<div class="detail-prompt">📄 ${esc(promptText)}</div>` : ""}
          <div class="detail-summary">${esc(an.summary || "")}</div>
          ${chars}
          ${propsBlock}
          ${an.scene_notes ? `<div class="scene-notes">🎬 ${esc(an.scene_notes)}</div>` : ""}
        </div>
      </div>`;
  }).join("");
}

/* ---------------- 初始化 ---------------- */
syncApiStatus();
renderShots();
