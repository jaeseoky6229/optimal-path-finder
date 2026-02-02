const officeFilterEl = document.getElementById("officeFilter");
const bridgeSearchEl = document.getElementById("bridgeSearch");
const bridgeListEl = document.getElementById("bridgeList");
const selectedCountTextEl = document.getElementById("selectedCountText");
const selectAllBridgesBtn = document.getElementById("selectAllBridges");
const clearSelectedBridgesBtn = document.getElementById("clearSelectedBridges");
const applySelectionBtn = document.getElementById("applySelection");
const optionsPanelEl = document.getElementById("optionsPanel");
const selectPanelEl = document.getElementById("selectPanel");
const resultPanelEl = document.getElementById("resultPanel");
const goHomeBtn = document.getElementById("goHomeBtn");
const saveResultBtn = document.getElementById("saveResultBtn");
const tripDaysEl = document.getElementById("tripDays");
const perBridgeInspectCardEl = document.getElementById("perBridgeInspectCard");
const perBridgeInspectBoxEl = document.getElementById("perBridgeInspectBox");
const useBulkWorkTimeEl = document.getElementById("useBulkWorkTime");
const bulkWorkTimeBoxEl = document.getElementById("bulkWorkTimeBox");
const bulkWorkStartEl = document.getElementById("bulkWorkStart");
const bulkWorkEndEl = document.getElementById("bulkWorkEnd");

// ✅ 신규(필수/마감 UI)
const perBridgeMandatoryBoxEl = document.getElementById("perBridgeMandatoryBox");

const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const optimizeBtn = document.getElementById("runOptimize");
const clearBtn = document.getElementById("clearMap");

const startDateEl = document.getElementById("startDate");
const useRouteCacheEl = document.getElementById("useRouteCache");
const routeCachePathEl = document.getElementById("routeCachePath");
const cacheLabelTextEl = document.getElementById("cacheLabelText");

const legendEl = document.getElementById("legend");
const legendItemsEl = document.getElementById("legendItems");
const legendFooterEl = document.getElementById("legendFooter");

const workGridEl = document.getElementById("workGrid");
const useBulkInspectEl = document.getElementById("useBulkInspect");
const bulkInspectMinEl = document.getElementById("bulkInspectMin");

(function initStartDateToday() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  startDateEl.value = `${yyyy}-${mm}-${dd}`;
})();

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function pad2(n) { return String(n).padStart(2, "0"); }

function parseDateYYYYMMDD(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || "").trim());
  if (!m) return null;
  const y = Number(m[1]), mo = Number(m[2]) - 1, d = Number(m[3]);
  const dt = new Date(y, mo, d, 0, 0, 0, 0);
  if (!Number.isFinite(dt.getTime())) return null;
  return dt;
}

function addDays(dt, days) {
  const x = new Date(dt.getTime());
  x.setDate(x.getDate() + Number(days || 0));
  return x;
}

function withTime(dt, hh, mm) {
  const x = new Date(dt.getTime());
  x.setHours(hh, mm, 0, 0);
  return x;
}

function addMinutes(dt, min) {
  return new Date(dt.getTime() + Number(min || 0) * 60 * 1000);
}

function fmtDate(dt) {
  return `${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`;
}

function fmtTime(dt) {
  return `${pad2(dt.getHours())}:${pad2(dt.getMinutes())}`;
}

function parseHHMM(s) {
  const m = /^(\d{2}):(\d{2})$/.exec(String(s || "").trim());
  if (!m) return null;
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return null;
  if (hh < 0 || hh > 23 || mm < 0 || mm > 59) return null;
  return { hh, mm, totalMin: hh * 60 + mm };
}

function makeTimeOptions30Min() {
  const opts = [];
  for (let h = 0; h < 24; h++) {
    for (let m = 0; m < 60; m += 30) {
      opts.push(`${pad2(h)}:${pad2(m)}`);
    }
  }
  return opts;
}

const TIME_OPTIONS = makeTimeOptions30Min();

function fillSelectWithTimes(selectEl, defaultValue) {
  if (!selectEl) return;
  selectEl.innerHTML = "";
  for (const t of TIME_OPTIONS) {
    const op = document.createElement("option");
    op.value = t;
    op.textContent = t;
    selectEl.appendChild(op);
  }
  if (defaultValue) selectEl.value = defaultValue;
}

function getMaxDays() {
  const v = Number(tripDaysEl?.value ?? 7);
  if (!Number.isFinite(v)) return 7;
  return Math.min(30, Math.max(1, Math.floor(v)));
}

function clearWorkGridRows() {
  // workGrid에는 헤더 3칸이 이미 있음: <div></div><div class="hdr">시작</div><div class="hdr">끝</div>
  while (workGridEl.children.length > 3) {
    workGridEl.removeChild(workGridEl.lastChild);
  }
}

function buildDayWorkTimeUI(maxDays) {
  clearWorkGridRows();

  for (let day = 1; day <= maxDays; day++) {
    const dayLabel = document.createElement("div");
    dayLabel.className = "dayLabel";
    dayLabel.textContent = `Day ${day}`;

    const stSel = document.createElement("select");
    stSel.id = `day${day}_start`;
    for (const t of TIME_OPTIONS) {
      const op = document.createElement("option");
      op.value = t;
      op.textContent = t;
      stSel.appendChild(op);
    }

    const enSel = document.createElement("select");
    enSel.id = `day${day}_end`;
    for (const t of TIME_OPTIONS) {
      const op = document.createElement("option");
      op.value = t;
      op.textContent = t;
      enSel.appendChild(op);
    }

    // 기본값: 08:00~16:00
    stSel.value = "08:00";
    enSel.value = "16:00";

    workGridEl.appendChild(dayLabel);
    workGridEl.appendChild(stSel);
    workGridEl.appendChild(enSel);
  }
}

function validateDayWindowsUI(maxDays) {
  const bulkOn = !!useBulkWorkTimeEl?.checked;

  if (bulkOn) {
    const st = bulkWorkStartEl?.value;
    const en = bulkWorkEndEl?.value;
    const pst = parseHHMM(st);
    const pen = parseHHMM(en);
    if (!pst || !pen) return { ok: false, message: "근무시간(일괄) 시작/끝 시간이 올바르지 않습니다." };
    if (pen.totalMin <= pst.totalMin) return { ok: false, message: "근무시간(일괄) 끝 시간은 시작 시간보다 뒤여야 합니다." };
    return { ok: true };
  }

  for (let day = 1; day <= maxDays; day++) {
    const st = document.getElementById(`day${day}_start`).value;
    const en = document.getElementById(`day${day}_end`).value;
    const pst = parseHHMM(st);
    const pen = parseHHMM(en);
    if (!pst || !pen) return { ok: false, message: `Day ${day} 시작/끝 시간이 올바르지 않습니다.` };
    if (pen.totalMin <= pst.totalMin) return { ok: false, message: `Day ${day} 끝 시간은 시작 시간보다 뒤여야 합니다.` };
  }
  return { ok: true };
}

