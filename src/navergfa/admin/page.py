"""운영자 콘솔 단일 페이지 UI (vanilla JS)."""

HTML_PAGE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GFA 운영자 콘솔</title>
<style>
  :root{
    --bg:#eef1f7; --panel:#ffffff; --panel2:#f7f9fc;
    --ink:#0f1b2d; --muted:#647089; --faint:#9aa6bb; --line:#e6eaf2;
    --chrome:#0b1a30; --chrome2:#0e213c; --chrome-ink:#e9f0fb; --chrome-dim:#8ba6cc;
    --accent:#2f6bff; --accent-weak:#e9f0ff; --accent-ink:#1b52e0;
    --green:#0f9d58; --green-weak:#e4f6ec; --red:#d6392f; --red-weak:#fdeceb;
    --amber:#b26a00; --amber-weak:#fbf0dd;
    --r:14px; --r-sm:9px;
    --sh:0 1px 2px rgba(15,27,45,.04), 0 6px 20px rgba(15,27,45,.06);
    --sh-lg:0 10px 34px rgba(15,27,45,.12);
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%}
  body{
    font-family:'Pretendard',-apple-system,BlinkMacSystemFont,'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;
    background:var(--bg); color:var(--ink); -webkit-font-smoothing:antialiased;
    font-size:14px; line-height:1.55;
  }
  .mono{font-family:ui-monospace,'SF Mono','Cascadia Code',Consolas,monospace}
  .tnum{font-variant-numeric:tabular-nums}
  ::-webkit-scrollbar{width:9px;height:9px}
  ::-webkit-scrollbar-thumb{background:#c7cede;border-radius:9px}
  ::-webkit-scrollbar-thumb:hover{background:#aeb8cd}

  /* ── top bar ── */
  .topbar{
    position:sticky; top:0; z-index:20; display:flex; align-items:center; gap:16px;
    background:linear-gradient(180deg,var(--chrome2),var(--chrome));
    color:var(--chrome-ink); padding:0 22px; height:60px;
    border-bottom:1px solid rgba(255,255,255,.06);
  }
  .brand{display:flex; align-items:center; gap:11px; margin-right:auto; min-width:0}
  .logo{width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,var(--accent),#5b8cff);
    display:grid;place-items:center;font-size:17px;box-shadow:0 4px 14px rgba(47,107,255,.4);flex:none}
  .brand .t{font-weight:750;font-size:15px;letter-spacing:-.01em;line-height:1.1}
  .brand .s{font-size:11px;color:var(--chrome-dim);letter-spacing:.02em}
  .auth{display:flex;align-items:center;gap:9px}
  .auth input{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.14);color:#fff;
    padding:8px 11px;border-radius:9px;font-size:13px;width:230px;outline:none}
  .auth input::placeholder{color:#8ba6cc}
  .auth input:focus{border-color:var(--accent);background:rgba(47,107,255,.14)}
  .status{display:flex;align-items:center;gap:7px;font-size:12.5px;color:var(--chrome-dim);white-space:nowrap}
  .dot{width:8px;height:8px;border-radius:50%;background:#5a6b86;box-shadow:0 0 0 0 rgba(0,0,0,0)}
  .dot.on{background:var(--green);box-shadow:0 0 0 4px rgba(15,157,88,.18)}
  .dot.err{background:var(--red);box-shadow:0 0 0 4px rgba(214,57,47,.18)}

  /* ── buttons ── */
  .btn{cursor:pointer;border:1px solid var(--line);background:var(--panel);color:var(--ink);
    border-radius:9px;padding:8px 13px;font-size:13px;font-weight:600;font-family:inherit;
    transition:.14s ease;display:inline-flex;align-items:center;gap:6px}
  .btn:hover{border-color:#cfd6e4;background:var(--panel2)}
  .btn:active{transform:translateY(1px)}
  .btn-primary{background:var(--accent);border-color:var(--accent);color:#fff;box-shadow:0 3px 10px rgba(47,107,255,.28)}
  .btn-primary:hover{background:var(--accent-ink);border-color:var(--accent-ink)}
  .btn-danger{color:var(--red);border-color:#f0c9c6;background:#fff}
  .btn-danger:hover{background:var(--red-weak);border-color:#e6a9a4}
  .btn-sm{padding:5px 10px;font-size:12px}
  .btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

  /* ── app shell ── */
  .shell{display:grid;grid-template-columns:322px 1fr;gap:18px;max-width:1240px;margin:0 auto;padding:20px 22px 60px}
  @media (max-width:860px){.shell{grid-template-columns:1fr}}

  .panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--sh)}
  .sidebar{align-self:start;position:sticky;top:80px;overflow:hidden}
  .side-head{display:flex;align-items:baseline;justify-content:space-between;padding:16px 16px 0}
  .side-head h2{margin:0;font-size:13px;font-weight:750;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
  .count{font-size:12px;color:var(--faint);font-weight:500}

  .toolbar{display:flex;gap:7px;padding:12px 16px 10px}
  .toolbar input,.toolbar select{padding:8px 10px;border:1px solid var(--line);border-radius:9px;
    font-size:13px;font-family:inherit;background:var(--panel2);outline:none;color:var(--ink)}
  .toolbar input{flex:1;min-width:0}
  .toolbar input:focus,.toolbar select:focus{border-color:var(--accent);background:#fff}
  .toolbar select{flex:0 0 auto}

  .advscroll{max-height:56vh;overflow-y:auto;padding:2px 8px 8px}
  .adv-item{display:flex;align-items:center;justify-content:space-between;gap:8px;
    padding:9px 11px;border-radius:10px;cursor:pointer;border:1px solid transparent;transition:.12s}
  .adv-item:hover{background:var(--panel2)}
  .adv-item.active{background:var(--accent-weak);border-color:#cfddff}
  .adv-item .nm{font-weight:600;font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .adv-item.active .nm{color:var(--accent-ink)}
  .adv-item .meta{font-size:11.5px;color:var(--faint);white-space:nowrap;flex:none}
  .adv-empty{padding:18px;text-align:center;color:var(--faint);font-size:13px}

  .side-foot{border-top:1px solid var(--line);padding:12px 16px}
  .newrow{display:flex;gap:7px}
  .newrow input{flex:1;min-width:0;padding:8px 10px;border:1px solid var(--line);border-radius:9px;font-size:13px;font-family:inherit;outline:none}
  .newrow input:focus{border-color:var(--accent)}
  .maint{margin-top:12px}
  .maint .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);font-weight:700;margin-bottom:7px}
  .maint .hint{font-size:11.5px;color:var(--faint);margin-top:6px;line-height:1.4}

  /* ── workspace ── */
  .workspace{min-width:0}
  .empty-state{background:var(--panel);border:1px dashed var(--line);border-radius:var(--r);
    padding:70px 24px;text-align:center;color:var(--faint)}
  .empty-state .big{font-size:34px;margin-bottom:10px}
  .empty-state p{margin:0;font-size:14px}

  .dhead{padding:20px 22px;border-bottom:1px solid var(--line)}
  .dhead .ey{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--faint);font-weight:700}
  .dhead h1{margin:4px 0 0;font-size:23px;font-weight:800;letter-spacing:-.01em;word-break:break-all}
  .tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:16px 22px 0}
  .tile{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:13px 15px}
  .tile .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700}
  .tile .v{font-size:25px;font-weight:800;margin-top:3px;letter-spacing:-.01em}
  .tile.a .v{color:var(--accent)}
  .tile.g .v{color:var(--green)}

  .sec{padding:20px 22px}
  .sec+.sec{border-top:1px solid var(--line)}
  .sec-h{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}
  .sec-h h3{margin:0;font-size:13px;font-weight:750;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}

  .tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px}
  table{width:100%;border-collapse:collapse;font-size:13.5px}
  thead th{text-align:left;padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
    color:var(--faint);font-weight:700;background:var(--panel2);border-bottom:1px solid var(--line)}
  tbody td{padding:11px 14px;border-bottom:1px solid var(--line);vertical-align:middle}
  tbody tr:last-child td{border-bottom:0}
  tbody tr:hover{background:var(--panel2)}
  td.num{font-variant-numeric:tabular-nums;color:var(--muted)}
  td.name{font-weight:600}
  .cell-empty{padding:16px 14px;color:var(--faint);text-align:center}

  .pill{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:700;
    padding:3px 9px;border-radius:999px;letter-spacing:.02em}
  .pill::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.9}
  .pill.active{background:var(--green-weak);color:var(--green)}
  .pill.revoked{background:#eef1f5;color:var(--faint)}

  .searchbar{display:flex;gap:8px;margin-bottom:12px}
  .searchbar input,.searchbar select{padding:9px 11px;border:1px solid var(--line);border-radius:9px;
    font-size:13px;font-family:inherit;background:var(--panel2);outline:none;color:var(--ink)}
  .searchbar input{flex:1;min-width:0}
  .searchbar input:focus,.searchbar select:focus{border-color:var(--accent);background:#fff}

  .keyreveal{margin-top:12px;border:1px solid #cfddff;background:var(--accent-weak);border-radius:12px;padding:13px 15px}
  .keyreveal .cap{font-size:12px;color:var(--accent-ink);font-weight:700;display:flex;align-items:center;gap:6px;margin-bottom:8px}
  .keyreveal .kv{display:flex;gap:9px;align-items:center}
  .keyreveal code{flex:1;min-width:0;background:#0b1a30;color:#a9ffd8;padding:10px 12px;border-radius:9px;
    font-size:12.5px;overflow-x:auto;white-space:nowrap}

  /* ── toast ── */
  .toast{position:fixed;left:50%;bottom:26px;transform:translate(-50%,20px);opacity:0;pointer-events:none;
    background:var(--chrome);color:#fff;padding:11px 18px;border-radius:11px;font-size:13.5px;font-weight:600;
    box-shadow:var(--sh-lg);z-index:50;transition:.24s ease;display:flex;align-items:center;gap:9px;max-width:90vw}
  .toast.show{opacity:1;transform:translate(-50%,0)}
  .toast::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--green)}
  .toast.err::before{background:var(--red)}
  .toast.warn::before{background:var(--amber)}

  /* ── nav tabs ── */
  .nav{display:flex;gap:3px;background:rgba(255,255,255,.06);padding:4px;border-radius:11px}
  .nav .tab{background:transparent;border:0;color:var(--chrome-dim);font-weight:650;font-size:13px;
    padding:7px 15px;border-radius:8px;cursor:pointer;font-family:inherit;transition:.14s}
  .nav .tab:hover{color:#fff}
  .nav .tab.active{background:rgba(255,255,255,.13);color:#fff}

  /* ── usage dashboard ── */
  .uwrap{max-width:1240px;margin:0 auto;padding:20px 22px 60px;display:flex;flex-direction:column;gap:18px}
  .kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
  @media (max-width:760px){.kpis{grid-template-columns:repeat(2,1fr)}}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:var(--sh)}
  .kpi .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700}
  .kpi .v{font-size:30px;font-weight:800;margin-top:4px;letter-spacing:-.02em}
  .kpi.accent .v{color:var(--accent)}
  .chartcard{padding:18px}
  .chart svg{display:block}
  .ugrid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  @media (max-width:860px){.ugrid{grid-template-columns:1fr}}
  .ugrid .panel{overflow:hidden}
  .ugrid .sec-h{margin-bottom:0;padding:16px 18px 12px;border-bottom:1px solid var(--line)}
  .logscroll{max-height:360px;overflow-y:auto}
  .seg{display:inline-flex;background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:2px}
  .seg button{border:0;background:transparent;padding:5px 12px;font-size:12px;font-weight:600;border-radius:7px;
    cursor:pointer;color:var(--muted);font-family:inherit;transition:.12s}
  .seg button.on{background:#fff;color:var(--ink);box-shadow:var(--sh)}
  #advChart svg{display:block}

  @media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<header class="topbar">
  <div class="brand">
    <div class="logo">🔑</div>
    <div><div class="t">GFA 운영자 콘솔</div><div class="s">네이버 GFA 리포팅 중계 · 광고주 &amp; 키 관리</div></div>
  </div>
  <nav class="nav">
    <button class="tab active" data-view="manage" onclick="switchView('manage')">관리</button>
    <button class="tab" data-view="usage" onclick="switchView('usage')">사용 현황</button>
  </nav>
  <div class="auth">
    <input id="token" type="password" placeholder="관리자 토큰" autocomplete="off">
    <button class="btn btn-primary" onclick="saveToken()">접속</button>
    <span class="status"><span id="dot" class="dot"></span><span id="status">토큰 입력</span></span>
  </div>
</header>

<div id="view-manage">
<div class="shell">
  <!-- 사이드바 -->
  <aside class="panel sidebar">
    <div class="side-head"><h2>광고주</h2><span id="advCount" class="count"></span></div>
    <div class="toolbar">
      <input id="advSearch" placeholder="광고주 검색" oninput="renderAdvertisers()">
      <select id="advSort" onchange="renderAdvertisers()">
        <option value="name">이름순</option>
        <option value="accounts">계정 많은순</option>
        <option value="keys">키 많은순</option>
        <option value="recent">최근 추가순</option>
      </select>
    </div>
    <div id="advList" class="advscroll"></div>
    <div class="side-foot">
      <div class="newrow">
        <input id="newAdv" placeholder="새 광고주명" onkeydown="if(event.key==='Enter')createAdvertiser()">
        <button class="btn btn-primary" onclick="createAdvertiser()">추가</button>
      </div>
      <div class="maint">
        <div class="lbl">유지보수</div>
        <button class="btn" onclick="triggerEnrich()">전체 계정 이름 보강</button>
        <div class="hint">네이버에서 계정명을 일괄로 채웁니다(수 분).</div>
      </div>
    </div>
  </aside>

  <!-- 워크스페이스 -->
  <main class="workspace">
    <div id="empty" class="empty-state">
      <div class="big">🗂️</div>
      <p>왼쪽에서 광고주를 선택하거나 새로 추가하세요.</p>
    </div>

    <div id="detail" class="panel" style="display:none">
      <div class="dhead">
        <div class="ey">광고주</div>
        <h1 id="advTitle"></h1>
      </div>
      <div class="tiles">
        <div class="tile a"><div class="k">배정 계정</div><div class="v tnum" id="tileAccounts">0</div></div>
        <div class="tile g"><div class="k">활성 키</div><div class="v tnum" id="tileKeys">0</div></div>
      </div>

      <div class="sec">
        <div class="sec-h"><h3>사용 현황 · 최근 14일</h3><span id="advUsageMeta" class="count"></span></div>
        <div id="advChart" class="chart"></div>
      </div>

      <div class="sec">
        <div class="sec-h"><h3>배정된 광고계정</h3></div>
        <div class="tblwrap"><table>
          <thead><tr><th>번호</th><th>이름</th><th>팀</th><th></th></tr></thead>
          <tbody id="assignedBody"></tbody>
        </table></div>
      </div>

      <div class="sec">
        <div class="sec-h"><h3>계정 검색 · 배정</h3></div>
        <div class="searchbar">
          <input id="q" placeholder="계정명 또는 번호 검색" onkeydown="if(event.key==='Enter')searchAccounts()">
          <select id="assignedFilter">
            <option value="">전체</option>
            <option value="no">미배정만</option>
            <option value="yes">배정됨만</option>
          </select>
          <button class="btn" onclick="searchAccounts()">검색</button>
        </div>
        <div class="tblwrap"><table>
          <thead><tr><th>번호</th><th>이름</th><th>현재 배정</th><th></th></tr></thead>
          <tbody id="searchBody"><tr><td colspan="4" class="cell-empty">검색어를 입력하세요</td></tr></tbody>
        </table></div>
      </div>

      <div class="sec">
        <div class="sec-h"><h3>API 키</h3><button class="btn btn-primary btn-sm" onclick="issueKey()">+ 새 키 발급</button></div>
        <div id="newKey"></div>
        <div class="tblwrap"><table>
          <thead><tr><th>Prefix</th><th>상태</th><th>마지막 사용</th><th></th></tr></thead>
          <tbody id="keysBody"></tbody>
        </table></div>
      </div>
    </div>
  </main>
</div>
</div><!-- /view-manage -->

<section id="view-usage" hidden>
  <div class="uwrap">
    <div class="kpis">
      <div class="kpi accent"><div class="k">오늘 호출</div><div class="v tnum" id="k1">–</div></div>
      <div class="kpi"><div class="k">최근 7일 호출</div><div class="v tnum" id="k7">–</div></div>
      <div class="kpi"><div class="k">활성 광고주 · 7일</div><div class="v tnum" id="kadv">–</div></div>
      <div class="kpi"><div class="k">에러율 · 7일</div><div class="v tnum" id="kerr">–</div></div>
    </div>
    <div class="panel chartcard">
      <div class="sec-h"><h3 id="chartTitle">일별 호출 · 최근 14일</h3>
        <div class="seg" id="periodSeg">
          <button data-d="14" class="on" onclick="setPeriod(14)">14일</button>
          <button data-d="30" onclick="setPeriod(30)">30일</button>
          <button data-d="90" onclick="setPeriod(90)">90일</button>
        </div>
      </div>
      <div id="chart" class="chart"></div>
    </div>
    <div class="ugrid">
      <div class="panel">
        <div class="sec-h"><h3 id="byAdvTitle">광고주별 사용 현황 · 14일</h3>
          <button class="btn btn-sm" onclick="exportCSV()">CSV 내보내기</button></div>
        <div class="logscroll"><div class="tblwrap" style="border:0"><table>
          <thead><tr><th>광고주</th><th>호출</th><th>에러</th><th>마지막</th></tr></thead>
          <tbody id="byAdvBody"></tbody></table></div></div>
      </div>
      <div class="panel">
        <div class="sec-h"><h3>최근 호출 로그</h3></div>
        <div class="logscroll"><div class="tblwrap" style="border:0"><table>
          <thead><tr><th>시간</th><th>광고주</th><th>엔드포인트</th><th>상태</th></tr></thead>
          <tbody id="recentBody"></tbody></table></div></div>
      </div>
    </div>
  </div>
</section>

<div id="toast" class="toast"></div>

<script>
let TOKEN = sessionStorage.getItem("adminToken") || "";
let CUR = null;
let ADVS = [];
document.getElementById("token").value = TOKEN;

function toast(msg, type){ const t=document.getElementById("toast"); t.textContent=msg;
  t.className="toast show"+(type?" "+type:""); clearTimeout(t._t); t._t=setTimeout(()=>t.className="toast",2600); }
function setStatus(msg, state){ document.getElementById("status").textContent=msg;
  document.getElementById("dot").className="dot"+(state?" "+state:""); }

async function api(method, path, body){
  const res = await fetch(path, {
    method, headers:{ "X-Admin-Token":TOKEN, "Content-Type":"application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if(res.status===401){ setStatus("인증 실패", "err"); throw new Error("401"); }
  if(!res.ok){ throw new Error(await res.text()); }
  return res.json();
}
async function saveToken(){
  TOKEN=document.getElementById("token").value.trim();
  sessionStorage.setItem("adminToken", TOKEN);
  try{ await api("GET","/admin/api/me"); setStatus("접속됨", "on"); loadAdvertisers(); }
  catch{ setStatus("인증 실패", "err"); }
}

async function loadAdvertisers(){ const {data}=await api("GET","/admin/api/advertisers"); ADVS=data; renderAdvertisers(); }
function renderAdvertisers(){
  const term=(document.getElementById("advSearch").value||"").trim().toLowerCase();
  const sort=document.getElementById("advSort").value;
  let list=ADVS.slice();
  if(term) list=list.filter(a=>(a.name||"").toLowerCase().includes(term));
  const byName=(a,b)=>(a.name||"").localeCompare(b.name||"","ko");
  const cmp={ name:byName, accounts:(a,b)=>(b.accounts-a.accounts)||byName(a,b),
    keys:(a,b)=>(b.active_keys-a.active_keys)||byName(a,b), recent:(a,b)=>b.id-a.id }[sort]||byName;
  list.sort(cmp);
  document.getElementById("advCount").textContent=`총 ${ADVS.length}개`+(term?` · ${list.length} 검색`:"");
  document.getElementById("advList").innerHTML = list.map(a=>
    `<div class="adv-item ${CUR&&CUR.id===a.id?'active':''}" onclick="selectAdvertiser(${a.id})">
       <span class="nm">${esc(a.name)}</span>
       <span class="meta">계정 ${a.accounts} · 키 ${a.active_keys}</span></div>`).join("")
    || `<div class="adv-empty">검색 결과 없음</div>`;
}
async function createAdvertiser(){
  const el=document.getElementById("newAdv"); const name=el.value.trim(); if(!name) return;
  await api("POST","/admin/api/advertisers",{name}); el.value="";
  await loadAdvertisers(); toast("광고주 추가됨");
}
async function selectAdvertiser(id){
  const adv=ADVS.find(a=>a.id===id); CUR={id, name:adv?adv.name:String(id)};
  document.getElementById("empty").style.display="none";
  document.getElementById("detail").style.display="block";
  document.getElementById("advTitle").textContent=CUR.name;
  document.getElementById("newKey").innerHTML="";
  document.getElementById("searchBody").innerHTML=`<tr><td colspan="4" class="cell-empty">검색어를 입력하세요</td></tr>`;
  renderAdvertisers(); loadAssigned(); loadKeys(); loadAdvertiserUsage();
}
async function loadAssigned(){
  const {data}=await api("GET",`/admin/api/advertisers/${CUR.id}/accounts`);
  document.getElementById("tileAccounts").textContent=data.length;
  document.getElementById("assignedBody").innerHTML = data.map(a=>
    `<tr><td class="num">${a.naver_account_no}</td>
     <td class="name">${esc(a.account_name)||'<span style="color:var(--faint)">(미보강)</span>'}</td>
     <td style="color:var(--muted)">${esc(a.manager_account_name)||'—'}</td>
     <td style="text-align:right"><button class="btn btn-danger btn-sm" onclick="unassign(${a.naver_account_no})">해제</button></td></tr>`).join("")
    || `<tr><td colspan="4" class="cell-empty">배정된 계정이 없습니다</td></tr>`;
}
async function searchAccounts(){
  const q=document.getElementById("q").value.trim();
  const f=document.getElementById("assignedFilter").value;
  const {data}=await api("GET",`/admin/api/accounts?q=${encodeURIComponent(q)}&assigned=${f}&size=30`);
  document.getElementById("searchBody").innerHTML = data.map(a=>
    `<tr><td class="num">${a.naver_account_no}</td>
     <td class="name">${esc(a.account_name)||'<span style="color:var(--faint)">(미보강)</span>'}</td>
     <td>${a.advertiser_name?esc(a.advertiser_name):'<span style="color:var(--faint)">미배정</span>'}</td>
     <td style="text-align:right"><button class="btn btn-primary btn-sm" onclick="assign(${a.naver_account_no})">배정</button></td></tr>`).join("")
    || `<tr><td colspan="4" class="cell-empty">결과 없음</td></tr>`;
}
async function assign(no){ await api("POST",`/admin/api/advertisers/${CUR.id}/accounts`,{account_nos:[no]});
  loadAssigned(); searchAccounts(); loadAdvertisers(); toast("계정 배정됨"); }
async function unassign(no){ await api("DELETE",`/admin/api/advertisers/${CUR.id}/accounts/${no}`);
  loadAssigned(); loadAdvertisers(); toast("계정 해제됨"); }

async function loadKeys(){
  const {data}=await api("GET",`/admin/api/advertisers/${CUR.id}/keys`);
  document.getElementById("tileKeys").textContent=data.filter(k=>k.status==="active").length;
  document.getElementById("keysBody").innerHTML = data.map(k=>
    `<tr><td class="mono">${k.key_prefix}</td>
     <td><span class="pill ${k.status==='revoked'?'revoked':'active'}">${k.status}</span></td>
     <td style="color:var(--muted)">${k.last_used_at?k.last_used_at.slice(0,10):'—'}</td>
     <td style="text-align:right">${k.status==='active'?`<button class="btn btn-danger btn-sm" onclick="revoke(${k.id})">폐기</button>`:''}</td></tr>`).join("")
    || `<tr><td colspan="4" class="cell-empty">발급된 키가 없습니다</td></tr>`;
}
async function issueKey(){
  const {api_key}=await api("POST",`/admin/api/advertisers/${CUR.id}/keys`,{});
  document.getElementById("newKey").innerHTML =
    `<div class="keyreveal">
       <div class="cap">⚠️ 이 키는 지금 한 번만 표시됩니다 — 광고주에게 안전하게 전달하세요</div>
       <div class="kv"><code id="freshKey">${esc(api_key)}</code>
         <button class="btn btn-sm" onclick="copyKey()">복사</button></div>
     </div>`;
  loadKeys(); loadAdvertisers(); toast("새 키 발급됨");
}
function copyKey(){ const t=document.getElementById("freshKey").textContent;
  navigator.clipboard.writeText(t).then(()=>toast("키를 복사했습니다"),()=>toast("복사 실패","err")); }
async function revoke(id){
  if(!confirm("이 키를 폐기하시겠습니까? 되돌릴 수 없습니다.")) return;
  await api("POST",`/admin/api/keys/${id}/revoke`,{}); loadKeys(); loadAdvertisers(); toast("키 폐기됨","warn");
}
async function triggerEnrich(){
  try{ const r=await api("POST","/admin/api/enrich",{}); toast(r.message||"실행됨"); }
  catch(e){ toast("실패: "+e.message,"err"); }
}
function esc(s){ return s?String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])):""; }
function fmt(iso){ return iso? String(iso).replace('T',' ').slice(5,16):'—'; }

/* ── 뷰 전환 & 사용 현황 ── */
function switchView(v){
  document.querySelectorAll(".nav .tab").forEach(t=>t.classList.toggle("active", t.dataset.view===v));
  document.getElementById("view-manage").hidden = v!=="manage";
  document.getElementById("view-usage").hidden  = v!=="usage";
  if(v==="usage" && TOKEN) loadUsage();
}
let PERIOD=14, BYADV=[];
async function loadUsage(){ loadKPIs(); loadChart(PERIOD); loadByAdv(PERIOD); loadRecent(); }
async function loadKPIs(){
  try{ const s=await api("GET","/admin/api/usage/summary");
    document.getElementById("k1").textContent=(s.calls_1d??0).toLocaleString();
    document.getElementById("k7").textContent=(s.calls_7d??0).toLocaleString();
    document.getElementById("kadv").textContent=(s.active_7d??0).toLocaleString();
    document.getElementById("kerr").textContent=(s.calls_7d? Math.round(s.errors_7d/s.calls_7d*100):0)+"%";
  }catch(e){ toast("사용 현황 로드 실패","err"); }
}
async function loadChart(days){
  const ts=await api("GET","/admin/api/usage/timeseries?days="+days);
  document.getElementById("chartTitle").textContent="일별 호출 · 최근 "+days+"일";
  renderBars(ts.data||[], "chart", 150, true);
}
async function loadByAdv(days){
  const ba=await api("GET","/admin/api/usage/by-advertiser?days="+days);
  BYADV=ba.data||[];
  document.getElementById("byAdvTitle").textContent="광고주별 사용 현황 · "+days+"일";
  document.getElementById("byAdvBody").innerHTML=BYADV.map(r=>
    `<tr><td class="name">${esc(r.name)}</td>
     <td class="num">${(r.calls||0).toLocaleString()}</td>
     <td class="num" style="color:${r.errors?'var(--red)':'var(--muted)'}">${r.errors||0}</td>
     <td style="color:var(--muted)">${fmt(r.last_call)}</td></tr>`).join("")
    || `<tr><td colspan="4" class="cell-empty">아직 호출 기록이 없습니다</td></tr>`;
}
async function loadRecent(){
  const rc=await api("GET","/admin/api/usage/recent?limit=40");
  document.getElementById("recentBody").innerHTML=(rc.data||[]).map(r=>{
    const err=r.status_code>=400;
    return `<tr><td class="mono" style="color:var(--muted);font-size:12px">${fmt(r.ts)}</td>
     <td class="name">${r.advertiser?esc(r.advertiser):'—'}</td>
     <td class="mono" style="font-size:12px">${esc(r.endpoint)}</td>
     <td><span class="pill ${err?'revoked':'active'}" style="${err?'color:var(--red);background:var(--red-weak)':''}">${r.status_code}</span></td></tr>`;
  }).join("") || `<tr><td colspan="4" class="cell-empty">아직 호출 기록이 없습니다</td></tr>`;
}
function setPeriod(d){ PERIOD=d;
  document.querySelectorAll("#periodSeg button").forEach(b=>b.classList.toggle("on", (+b.dataset.d)===d));
  loadChart(d); loadByAdv(d);
}
function csvCell(s){ s=String(s??""); return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s; }
function exportCSV(){
  if(!BYADV.length){ toast("내보낼 데이터가 없습니다","warn"); return; }
  const head=["광고주","호출","에러","마지막호출"];
  const lines=[head.join(",")].concat(BYADV.map(r=>
    [csvCell(r.name), r.calls||0, r.errors||0, csvCell(fmt(r.last_call))].join(",")));
  const blob=new Blob(["﻿"+lines.join("\r\n")],{type:"text/csv;charset=utf-8"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
  a.download="gfa_usage_"+PERIOD+"d.csv"; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
  toast("CSV를 내보냈습니다");
}
async function loadAdvertiserUsage(){
  try{
    const u=await api("GET",`/admin/api/advertisers/${CUR.id}/usage?days=14`);
    const s=u.summary||{};
    document.getElementById("advUsageMeta").textContent=
      `7일 ${(s.calls_7d||0).toLocaleString()}회 · 30일 ${(s.calls_30d||0).toLocaleString()}회 · 마지막 ${s.last_call?fmt(s.last_call):'없음'}`;
    renderBars(u.series||[], "advChart", 92, false);
  }catch(e){ document.getElementById("advChart").innerHTML=""; document.getElementById("advUsageMeta").textContent=""; }
}
function renderBars(series, elId, h, showAxis){
  const pad=14, n=Math.max(series.length,1);
  const w=Math.max(n*26, 260);
  const max=Math.max(1,...series.map(d=>d.calls));
  const slot=(w-pad*2)/n, bw=Math.min(20, slot-6);
  const bars=series.map((d,i)=>{
    const x=pad+i*slot+(slot-bw)/2;
    const drawn=d.calls>0?Math.max((d.calls/max)*(h-pad*2),3):0;
    const last=i===series.length-1;
    return `<rect x="${x.toFixed(1)}" y="${(h-pad-drawn).toFixed(1)}" width="${bw.toFixed(1)}" height="${drawn.toFixed(1)}" rx="3"
      fill="${last?'var(--accent)':'#a9c2ff'}"><title>${d.d} · ${d.calls}회</title></rect>`;
  }).join("");
  const base=`<line x1="${pad}" y1="${h-pad}" x2="${w-pad}" y2="${h-pad}" stroke="var(--line)" stroke-width="1"/>`;
  const axis=showAxis?
    `<div style="display:flex;justify-content:space-between;font-size:11px;color:var(--faint);margin-top:6px">
       <span>${series[0]?series[0].d.slice(5):''}</span><span>최대 ${max.toLocaleString()}회/일</span><span>${series.length?series[series.length-1].d.slice(5):''}</span></div>`:"";
  document.getElementById(elId).innerHTML=
    `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none" style="max-width:100%">${base}${bars}</svg>${axis}`;
}

if(TOKEN) saveToken();
</script>
</body>
</html>
"""
