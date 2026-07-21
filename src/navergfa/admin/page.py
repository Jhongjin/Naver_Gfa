"""운영자 콘솔 단일 페이지 UI (vanilla JS)."""

HTML_PAGE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Naver GFA 운영자 콘솔</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0; background: #f6f7f9; color: #1a1a1a; }
  header { background: #0b1f3a; color: #fff; padding: 12px 20px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  header h1 { font-size: 16px; margin: 0; margin-right: auto; }
  header input { padding: 6px 8px; border-radius: 6px; border: 1px solid #33507a; background: #fff; }
  button { cursor: pointer; border: 1px solid #cfd6e0; background: #fff; border-radius: 6px; padding: 6px 10px; font-size: 13px; }
  button.primary { background: #1b57d6; color: #fff; border-color: #1b57d6; }
  button.danger { color: #c0392b; border-color: #e6b0aa; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  main { display: grid; grid-template-columns: 300px 1fr; gap: 16px; padding: 16px; }
  @media (max-width: 800px) { main { grid-template-columns: 1fr; } }
  .card { background: #fff; border: 1px solid #e5e8ec; border-radius: 10px; padding: 14px; margin-bottom: 14px; }
  .card h2 { font-size: 14px; margin: 0 0 10px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eef1f4; }
  th { color: #667; font-weight: 600; }
  .row { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
  .row input, .row select { padding: 6px 8px; border: 1px solid #cfd6e0; border-radius: 6px; flex: 1; min-width: 120px; }
  .adv-item { padding: 8px 10px; border-radius: 8px; cursor: pointer; display: flex; justify-content: space-between; }
  .adv-item:hover { background: #f0f3f8; }
  .adv-item.active { background: #e7f0ff; font-weight: 600; }
  .muted { color: #889; font-size: 12px; }
  .pill { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: #eef1f4; }
  .pill.revoked { background: #fdecea; color: #c0392b; }
  .keybox { background: #0b1f3a; color: #7CFC98; padding: 10px; border-radius: 8px; font-family: monospace; word-break: break-all; margin-top: 8px; }
  #status { font-size: 12px; }
</style>
</head>
<body>
<header>
  <h1>🔑 Naver GFA 운영자 콘솔</h1>
  <input id="token" type="password" placeholder="관리자 토큰(ADMIN_TOKEN)" size="28">
  <button class="primary" onclick="saveToken()">접속</button>
  <span id="status" class="muted">토큰을 입력하세요</span>
</header>
<main>
  <div>
    <div class="card">
      <h2>광고주</h2>
      <div id="advList"></div>
      <div class="row" style="margin-top:10px">
        <input id="newAdv" placeholder="새 광고주명">
        <button class="primary" onclick="createAdvertiser()">추가</button>
      </div>
    </div>
    <div class="card">
      <h2>유지보수</h2>
      <button onclick="triggerEnrich()">전체 계정 이름 보강</button>
      <div class="muted" style="margin-top:6px">2110개 계정명을 채웁니다(수 분, GitHub Actions).</div>
    </div>
  </div>

  <div>
    <div id="detail" class="card" style="display:none">
      <h2 id="advTitle"></h2>

      <h3 style="font-size:13px">배정된 광고계정</h3>
      <table><thead><tr><th>번호</th><th>이름</th><th>팀</th><th></th></tr></thead>
        <tbody id="assignedBody"></tbody></table>

      <h3 style="font-size:13px;margin-top:16px">계정 검색·배정</h3>
      <div class="row">
        <input id="q" placeholder="계정명 또는 번호 검색">
        <select id="assignedFilter">
          <option value="">전체</option>
          <option value="no">미배정만</option>
          <option value="yes">배정됨만</option>
        </select>
        <button onclick="searchAccounts()">검색</button>
      </div>
      <table><thead><tr><th>번호</th><th>이름</th><th>현재 배정</th><th></th></tr></thead>
        <tbody id="searchBody"></tbody></table>

      <h3 style="font-size:13px;margin-top:16px">API 키</h3>
      <button class="primary" onclick="issueKey()">새 키 발급</button>
      <div id="newKey"></div>
      <table><thead><tr><th>Prefix</th><th>상태</th><th>마지막 사용</th><th></th></tr></thead>
        <tbody id="keysBody"></tbody></table>
    </div>
    <div id="empty" class="card muted">왼쪽에서 광고주를 선택하거나 새로 추가하세요.</div>
  </div>
</main>

<script>
let TOKEN = sessionStorage.getItem("adminToken") || "";
let CUR = null; // {id, name}
document.getElementById("token").value = TOKEN;

function setStatus(msg, ok) {
  const s = document.getElementById("status");
  s.textContent = msg; s.style.color = ok ? "#7CFC98" : "#ffb4a2";
}
async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "X-Admin-Token": TOKEN, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) { setStatus("인증 실패 — 토큰 확인", false); throw new Error("401"); }
  if (!res.ok) { throw new Error(await res.text()); }
  return res.json();
}
async function saveToken() {
  TOKEN = document.getElementById("token").value.trim();
  sessionStorage.setItem("adminToken", TOKEN);
  try { await api("GET", "/admin/api/me"); setStatus("접속됨 ✓", true); loadAdvertisers(); }
  catch { setStatus("인증 실패", false); }
}
async function loadAdvertisers() {
  const { data } = await api("GET", "/admin/api/advertisers");
  const el = document.getElementById("advList");
  el.innerHTML = data.map(a =>
    `<div class="adv-item ${CUR&&CUR.id===a.id?'active':''}" onclick="selectAdvertiser(${a.id}, ${JSON.stringify(a.name)})">
       <span>${esc(a.name)}</span>
       <span class="muted">계정 ${a.accounts} · 키 ${a.active_keys}</span></div>`).join("");
}
async function createAdvertiser() {
  const name = document.getElementById("newAdv").value.trim();
  if (!name) return;
  await api("POST", "/admin/api/advertisers", { name });
  document.getElementById("newAdv").value = "";
  loadAdvertisers();
}
async function selectAdvertiser(id, name) {
  CUR = { id, name };
  document.getElementById("empty").style.display = "none";
  document.getElementById("detail").style.display = "block";
  document.getElementById("advTitle").textContent = name;
  document.getElementById("newKey").innerHTML = "";
  loadAdvertisers(); loadAssigned(); loadKeys();
}
async function loadAssigned() {
  const { data } = await api("GET", `/admin/api/accounts?assigned=yes&size=100&q=`);
  const mine = data.filter(a => a.advertiser_id === CUR.id);
  document.getElementById("assignedBody").innerHTML = mine.map(a =>
    `<tr><td>${a.naver_account_no}</td><td>${esc(a.account_name)||'<span class=muted>(미보강)</span>'}</td>
     <td class="muted">${esc(a.manager_account_name)||''}</td>
     <td><button class="danger" onclick="unassign(${a.naver_account_no})">해제</button></td></tr>`).join("")
     || `<tr><td colspan=4 class="muted">배정된 계정 없음</td></tr>`;
}
async function searchAccounts() {
  const q = document.getElementById("q").value.trim();
  const f = document.getElementById("assignedFilter").value;
  const { data } = await api("GET", `/admin/api/accounts?q=${encodeURIComponent(q)}&assigned=${f}&size=30`);
  document.getElementById("searchBody").innerHTML = data.map(a =>
    `<tr><td>${a.naver_account_no}</td><td>${esc(a.account_name)||'<span class=muted>(미보강)</span>'}</td>
     <td class="muted">${a.advertiser_name?esc(a.advertiser_name):'<span class=muted>미배정</span>'}</td>
     <td><button class="primary" onclick="assign(${a.naver_account_no})">배정</button></td></tr>`).join("")
     || `<tr><td colspan=4 class="muted">결과 없음</td></tr>`;
}
async function assign(no) {
  await api("POST", `/admin/api/advertisers/${CUR.id}/accounts`, { account_nos: [no] });
  loadAssigned(); searchAccounts(); loadAdvertisers();
}
async function unassign(no) {
  await api("DELETE", `/admin/api/advertisers/${CUR.id}/accounts/${no}`);
  loadAssigned(); loadAdvertisers();
}
async function loadKeys() {
  const { data } = await api("GET", `/admin/api/advertisers/${CUR.id}/keys`);
  document.getElementById("keysBody").innerHTML = data.map(k =>
    `<tr><td>${k.key_prefix}</td>
     <td><span class="pill ${k.status==='revoked'?'revoked':''}">${k.status}</span></td>
     <td class="muted">${k.last_used_at?k.last_used_at.slice(0,10):'-'}</td>
     <td>${k.status==='active'?`<button class="danger" onclick="revoke(${k.id})">폐기</button>`:''}</td></tr>`).join("")
     || `<tr><td colspan=4 class="muted">키 없음</td></tr>`;
}
async function issueKey() {
  const { api_key } = await api("POST", `/admin/api/advertisers/${CUR.id}/keys`, {});
  document.getElementById("newKey").innerHTML =
    `<div class="keybox">⚠️ 지금 한 번만 표시됩니다. 광고주에게 안전하게 전달하세요:<br>${api_key}</div>`;
  loadKeys(); loadAdvertisers();
}
async function revoke(id) {
  if (!confirm("이 키를 폐기하시겠습니까? 되돌릴 수 없습니다.")) return;
  await api("POST", `/admin/api/keys/${id}/revoke`, {});
  loadKeys(); loadAdvertisers();
}
async function triggerEnrich() {
  try { const r = await api("POST", "/admin/api/enrich", {}); alert(r.message); }
  catch (e) { alert("실패: " + e.message); }
}
function esc(s) { return s ? String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])) : ""; }

if (TOKEN) saveToken();
</script>
</body>
</html>
"""