function collectDayWindowsJson(maxDays) {
  const bulkOn = !!useBulkWorkTimeEl?.checked;
  const arr = [];

  if (bulkOn) {
    const st = bulkWorkStartEl?.value || "";
    const en = bulkWorkEndEl?.value || "";
    for (let day = 1; day <= maxDays; day++) {
      arr.push({ start: st, end: en });
    }
    return arr;
  }

  for (let day = 1; day <= maxDays; day++) {
    const stEl = document.getElementById(`day${day}_start`);
    const enEl = document.getElementById(`day${day}_end`);
    arr.push({ start: stEl ? stEl.value : "", end: enEl ? enEl.value : "" });
  }
  return arr;
}

function syncBulkInspectUI() {
  const on = !!useBulkInspectEl.checked;
  bulkInspectMinEl.disabled = !on;
  // per-bridge UI는 initMapAndBind 안에서 BRIDGES/SELECTED 기반으로 갱신
}

function renderPerBridgeInspectUI(BRIDGES, SELECTED) {
  if (!perBridgeInspectCardEl || !perBridgeInspectBoxEl) return;

  const bulkOn = !!useBulkInspectEl.checked;
  perBridgeInspectCardEl.style.display = bulkOn ? "none" : "block";
  if (bulkOn) return;

  const selectedIds = Array.from(SELECTED).map(Number).filter(Number.isFinite);

  perBridgeInspectBoxEl.innerHTML = "";

  for (const id of selectedIds) {
    const b = (BRIDGES || []).find(x => Number(x.bridge_id) === id);
    if (!b) continue;

    const row = document.createElement("div");
    row.className = "subrow";
    row.style.alignItems = "center";
    row.style.gap = "10px";
    row.style.marginTop = "6px";

    const title = document.createElement("div");
    title.style.flex = "1";
    title.innerHTML =
      `<b>${escapeHtml(b.bridge_name || "-")}</b> ` +
      ` <span class="muted">(${escapeHtml(b.office || "")})</span>` +
      `<div class="hint muted" style="margin-top:2px;">${escapeHtml(b.address || "")}</div>`;

    const inp = document.createElement("input");
    inp.type = "number";
    inp.min = "1";
    inp.step = "1";
    inp.style.width = "110px";
    inp.id = `inspect_${id}`;

    // 초기값: DB inspect_min, 없거나(비정상)면 60
    const dbMin = Number(b.inspect_min);
    const initMin = (Number.isFinite(dbMin) && dbMin > 0) ? Math.floor(dbMin) : 60;
    inp.value = String(initMin);

    row.appendChild(title);
    row.appendChild(inp);
    perBridgeInspectBoxEl.appendChild(row);
  }
}

function collectInspectOverrides(SELECTED) {
  const selectedIds = Array.from(SELECTED).map(Number).filter(Number.isFinite);
  const out = {}; // { "bridge_id": minutes }

  for (const id of selectedIds) {
    const el = document.getElementById(`inspect_${id}`);
    if (!el) continue;

    const v = Number(el.value);
    if (!Number.isFinite(v) || v <= 0) {
      throw new Error(`교량별 점검시간이 올바르지 않습니다(bridge_id=${id}).`);
    }
    out[String(id)] = Math.floor(v);
  }
  return out;
}

// ✅ 신규: 필수 점검/마감 Day UI 렌더
function renderPerBridgeMandatoryUI(BRIDGES, SELECTED, maxDays) {
  if (!perBridgeMandatoryBoxEl) return;

  const selectedIds = Array.from(SELECTED).map(Number).filter(Number.isFinite);
  perBridgeMandatoryBoxEl.innerHTML = "";

  if (selectedIds.length === 0) {
    perBridgeMandatoryBoxEl.innerHTML = `<div class="hint muted">선택된 교량이 없습니다.</div>`;
    return;
  }

  for (const id of selectedIds) {
    const b = (BRIDGES || []).find(x => Number(x.bridge_id) === id);
    if (!b) continue;

    const row = document.createElement("div");
    row.className = "mandRow";

    const left = document.createElement("div");
    left.className = "mandLeft";

    const title = document.createElement("div");
    title.className = "mandTitle";
    title.innerHTML = `${escapeHtml(b.bridge_name || "-")} <span class="muted">(${escapeHtml(b.office || "")})</span>`;

    const sub = document.createElement("div");
    sub.className = "mandSub";
    sub.textContent = String(b.address || "").trim();

    left.appendChild(title);
    left.appendChild(sub);

    const right = document.createElement("div");
    right.className = "mandRight";

    const chkLabel = document.createElement("label");
    chkLabel.className = "hint";
    chkLabel.style.fontWeight = "900";

    const chk = document.createElement("input");
    chk.type = "checkbox";
    chk.id = `mandatory_${id}`;

    const chkTxt = document.createElement("span");
    chkTxt.textContent = "필수";

    chkLabel.appendChild(chk);
    chkLabel.appendChild(chkTxt);

    const deadlineLabel = document.createElement("label");
    deadlineLabel.className = "hint";
    deadlineLabel.style.fontWeight = "900";
    deadlineLabel.textContent = "마감 Day:";

    const sel = document.createElement("select");
    sel.id = `deadline_${id}`;
    for (let d = 1; d <= Math.max(1, Number(maxDays || 1)); d++) {
      const op = document.createElement("option");
      op.value = String(d);
      op.textContent = `Day ${d}`;
      sel.appendChild(op);
    }
    sel.value = "1";
    sel.disabled = true;

    // 기존 값 유지(사용자가 tripDays 변경/리렌더해도 값 유지)
    // - 숨겨진 input에 저장해두면 이상적이지만, 간단히 localStorage도 부담이라
    //   DOM이 존재하는 동안에는 값을 유지하고, 리렌더 시에는 이전 DOM에서 읽어와 반영
    const oldChk = document.getElementById(`mandatory_${id}`);
    const oldSel = document.getElementById(`deadline_${id}`);
    if (oldChk && oldSel) {
      const wasOn = !!oldChk.checked;
      const wasVal = String(oldSel.value || "1");
      chk.checked = wasOn;
      sel.disabled = !wasOn;
      if (wasVal) {
        const vv = Math.max(1, Math.min(Number(maxDays || 1), Number(wasVal) || 1));
        sel.value = String(vv);
      }
    }

    chk.addEventListener("change", () => {
      sel.disabled = !chk.checked;
      if (chk.checked) {
        // 켜면 기본은 현재 선택된 값 유지, 없으면 1
        if (!sel.value) sel.value = "1";
      }
    });

    const pill = document.createElement("span");
    pill.className = "mandPill";
    pill.textContent = `ID ${id}`;

    right.appendChild(chkLabel);
    right.appendChild(deadlineLabel);
    right.appendChild(sel);
    right.appendChild(pill);

    row.appendChild(left);
    row.appendChild(right);

    perBridgeMandatoryBoxEl.appendChild(row);
  }
}

// ✅ 신규: mandatory_rules 수집
function collectMandatoryRules(SELECTED, maxDays) {
  const selectedIds = Array.from(SELECTED).map(Number).filter(Number.isFinite);
  const out = {}; // { "bridge_id": { required: true/false, deadline_day: int|null } }

  for (const id of selectedIds) {
    const chk = document.getElementById(`mandatory_${id}`);
    const sel = document.getElementById(`deadline_${id}`);

    const required = !!chk?.checked;
    let deadlineDay = null;

    if (required) {
      const v = Number(sel?.value);
      if (!Number.isFinite(v)) throw new Error(`마감 Day 값이 올바르지 않습니다(bridge_id=${id}).`);
      const dd = Math.floor(v);
      if (dd < 1 || dd > Math.max(1, Number(maxDays || 1))) {
        throw new Error(`마감 Day 범위가 올바르지 않습니다(bridge_id=${id}).`);
      }
      deadlineDay = dd;
    }

    out[String(id)] = { required: !!required, deadline_day: deadlineDay };
  }
  return out;
}

useBulkInspectEl.addEventListener("change", syncBulkInspectUI);

async function geocodeAddress(address) {
  const url = `/api/geocode?query=${encodeURIComponent(address)}`;
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error || `geocode failed: ${res.status}`);
  return data;
}

async function runOptimizeSelected(depotAddress, selectedBridgeIds, options) {
  const body = {
    depot_address: depotAddress,
    selected_bridge_ids: selectedBridgeIds, // number[]
    day_windows_json: options.dayWindowsJson, // array
    day_limit_total_min: 480,
    day_limit_move_min: 240,

    use_bulk_inspect: options.useBulkInspect,
    bulk_inspect_min: options.useBulkInspect ? Number(options.bulkInspectMin) : null,

    use_route_cache: options.useRouteCache,
    route_cache_path: options.useRouteCache ? (options.routeCachePath || "") : null,

    inspect_overrides: (!options.useBulkInspect ? (options.inspectOverrides || {}) : null),

    // ✅ 신규: 필수/마감 규칙
    mandatory_rules: options.mandatoryRules || {},

    // 선택 옵션들
    routing_mode: "real_matrix",
    do_two_opt: true,
    multistart_iters: 60,
    rnn_k: 3,
    seed: 42,
    approx_avg_kmh: 30.0,
    max_days: Number(options.maxDays)
  };

  if (!body.route_cache_path) delete body.route_cache_path;

  const res = await fetch("/api/optimize_selected", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error || `optimize_selected failed: ${res.status}`);
  return data;
}

function dayColor(dayIdx) {
  const d = Number(dayIdx);
  if (d === 1) return "#2563eb";
  if (d === 2) return "#dc2626";
  if (d === 3) return "#16a34a";
  const palette = ["#7c3aed", "#ea580c", "#0891b2", "#db2777", "#65a30d", "#0f766e", "#a16207", "#4f46e5", "#be123c"];
  return palette[(Math.max(d, 4) - 4) % palette.length];
}

function updateLegend(days, startDateStr, unscheduledCount) {
  const base = parseDateYYYYMMDD(startDateStr);
  const n = (days || []).length;

  if (!n) {
    legendEl.style.display = "none";
    legendItemsEl.innerHTML = "";
    legendFooterEl.textContent = "";
    return;
  }

  legendItemsEl.innerHTML = "";
  for (const d of days) {
    const dayNum = Number(d.day);
    const dt = base ? addDays(base, dayNum - 1) : null;
    const dateTxt = dt ? fmtDate(dt) : "";
    const color = dayColor(dayNum);

    const st = (d && d.start_time) ? String(d.start_time) : "";
    const en = (d && d.end_time) ? String(d.end_time) : "";

    const item = document.createElement("div");
    item.className = "item";

    const sw = document.createElement("div");
    sw.className = "swatch";
    sw.style.background = color;

    const label = document.createElement("div");
    label.textContent = `Day ${dayNum} (${dateTxt}) ${st && en ? `· ${st}~${en}` : ""}`;

    item.appendChild(sw);
    item.appendChild(label);
    legendItemsEl.appendChild(item);
  }

  const nights = Math.max(0, n - 1);
  const unsTxt = (Number(unscheduledCount || 0) > 0) ? ` · 미배정 ${unscheduledCount}개` : "";
  legendFooterEl.textContent = `총 ${nights}박 ${n}일${unsTxt}`;

  legendEl.style.display = "block";
}

function calcDayTotals(dayObj) {
  const edges = dayObj?.edges || [];
  const order = dayObj?.order || [];
  const move = edges.reduce((acc, e) => acc + (Number(e?.duration_min) || 0), 0);
  const inspect = order.reduce((acc, b) => acc + (Number(b?.inspect_min) || 0), 0);
  const total = move + inspect;
  return { move, inspect, total };
}

function renderScheduleHtml(apiResult, startDateStr) {
  const schedule = apiResult.schedule || {};
  const depot = apiResult.depot || {};
  const baseDate = parseDateYYYYMMDD(startDateStr);
  const days = schedule.days || [];

  const unscheduled = schedule.unscheduled || apiResult.unscheduled || [];
  const unsCount = (unscheduled || []).length;

  const safe = escapeHtml;

  // ✅ 서버가 필수/마감 위반 정보를 주면 상단에 표시(서버 수정 후 자동으로 보임)
  const mandMeta = schedule.mandatory_meta || apiResult.mandatory_meta || null;

  if (!days.length) {
    let msg = `<div class="hint">(배정된 일정이 없습니다)</div>`;
    if (mandMeta && mandMeta.required_missing_count > 0) {
      msg += `<div class="hint" style="margin-top:8px;color:#b91c1c;"><b>필수 점검 미배정 ${safe(mandMeta.required_missing_count)}개</b></div>`;
      msg += `<div class="hint" style="margin-top:6px;color:#b91c1c;line-height:1.4;">
                조건을 만족하는 경로가 없습니다.<br>
                마감일 조건 대비 근무시간이 부족하여 일부 교량이 미배정되었습니다.<br>
                근무시간 또는 일정 조건을 조정한 뒤 다시 실행해 주세요.
              </div>`;
    }
    if (unsCount > 0) {
      msg += `<div style="margin-top:10px;"><b>미배정 ${safe(unsCount)}개</b></div>`;
    }
    return msg;
  }

  let html = "";

  html += `<div class="resultTop">`;
  html += `<div class="resultTopTitle">0. 사무실</div>`;
  html += `<div class="resultTopSub">${safe(depot.address || "-")}</div>`;
  html += `<div class="resultTopSub">총 이동 ${safe(schedule.total_move_min ?? 0)}분 · 총 점검 ${safe(schedule.total_inspect_min ?? 0)}분 · 총합 ${safe(schedule.total_min ?? 0)}분</div>`;

  if (mandMeta) {
    const miss = Number(mandMeta.required_missing_count || 0) || 0;
    const late = Number(mandMeta.deadline_violations_count || 0) || 0;
    if (miss > 0 || late > 0) {
      html += `<div class="resultTopSub"><b style="color:#b91c1c;">필수/마감 경고: 미배정 ${safe(miss)}개 · 마감위반 ${safe(late)}개</b></div>`;
    }
  }

  if (unsCount > 0) {
    html += `<div class="resultTopSub"><b style="color:#6b7280;">미배정 ${safe(unsCount)}개</b></div>`;
  }
  html += `</div>`;

  let globalIdx = 1;

  for (let di = 0; di < days.length; di++) {
    const d = days[di];
    const dayNum = Number(d.day);
    const dayDate = baseDate ? addDays(baseDate, dayNum - 1) : null;
    const color = dayColor(dayNum);

    const { move, inspect, total } = calcDayTotals(d);
    const title = `Day ${dayNum} - ${dayDate ? fmtDate(dayDate) : ""}`.trim();

    const stTxt = String(d.start_time || "");
    const enTxt = String(d.end_time || "");
    const timeBadge = (stTxt && enTxt) ? `<span class="badge">${safe(stTxt)}~${safe(enTxt)}</span>` : "";

    html += `
      <div class="dayHeader">
        <div class="dayHeaderLeft" style="color:${safe(color)}">[${safe(title)}] ${timeBadge}</div>
        <div class="dayHeaderRight">(총 이동 ${safe(move)}분 · 총 점검 ${safe(inspect)}분 · 총 ${safe(total)}분)</div>
      </div>
    `;

    const order = d.order || [];
    const edges = d.edges || [];

    // Day별 시작시각 반영
    let t = null;
    if (dayDate) {
      const parsed = parseHHMM(d.start_time || "");
      if (parsed) t = withTime(dayDate, parsed.hh, parsed.mm);
    }

    for (let i = 0; i < order.length; i++) {
      const b = order[i] || {};
      const moveMin = Number(edges?.[i]?.duration_min ?? 0) || 0;
      const inspMin = Number(b.inspect_min ?? 0) || 0;

      let arriveStr = "-";
      let finishStr = "-";
      if (t) {
        t = addMinutes(t, moveMin);
        arriveStr = fmtTime(t);
        t = addMinutes(t, inspMin);
        finishStr = fmtTime(t);
      }

      const bridgeName = safe(b.bridge_name || "-");
      const addr = String(b.address || "").trim();
      const addrPart = addr ? ` <span class="muted">(${safe(addr)})</span>` : "";

      // 서버가 required/deadline 정보를 내려주면 표시 가능(서버 수정 후 자동)
      const reqBadge = b.required ? `<span class="badge" style="background:#fff7ed;color:#9a3412;border-color:#fed7aa;">필수</span>` : "";
      const dlBadge = Number.isFinite(Number(b.deadline_day)) ? `<span class="badge" style="background:#f0f9ff;color:#075985;border-color:#bae6fd;">마감 Day ${safe(b.deadline_day)}</span>` : "";

      html += `<div class="step">`;
      html += `<div class="stepTitle"><span class="idx">${globalIdx}.</span>${bridgeName}${addrPart} ${reqBadge} ${dlBadge}</div>`;
      html += `<div class="stepSub">(도착 ${safe(arriveStr)} ~ 완료 ${safe(finishStr)} | 이동 ${safe(moveMin)}분 | 점검 ${safe(inspMin)}분)</div>`;
      html += `<div class="stepDivider"></div>`;
      html += `</div>`;

      globalIdx += 1;
    }
  }

  // 마지막 "사무실(도착)" (기존 유지)
  if (schedule.return_to_depot) {
    const ret = schedule.return_to_depot;
    const moveMin = Number(ret.duration_min ?? 0) || 0;

    const lastDay = days[days.length - 1];
    const lastDayNum = Number(lastDay.day);
    const lastDate = baseDate ? addDays(baseDate, lastDayNum - 1) : null;

    let t = null;
    if (lastDate) {
      const parsed = parseHHMM(lastDay.start_time || "");
      if (parsed) t = withTime(lastDate, parsed.hh, parsed.mm);
    }

    if (t) {
      const edges = lastDay.edges || [];
      const order = lastDay.order || [];
      for (let i = 0; i < order.length; i++) {
        const mv = Number(edges?.[i]?.duration_min ?? 0) || 0;
        const ins = Number(order[i]?.inspect_min ?? 0) || 0;
        t = addMinutes(t, mv);
        t = addMinutes(t, ins);
      }
      t = addMinutes(t, moveMin);
    }

    const arriveStr = t ? fmtTime(t) : "-";

    html += `<div class="step">`;
    html += `<div class="stepTitle"><span class="idx">${globalIdx}.</span>사무실 (도착)</div>`;
    html += `<div class="stepSub">(도착 ${safe(arriveStr)} | 이동 ${safe(moveMin)}분)</div>`;
    html += `</div>`;
  }

  // 미배정 리스트
  if (unsCount > 0) {
    html += `<div style="margin-top:16px; padding-top:10px; border-top:1px solid #e5e7eb;">`;
    html += `<div style="font-weight:900; color:#6b7280;">미배정 (${safe(unsCount)}개)</div>`;
    html += `<div class="hint" style="margin-top:6px;">※ 출장 내에 배정되지 못한 교량입니다.</div>`;

    for (let i = 0; i < unscheduled.length; i++) {
      const b = unscheduled[i] || {};
      const nm = safe(b.bridge_name || "-");
      const ad = safe(b.address || "");
      const ins = safe(b.inspect_min ?? "-");
      const req = b.required ? " · 필수" : "";
      const dl = Number.isFinite(Number(b.deadline_day)) ? ` · 마감 Day ${safe(b.deadline_day)}` : "";
      html += `<div class="step">`;
      html += `<div class="stepTitle"><span class="idx">-</span>${nm} <span class="muted">(${ad})</span></div>`;
      html += `<div class="stepSub">(점검 ${ins}분${req}${dl})</div>`;
      html += `<div class="stepDivider"></div>`;
      html += `</div>`;
    }
    html += `</div>`;
  }

  return html;
}

function initMapAndBind() {
  let BRIDGES = [];           // /api/bridges items
  const SELECTED = new Set(); // bridge_id numbers
  let LAST_RESULT = null;
  let LAST_START_DATE = "";

  function updateSelectedCount() {
    if (selectedCountTextEl) selectedCountTextEl.textContent = `선택 ${SELECTED.size}개`;
  }

  function renderBridgeList() {
    if (!bridgeListEl) return;

    const office = (officeFilterEl?.value || "").trim();
    const q = (bridgeSearchEl?.value || "").trim().toLowerCase();

    const filtered = (BRIDGES || []).filter(b => {
      if (office && String(b.office || "") !== office) return false;
      if (!q) return true;
      const hay = `${b.bridge_name || ""} ${b.address || ""}`.toLowerCase();
      return hay.includes(q);
    });

    bridgeListEl.innerHTML = "";

    for (const b of filtered) {
      const bid = Number(b.bridge_id);
      if (!Number.isFinite(bid)) continue;

      const row = document.createElement("label");
      row.style.display = "block";
      row.style.padding = "6px 4px";
      row.style.borderBottom = "1px solid #f3f4f6";
      row.style.cursor = "pointer";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = SELECTED.has(bid);
      cb.addEventListener("change", () => {
        if (cb.checked) SELECTED.add(bid);
        else SELECTED.delete(bid);
        updateSelectedCount();
        // ✅ 선택 변경 시 필수/마감 UI도 갱신
        renderPerBridgeInspectUI(BRIDGES, SELECTED);
        renderPerBridgeMandatoryUI(BRIDGES, SELECTED, getMaxDays());
      });

      const title = document.createElement("span");
      title.style.marginLeft = "8px";
      title.innerHTML =
        `<b>${escapeHtml(b.bridge_name || "-")}</b>` +
        ` <span class="muted">(${escapeHtml(b.office || "")})</span>` +
        `<div class="hint muted" style="margin-top:2px;">${escapeHtml(b.address || "")}</div>`;

      row.appendChild(cb);
      row.appendChild(title);
      bridgeListEl.appendChild(row);
    }

    updateSelectedCount();
  }

  async function loadOfficesAndBridges() {
    // offices
    if (officeFilterEl) {
      const r1 = await fetch("/api/offices");
      const d1 = await r1.json();
      const offices = d1.items || [];
      for (const o of offices) {
        const op = document.createElement("option");
        op.value = o;
        op.textContent = o;
        officeFilterEl.appendChild(op);
      }
    }

    // bridges
    const r2 = await fetch("/api/bridges");
    const d2 = await r2.json();
    BRIDGES = d2.items || [];
    renderBridgeList();
    renderPerBridgeInspectUI(BRIDGES, SELECTED);
    renderPerBridgeMandatoryUI(BRIDGES, SELECTED, getMaxDays());
  }

  if (!window.kakao || !kakao.maps) {
    statusEl.textContent = "카카오 지도 SDK 로드 실패: appkey 확인 필요";
    return;
  }

  officeFilterEl?.addEventListener("change", renderBridgeList);
  bridgeSearchEl?.addEventListener("input", renderBridgeList);

  selectAllBridgesBtn?.addEventListener("click", () => {
    const office = (officeFilterEl?.value || "").trim();
    const q = (bridgeSearchEl?.value || "").trim().toLowerCase();

    for (const b of (BRIDGES || [])) {
      const bid = Number(b.bridge_id);
      if (!Number.isFinite(bid)) continue;

      if (office && String(b.office || "") !== office) continue;
      if (q) {
        const hay = `${b.bridge_name || ""} ${b.address || ""}`.toLowerCase();
        if (!hay.includes(q)) continue;
      }
      SELECTED.add(bid);
    }
    renderBridgeList();
    renderPerBridgeInspectUI(BRIDGES, SELECTED);
    renderPerBridgeMandatoryUI(BRIDGES, SELECTED, getMaxDays());
  });

  clearSelectedBridgesBtn?.addEventListener("click", () => {
    SELECTED.clear();
    renderBridgeList();
    renderPerBridgeInspectUI(BRIDGES, SELECTED);
    renderPerBridgeMandatoryUI(BRIDGES, SELECTED, getMaxDays());
    statusEl.textContent = "선택해제 완료";
  });

  useBulkInspectEl?.addEventListener("change", () => {
    renderPerBridgeInspectUI(BRIDGES, SELECTED);
  });

  document.getElementById("backToSelect")?.addEventListener("click", () => {
    if (optionsPanelEl) optionsPanelEl.style.display = "none";
    if (resultPanelEl) resultPanelEl.style.display = "none";
    if (selectPanelEl) selectPanelEl.style.display = "block";
    if (selectPanelEl) selectPanelEl.scrollTop = 0;
    relayoutMapSoon();
  });

  goHomeBtn?.addEventListener("click", () => {
    if (!confirm("처음으로 돌아가면 선택/결과/지도 표시가 초기화됩니다. 진행할까요?")) return;

    SELECTED.clear();
    renderBridgeList();

    LAST_RESULT = null;
    LAST_START_DATE = "";
    resultEl.innerHTML = "-";

    clearMapGraphics();
    clearPreviewGraphics();

    if (resultPanelEl) resultPanelEl.style.display = "none";
    if (optionsPanelEl) optionsPanelEl.style.display = "none";
    if (selectPanelEl) selectPanelEl.style.display = "block";
    if (selectPanelEl) selectPanelEl.scrollTop = 0;

    statusEl.textContent = "초기화 완료. 점검 대상을 다시 선택하세요.";

    relayoutMapSoon(() => {
      map.setCenter(new kakao.maps.LatLng(37.5665, 126.9780));
      map.setLevel(7);
    });
  });

  function downloadTextFile(filename, text, mime = "text/plain;charset=utf-8") {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function buildHtmlReport({ title, generatedAt, startDate, depotAddress, resultInnerHtml }) {
    const safeTitle = escapeHtml(title || "최적화 결과");
    const safeDepot = escapeHtml(depotAddress || "-");
    const safeStart = escapeHtml(startDate || "-");
    const safeGen = escapeHtml(generatedAt || "-");

    return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${safeTitle}</title>
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;margin:0;background:#f8fafc;color:#111827}
    .wrap{max-width:900px;margin:0 auto;padding:16px}
    .card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden}
    .header{padding:14px 16px;border-bottom:1px solid #e5e7eb}
    .header h1{margin:0;font-size:18px}
    .meta{margin-top:6px;font-size:13px;color:#6b7280;line-height:1.5}
    .content{padding:12px 16px}
    .resultTop{padding:12px 0;border-bottom:1px solid #e5e7eb;margin-bottom:10px}
    .resultTopTitle{font-weight:900;margin-bottom:4px}
    .resultTopSub{color:#374151;font-size:14px;margin-top:2px}
    .dayHeader{display:flex;justify-content:space-between;gap:12px;align-items:flex-end;margin-top:14px;padding-top:10px;border-top:1px solid #eef2f7}
    .dayHeaderLeft{font-weight:900}
    .dayHeaderRight{color:#6b7280;font-size:13px;white-space:nowrap}
    .badge{display:inline-block;margin-left:8px;padding:2px 8px;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:12px;font-weight:700}
    .step{padding:8px 0}
    .stepTitle{font-weight:800}
    .idx{display:inline-block;min-width:28px;color:#6b7280}
    .stepSub{color:#6b7280;font-size:13px;margin-top:2px}
    .muted{color:#6b7280}
    .hint{color:#6b7280;font-size:13px}
    .stepDivider{height:1px;background:#f1f5f9;margin-top:8px}
    @media (max-width: 520px){
      .wrap{padding:12px}
      .dayHeader{flex-direction:column;align-items:flex-start}
      .dayHeaderRight{white-space:normal}
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="header">
        <h1>${safeTitle}</h1>
        <div class="meta">
          생성: ${safeGen}<br/>
          시작일(Day1): ${safeStart}<br/>
          사무실: ${safeDepot}
        </div>
      </div>
      <div class="content">
        ${resultInnerHtml || "-"}
      </div>
    </div>
  </div>
</body>
</html>`;
  }

  saveResultBtn?.addEventListener("click", () => {
    if (!LAST_RESULT) {
      alert("저장할 결과가 없습니다. 먼저 '일정 최적화 실행'을 완료하세요.");
      return;
    }

    const depotAddress = LAST_RESULT?.depot?.address || "";
    const generatedAt = new Date().toLocaleString("ko-KR");
    const title = "와따가다리 최적화 결과";

    const html = buildHtmlReport({
      title,
      generatedAt,
      startDate: LAST_START_DATE,
      depotAddress,
      resultInnerHtml: resultEl?.innerHTML || "-"
    });

    const stamp = new Date();
    const y = stamp.getFullYear();
    const mo = pad2(stamp.getMonth() + 1);
    const d = pad2(stamp.getDate());
    const hh = pad2(stamp.getHours());
    const mm = pad2(stamp.getMinutes());

    const filename = `opt_report_${y}${mo}${d}_${hh}${mm}.html`;
    downloadTextFile(filename, html, "text/html;charset=utf-8");
  });

  const map = new kakao.maps.Map(document.getElementById("map"), {
    center: new kakao.maps.LatLng(37.5665, 126.9780),
    level: 7
  });

  function relayoutMapSoon(fitBounds) {
    requestAnimationFrame(() => {
      map.relayout();
      requestAnimationFrame(() => {
        map.relayout();
        if (fitBounds && typeof fitBounds === "function") fitBounds();
      });
    });
  }

  const markers = [];
  const overlays = [];
  const bubbles = [];
  const polylines = [];
  let bounds = new kakao.maps.LatLngBounds();
  const previewMarkers = [];
  const previewOverlays = [];
  let previewBounds = new kakao.maps.LatLngBounds();

  function clearPreviewGraphics() {
    for (const m of previewMarkers) m.setMap(null);
    for (const ov of previewOverlays) ov.setMap(null);
    previewMarkers.length = 0;
    previewOverlays.length = 0;
  }

  function previewSelectedOnMap() {
    clearPreviewGraphics();
    previewBounds = new kakao.maps.LatLngBounds();

    const selectedIds = Array.from(SELECTED).map(Number).filter(Number.isFinite);
    if (selectedIds.length === 0) {
      statusEl.textContent = "선택된 교량이 없습니다.";
      return;
    }

    let ok = 0;
    for (const id of selectedIds) {
      const b = (BRIDGES || []).find(x => Number(x.bridge_id) === id);
      if (!b) continue;

      const lat = Number(b.lat);
      const lng = Number(b.lng);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;

      const pos = new kakao.maps.LatLng(lat, lng);
      previewBounds.extend(pos);

      const marker = new kakao.maps.Marker({ map, position: pos });
      previewMarkers.push(marker);

      const el = document.createElement("div");
      el.className = "numMarker numMarkerSmall numMarkerGray";
      el.textContent = String(++ok);

      const overlay = new kakao.maps.CustomOverlay({
        position: pos,
        content: el,
        yAnchor: 1.05,
        zIndex: 3
      });
      overlay.setMap(map);
      previewOverlays.push(overlay);
    }

    if (ok > 0) {
      map.setBounds(previewBounds);
      statusEl.textContent = `선택 교량 미리보기: ${ok}개 마커 표시`;
    } else {
      statusEl.textContent = "선택 교량에 좌표(lat/lng)가 없어 미리보기 표시를 할 수 없습니다.";
    }
  }

  applySelectionBtn?.addEventListener("click", () => {
    if (SELECTED.size === 0) {
      alert("DB 교량 목록에서 점검 대상을 선택하세요.");
      return;
    }

    if (selectPanelEl) selectPanelEl.style.display = "none";
    if (optionsPanelEl) optionsPanelEl.style.display = "block";
    if (resultPanelEl) resultPanelEl.style.display = "none";
    if (optionsPanelEl) optionsPanelEl.scrollTop = 0;

    buildDayWorkTimeUI(getMaxDays());
    renderPerBridgeInspectUI(BRIDGES, SELECTED);
    renderPerBridgeMandatoryUI(BRIDGES, SELECTED, getMaxDays());

    relayoutMapSoon(() => {
      previewSelectedOnMap();
    });
  });

  window.addEventListener("resize", () => {
    map.relayout();
  });

  function closeAllBubbles() {
    for (const b of bubbles) b.setMap(null);
  }

  kakao.maps.event.addListener(map, "click", () => {
    closeAllBubbles();
  });

  function createBubbleOverlay(position, html) {
    const el = document.createElement("div");
    el.className = "bubble";
    el.innerHTML = html;

    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
    });

    return new kakao.maps.CustomOverlay({
      position,
      content: el,
      yAnchor: 1.18,
      xAnchor: 0.0,
      zIndex: 999
    });
  }

  function toggleBubble(bubble) {
    if (bubble.getMap()) {
      bubble.setMap(null);
      return;
    }
    closeAllBubbles();
    bubble.setMap(map);
  }

  function clearMapGraphics() {
    for (const m of markers) m.setMap(null);
    for (const ov of overlays) ov.setMap(null);
    for (const b of bubbles) b.setMap(null);
    for (const pl of polylines) pl.setMap(null);

    markers.length = 0;
    overlays.length = 0;
    bubbles.length = 0;
    polylines.length = 0;

    legendEl.style.display = "none";
    legendItemsEl.innerHTML = "";
    legendFooterEl.textContent = "";
  }

  clearBtn.addEventListener("click", () => location.reload());

  function addInfoMarker(lat, lng, labelHtml) {
    const pos = new kakao.maps.LatLng(lat, lng);
    bounds.extend(pos);

    const marker = new kakao.maps.Marker({ map, position: pos });
    const bubble = createBubbleOverlay(pos, labelHtml);

    kakao.maps.event.addListener(marker, "click", () => {
      toggleBubble(bubble);
    });

    markers.push(marker);
    bubbles.push(bubble);
  }

  function addNumberOverlay(lat, lng, numberText, bgColor, onClick, classNameExtra) {
    const pos = new kakao.maps.LatLng(lat, lng);
    bounds.extend(pos);

    const el = document.createElement("div");
    el.className = "numMarker numMarkerSmall" + (classNameExtra ? (" " + classNameExtra) : "");
    el.style.background = bgColor;
    el.textContent = String(numberText);
    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (typeof onClick === "function") onClick();
    });

    const overlay = new kakao.maps.CustomOverlay({
      position: pos,
      content: el,
      yAnchor: 1.05,
      zIndex: 5
    });
    overlay.setMap(map);
    overlays.push(overlay);
  }

  function addPolylineFromPath(pathLatLngArray, strokeColor, zIndex, strokeWeight = 5, strokeOpacity = 0.9, strokeStyle = "solid") {
    if (!Array.isArray(pathLatLngArray) || pathLatLngArray.length < 2) return;

    const linePath = [];
    for (const p of pathLatLngArray) {
      if (!Array.isArray(p) || p.length < 2) continue;
      const lat = Number(p[0]);
      const lng = Number(p[1]);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
      const ll = new kakao.maps.LatLng(lat, lng);
      linePath.push(ll);
      bounds.extend(ll);
    }
    if (linePath.length < 2) return;

    const pl = new kakao.maps.Polyline({
      map,
      path: linePath,
      strokeWeight,
      strokeColor,
      strokeOpacity,
      strokeStyle
    });

    if (Number.isFinite(zIndex)) pl.setZIndex(zIndex);
    polylines.push(pl);
  }

  function syncCacheUi() {
    const on = !!useRouteCacheEl.checked;
    routeCachePathEl.disabled = !on;
    cacheLabelTextEl.textContent = on ? "route_cache 사용(ON)" : "route_cache 사용(OFF)";
    statusEl.textContent = on
      ? "캐시 ON: route_cache를 읽고/쓰며, 있으면 재사용합니다."
      : "캐시 OFF: 캐시를 읽지도/쓰지도 않으며, 항상 API를 새로 호출합니다.";
  }
  useRouteCacheEl.addEventListener("change", syncCacheUi);

  // 초기 UI 구성
  buildDayWorkTimeUI(getMaxDays());
  syncCacheUi();
  syncBulkInspectUI();

  function syncBulkWorkTimeUI() {
    const on = !!useBulkWorkTimeEl?.checked;
    if (bulkWorkTimeBoxEl) bulkWorkTimeBoxEl.style.display = on ? "flex" : "none";
    if (workGridEl) workGridEl.style.display = on ? "none" : "grid";
  }

  useBulkWorkTimeEl?.addEventListener("change", syncBulkWorkTimeUI);

  fillSelectWithTimes(bulkWorkStartEl, "08:00");
  fillSelectWithTimes(bulkWorkEndEl, "16:00");

  syncBulkWorkTimeUI();

  // 초기(선택 전)에는 비어있지만, 안전하게 호출
  renderPerBridgeInspectUI(BRIDGES, SELECTED);
  renderPerBridgeMandatoryUI(BRIDGES, SELECTED, getMaxDays());

  tripDaysEl?.addEventListener("change", () => {
    tripDaysEl.value = String(getMaxDays());
    buildDayWorkTimeUI(getMaxDays());
    // ✅ maxDays 변경 시 마감 Day 옵션 갱신
    renderPerBridgeMandatoryUI(BRIDGES, SELECTED, getMaxDays());
  });

  loadOfficesAndBridges().catch(err => {
    console.error(err);
    statusEl.textContent = "DB 교량 목록 로드 실패(/api/bridges 확인)";
  });

  const excelFileEl = document.getElementById("excelFile");
  excelFileEl?.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!window.XLSX) {
      statusEl.textContent = "XLSX 라이브러리 로드 실패(CDN 차단 여부 확인)";
      return;
    }

    statusEl.textContent = "엑셀(.xlsx) 읽는 중...";

    let arrayBuffer;
    try { arrayBuffer = await file.arrayBuffer(); }
    catch (err) { console.error(err); statusEl.textContent = "파일 읽기 실패"; return; }

    let rows = [];
    try {
      const wb = XLSX.read(arrayBuffer, { type: "array" });
      const firstSheetName = wb.SheetNames[0];
      const ws = wb.Sheets[firstSheetName];
      rows = XLSX.utils.sheet_to_json(ws, { defval: "", raw: false });
    } catch (err) {
      console.error(err);
      statusEl.textContent = "엑셀 파싱 실패 (파일 손상/형식 확인 필요)";
      return;
    }

    const norm = (s) => String(s ?? "").trim().toLowerCase();

    const targets = rows.map(r => {
      const keys = Object.keys(r);
      const getBy = (...cands) => {
        for (const c of cands) {
          const k = keys.find(x => norm(x) === norm(c));
          if (k) return r[k];
        }
        return "";
      };
      const name = getBy("bridge_name", "name", "교량명") || "교량";
      const address = getBy("address", "addr", "주소");
      return { name: String(name).trim(), address: String(address).trim() };
    }).filter(x => x.address);

    if (targets.length === 0) {
      statusEl.textContent = "엑셀에서 address(주소) 컬럼을 찾지 못했어요. 헤더를 확인해주세요.";
      return;
    }

    clearMapGraphics();
    statusEl.textContent = `총 ${targets.length}개 주소 지오코딩 중...`;

    let ok = 0, fail = 0;
    for (const t of targets) {
      try {
        const data = await geocodeAddress(t.address);
        const lat = Number(data.lat);
        const lng = Number(data.lng);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) throw new Error("invalid lat/lng from server");

        addInfoMarker(
          lat, lng,
          `<b>${escapeHtml(t.name)}</b><br/>${escapeHtml(t.address)}`
        );
        ok++;
      } catch (err) {
        console.error("지오코딩 실패:", t.address, err);
        fail++;
      }
      statusEl.textContent = `진행: 성공 ${ok}, 실패 ${fail} / ${targets.length}`;
    }

    if (ok > 0) map.setBounds(bounds);
    statusEl.textContent = `완료: 성공 ${ok}, 실패 ${fail} / ${targets.length}`;
  });

  optimizeBtn.addEventListener("click", async () => {
    const depot = (document.getElementById("depotAddress").value || "").trim();
    if (!depot) { alert("출발지 주소를 입력하세요."); return; }

    const selectedIds = Array.from(SELECTED).map(Number).filter(Number.isFinite);
    if (selectedIds.length === 0) {
      alert("DB 교량 목록에서 점검 대상을 선택하세요.");
      return;
    }

    const startDateStr = (startDateEl.value || "").trim();
    if (!parseDateYYYYMMDD(startDateStr)) {
      alert("시작 날짜(Day1)를 YYYY-MM-DD 형식으로 입력하세요.");
      return;
    }

    const maxDays = getMaxDays();

    const v = validateDayWindowsUI(maxDays);
    if (!v.ok) {
      alert(v.message || "Day별 근무시간 설정을 확인하세요.");
      return;
    }

    const useBulkInspect = !!useBulkInspectEl.checked;
    const bulkInspectMin = Number(bulkInspectMinEl.value);
    if (useBulkInspect) {
      if (!Number.isFinite(bulkInspectMin) || bulkInspectMin <= 0) {
        alert("일괄적용 점검시간(분)은 1 이상의 숫자여야 합니다.");
        return;
      }
    }

    // ✅ 신규: 필수/마감 규칙 수집
    let mandatoryRules = {};
    try {
      mandatoryRules = collectMandatoryRules(SELECTED, maxDays);
    } catch (e) {
      alert(e?.message || String(e));
      return;
    }

    const options = {
      maxDays,
      useRouteCache: !!useRouteCacheEl.checked,
      routeCachePath: (routeCachePathEl.value || "").trim(),
      dayWindowsJson: collectDayWindowsJson(maxDays),

      useBulkInspect,
      bulkInspectMin: Math.floor(bulkInspectMin || 0),

      // ✅ 추가
      mandatoryRules,
    };

    if (!options.useBulkInspect) {
      options.inspectOverrides = collectInspectOverrides(SELECTED);
    }

    optimizeBtn.disabled = true;
    statusEl.textContent = "최적화 실행 중...";
    resultEl.innerHTML = "-";

    try {
      const apiResult = await runOptimizeSelected(depot, selectedIds, options);

      LAST_RESULT = apiResult;
      LAST_START_DATE = startDateStr;

      const schedule = apiResult.schedule || {};
      const days = schedule.days || [];
      const unscheduled = schedule.unscheduled || apiResult.unscheduled || [];
      const unsCount = (unscheduled || []).length;

      resultEl.innerHTML = renderScheduleHtml(apiResult, startDateStr);

      clearMapGraphics();
      bounds = new kakao.maps.LatLngBounds();

      // depot
      addInfoMarker(
        Number(apiResult.depot.lat),
        Number(apiResult.depot.lng),
        `<b>DEPOT</b><br/>${escapeHtml(apiResult.depot.address)}`
      );

      // 범례
      updateLegend(days, startDateStr, unsCount);

      let globalIdx = 1;

      // 배정된 마커(번호 + Day색)
      for (const d of days) {
        const color = dayColor(d.day);

        (d.order || []).forEach((b, i) => {
          const lat = Number(b.lat);
          const lng = Number(b.lng);
          if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

          const pos = new kakao.maps.LatLng(lat, lng);
          bounds.extend(pos);

          // 투명 marker + bubble
          const marker = new kakao.maps.Marker({ map, position: pos, opacity: 0 });

          const labelHtml =
            `<b>#${escapeHtml(globalIdx)} (Day ${escapeHtml(d.day)} - ${escapeHtml(i + 1)})</b><br/>` +
            `<b>${escapeHtml(b.bridge_name)}</b><br/>` +
            `${escapeHtml(b.address)}<br/>` +
            `점검 ${escapeHtml(b.inspect_min)}분`;

          const bubble = createBubbleOverlay(pos, labelHtml);

          kakao.maps.event.addListener(marker, "click", () => {
            toggleBubble(bubble);
          });

          markers.push(marker);
          bubbles.push(bubble);

          addNumberOverlay(lat, lng, globalIdx, color, () => toggleBubble(bubble));

          globalIdx += 1;
        });
      }

      // 미배정 마커(회색)
      for (const b of (unscheduled || [])) {
        const lat = Number(b.lat);
        const lng = Number(b.lng);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;

        const pos = new kakao.maps.LatLng(lat, lng);
        bounds.extend(pos);

        const marker = new kakao.maps.Marker({ map, position: pos, opacity: 0 });

        const labelHtml =
          `<b>[미배정]</b><br/>` +
          `<b>${escapeHtml(b.bridge_name || "-")}</b><br/>` +
          `${escapeHtml(b.address || "")}<br/>` +
          `점검 ${escapeHtml(b.inspect_min ?? "-")}분`;

        const bubble = createBubbleOverlay(pos, labelHtml);

        kakao.maps.event.addListener(marker, "click", () => {
          toggleBubble(bubble);
        });

        markers.push(marker);
        bubbles.push(bubble);

        // 번호 대신 "U" 표시(unscheduled)
        addNumberOverlay(lat, lng, "U", "#6b7280", () => toggleBubble(bubble), "numMarkerGray");
      }

      // Day 폴리라인
      for (const d of days) {
        const color = dayColor(d.day);
        const z = 10 + Number(d.day || 0);
        for (const e of (d.edges || [])) {
          addPolylineFromPath(e.path, color, z, 5, 0.9, "solid");
        }
      }

      // 복귀 폴리라인(점선)
      if (schedule.return_to_depot && Array.isArray(schedule.return_to_depot.path) && schedule.return_to_depot.path.length >= 2) {
        const lastDayNum = Number(days?.[days.length - 1]?.day || 1);
        const returnColor = dayColor(lastDayNum);
        addPolylineFromPath(schedule.return_to_depot.path, returnColor, 999, 5, 0.95, "shortdash");
      }

      // 결과 화면 전환
      if (selectPanelEl) selectPanelEl.style.display = "none";
      if (optionsPanelEl) optionsPanelEl.style.display = "none";
      if (resultPanelEl) resultPanelEl.style.display = "block";

      relayoutMapSoon(() => {
        map.setBounds(bounds);
      });

      statusEl.textContent = "최적화 완료(경로 렌더링 완료)";
    } catch (err) {
      console.error(err);
      statusEl.textContent = `오류: ${err.message || err}`;
      alert(err.message || String(err));
    } finally {
      optimizeBtn.disabled = false;
    }
  });
}

initMapAndBind();
