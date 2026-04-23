# bodn/web_ui.py — HTML/CSS/JS for the parental control web UI

LOGIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bodn - Login</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;display:flex;justify-content:center;align-items:center;min-height:100vh}
.login{background:#0f3460;padding:32px;border-radius:12px;text-align:center;width:280px}
.login h1{color:#e94560;margin-bottom:16px;font-size:1.5em}
.login input{width:100%;padding:12px;font-size:1.5em;text-align:center;letter-spacing:8px;background:#16213e;border:1px solid #333;color:#e0e0e0;border-radius:8px;margin:12px 0}
.login button{width:100%;padding:12px;background:#e94560;color:#fff;border:none;border-radius:8px;font-size:1em;cursor:pointer;margin-top:8px}
.login .err{color:#e94560;font-size:0.85em;margin-top:8px;display:none}
</style>
</head>
<body>
<div class="login">
<h1>Bodn</h1>
<p>Enter PIN</p>
<input type="password" id="pin" maxlength="8" inputmode="numeric" autofocus>
<button onclick="login()">Unlock</button>
<div class="err" id="err">Wrong PIN</div>
</div>
<script>
document.getElementById('pin').addEventListener('keyup',function(e){if(e.key==='Enter')login()});
async function login(){
var pin=document.getElementById('pin').value;
var r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:pin})});
if(r.ok){location.reload()}else{document.getElementById('err').style.display='block';document.getElementById('pin').value=''}
}
</script>
</body>
</html>
"""

HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bodn</title>
<style>
:root{
--bg:#1a1a2e;
--surface:#16213e;
--surface-alt:#0f3460;
--accent:#e94560;
--text:#e0e0e0;
--text-dim:#aaa;
--text-faint:#666;
--ok:#27ae60;
--warn:#f39c12;
--info:#2980b9;
--cooldown:#8e44ad;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);max-width:480px;margin:0 auto;padding:16px}
h1{text-align:center;color:var(--accent);margin-bottom:8px;font-size:1.5em}
.tabs{display:flex;gap:0;overflow-x:auto;scrollbar-width:none;-ms-overflow-style:none;background:var(--surface);border-radius:8px 8px 0 0;position:sticky;top:0;z-index:10}
.tabs::-webkit-scrollbar{display:none}
.tab{flex:1 0 auto;min-width:72px;padding:10px 14px;text-align:center;background:transparent;border:none;color:var(--text-dim);cursor:pointer;font-size:0.9em;font-weight:600;white-space:nowrap;border-radius:8px 8px 0 0;transition:background-color .15s,color .15s}
.tab:hover{color:var(--text)}
.tab.active{background:var(--surface-alt);color:var(--accent)}
.tab:focus-visible{outline:2px solid var(--accent);outline-offset:-4px}
.panel{display:none;background:var(--surface-alt);border-radius:0 0 8px 8px;padding:16px}
.panel.active{display:block}
.badge{display:inline-block;padding:4px 12px;border-radius:12px;font-weight:bold;font-size:0.9em}
.badge.playing{background:var(--ok);color:#fff}
.badge.idle{background:#555;color:#ccc}
.badge.warn{background:var(--warn);color:#000}
.badge.sleeping{background:var(--info);color:#fff}
.badge.lockdown{background:var(--accent);color:#fff}
.badge.cooldown{background:var(--cooldown);color:#fff}
.stat{margin:12px 0}
.stat label{display:block;font-size:0.8em;color:var(--text-dim);margin-bottom:4px}
.stat .val{font-size:1.3em;font-weight:bold}
.progress{background:var(--surface);border-radius:6px;height:20px;overflow:hidden;margin-top:4px}
.progress .bar{height:100%;background:var(--ok);transition:width 1s}
.field{margin:14px 0}
.field label{display:block;font-size:0.85em;color:var(--text-dim);margin-bottom:6px}
.field input[type=range]{width:100%}
.field .rv{float:right;font-weight:bold;color:var(--accent)}
.toggle{display:flex;align-items:center;gap:10px;margin:14px 0}
.toggle input{width:20px;height:20px}
.btn{display:block;width:100%;padding:12px;margin-top:12px;border:none;border-radius:8px;font-size:1em;cursor:pointer}
.btn-danger{background:var(--accent);color:#fff}
.btn-primary{background:var(--info);color:#fff}
.btn-save{background:var(--ok);color:#fff}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--surface);font-size:0.85em}
th{color:var(--text-dim)}
.input-field{width:100%;padding:8px;background:var(--surface);border:1px solid #333;color:var(--text);border-radius:6px;margin-top:4px}
.msg{text-align:center;padding:8px;margin:8px 0;border-radius:6px;display:none}
.msg.ok{display:block;background:var(--ok);color:#fff}
.msg.err{display:block;background:var(--accent);color:#fff}
.bar-chart{margin:12px 0}
.bar-row{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:0.85em}
.bar-row .bar-label{width:70px;color:var(--text-dim);text-align:right}
.bar-row .bar-fill{height:16px;background:var(--accent);border-radius:3px;min-width:2px}
.bar-row .bar-val{color:var(--text);font-size:0.8em}
.stat-card{background:var(--surface);border-radius:8px;padding:12px;margin:8px 0;text-align:center}
.stat-card .val{font-size:1.5em;font-weight:bold;color:var(--accent)}
.stat-card .lbl{font-size:0.75em;color:var(--text-dim);margin-top:2px}
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.suggest-box{background:#1a3a1a;border:1px solid var(--ok);border-radius:8px;padding:12px;margin:12px 0}
.suggest-box .title{color:var(--ok);font-weight:bold;margin-bottom:6px}
.mode-row{display:flex;align-items:center;gap:8px;margin:8px 0}
.mode-row label{flex:1;font-size:0.85em;color:var(--text-dim)}
.mode-row input{width:70px;padding:6px;background:var(--surface);border:1px solid #333;color:var(--text);border-radius:6px;text-align:center}
.mode-row .hint{font-size:0.7em;color:var(--text-faint)}
</style>
</head>
<body>
<h1>Bodn</h1>
<div class="tabs" role="tablist" aria-label="Sections">
<button class="tab active" role="tab" id="tab-dash" aria-controls="dash" aria-selected="true" tabindex="0" onclick="show('dash')">Dashboard</button>
<button class="tab" role="tab" id="tab-limits" aria-controls="limits" aria-selected="false" tabindex="-1" onclick="show('limits')">Limits</button>
<button class="tab" role="tab" id="tab-history" aria-controls="history" aria-selected="false" tabindex="-1" onclick="show('history')">History</button>
<button class="tab" role="tab" id="tab-stats" aria-controls="stats" aria-selected="false" tabindex="-1" onclick="show('stats')">Stats</button>
<button class="tab" role="tab" id="tab-wifi" aria-controls="wifi" aria-selected="false" tabindex="-1" onclick="show('wifi')">WiFi</button>
<button class="tab" role="tab" id="tab-security" aria-controls="security" aria-selected="false" tabindex="-1" onclick="show('security')">Security</button>
<button class="tab" role="tab" id="tab-debug" aria-controls="debug" aria-selected="false" tabindex="-1" onclick="show('debug')">Debug</button>
<button class="tab" role="tab" id="tab-nfc" aria-controls="nfc" aria-selected="false" tabindex="-1" onclick="show('nfc')">NFC</button>
</div>

<div id="dash" class="panel active" role="tabpanel" aria-labelledby="tab-dash">
<div style="text-align:center;margin-bottom:12px">
<span id="state-badge" class="badge idle">IDLE</span>
</div>
<div class="stat"><label>Sessions today</label><span id="s-count" class="val">0</span> / <span id="s-max" class="val">5</span></div>
<div class="stat"><label id="time-label">Time remaining</label><div class="progress"><div id="time-bar" class="bar" style="width:0%"></div></div><div id="time-text" style="text-align:center;font-size:0.85em;margin-top:4px">--</div></div>
<div class="toggle"><input type="checkbox" id="sessions-enabled" checked onchange="toggleSessions()"><label>Session limits enabled</label></div>
<div class="stats-grid">
<div id="bat-card" class="stat-card" style="display:none">
<div class="val" id="bat-val">--</div>
<div class="lbl" id="bat-lbl">Battery</div>
</div>
<div id="temp-card" class="stat-card" style="display:none">
<div class="val" id="temp-val">--</div>
<div class="lbl" id="temp-lbl">Temperature</div>
</div>
</div>
<div id="safety-alert" style="display:none;margin:8px 0;padding:10px;border-radius:8px;font-size:0.85em;font-weight:bold"></div>
<button class="btn btn-primary" id="resume-btn" onclick="resumeNow()" style="display:none;margin-bottom:8px">Resume now</button>
<button class="btn btn-danger" id="lockdown-btn" onclick="toggleLockdown()">Lockdown</button>
</div>

<div id="limits" class="panel" role="tabpanel" aria-labelledby="tab-limits">
<div class="field"><label>Session length <span class="rv" id="rv-sess">20 min</span></label><input type="range" id="max_session_min" min="1" max="60" value="20" oninput="updRv(this,'rv-sess',' min')"></div>
<div class="field"><label>Max sessions/day <span class="rv" id="rv-maxs">5</span></label><input type="range" id="max_sessions_day" min="1" max="20" value="5" oninput="updRv(this,'rv-maxs','')"></div>
<div class="field"><label>Break between sessions <span class="rv" id="rv-brk">15 min</span></label><input type="range" id="break_min" min="1" max="60" value="15" oninput="updRv(this,'rv-brk',' min')"></div>
<div class="field"><label>Quiet start (HH:MM, empty=off)</label><input class="input-field" type="text" id="quiet_start" placeholder="21:00"></div>
<div class="field"><label>Quiet end (HH:MM)</label><input class="input-field" type="text" id="quiet_end" placeholder="07:00"></div>
<div class="field"><label>Device language</label><select id="language" class="input-field"><option value="sv">Svenska</option><option value="en">English</option></select></div>
<div class="field"><label>Timezone (UTC offset, DST added automatically)</label><select id="tz_offset" class="input-field"></select></div>
<h3 style="margin-top:16px;color:#e94560;font-size:0.95em">Audio</h3>
<div class="field"><label>Sound enabled</label><select id="audio_enabled" class="input-field"><option value="true">On</option><option value="false">Off</option></select></div>
<div class="field"><label>Volume <span class="rv" id="rv-vol">30%</span></label><input type="range" id="volume" min="0" max="100" step="5" value="30" oninput="updRv(this,'rv-vol','%')"></div>
<h3 style="margin-top:16px;color:#e94560;font-size:0.95em">Visible modes</h3>
<p style="font-size:0.75em;color:#666;margin:4px 0">Toggle which modes appear in the main menu.</p>
<div id="mode-vis"></div>
<h3 style="margin-top:16px;color:#e94560;font-size:0.95em">Per-mode limits</h3>
<p style="font-size:0.75em;color:#666;margin:4px 0">Minutes per session. Empty = use global. 0 = unlimited.</p>
<div id="mode-limits"></div>
<button class="btn btn-save" onclick="saveSettings()">Save</button>
<div id="limits-msg" class="msg"></div>
</div>

<div id="history" class="panel" role="tabpanel" aria-labelledby="tab-history">
<table><thead><tr><th>Date</th><th>Start</th><th>Duration</th><th>Mode</th></tr></thead><tbody id="hist-body"></tbody></table>
</div>

<div id="stats" class="panel" role="tabpanel" aria-labelledby="tab-stats">
<div class="stats-grid">
<div class="stat-card"><div class="val" id="st-avg-sess">--</div><div class="lbl">Avg session</div></div>
<div class="stat-card"><div class="val" id="st-avg-day">--</div><div class="lbl">Avg daily</div></div>
<div class="stat-card"><div class="val" id="st-total-sess">--</div><div class="lbl">Total sessions</div></div>
<div class="stat-card"><div class="val" id="st-days">--</div><div class="lbl">Days tracked</div></div>
</div>
<h3 style="margin:12px 0 4px;font-size:0.9em;color:#aaa">Daily play time</h3>
<div id="daily-chart" class="bar-chart"></div>
<h3 style="margin:12px 0 4px;font-size:0.9em;color:#aaa">Time by mode</h3>
<div id="mode-chart" class="bar-chart"></div>
<div id="suggest-box" class="suggest-box" style="display:none">
<div class="title">Suggested limits</div>
<div id="suggest-text"></div>
<button class="btn btn-primary" onclick="applySuggestions()" style="margin-top:8px">Apply suggestions</button>
</div>
</div>

<div id="security" class="panel" role="tabpanel" aria-labelledby="tab-security">
<div class="field"><label>Web UI PIN (empty = no login required)</label><input class="input-field" type="password" id="ui_pin" maxlength="8" inputmode="numeric" placeholder="e.g. 1234"></div>
<div class="field"><label>OTA token (empty = no token required)</label><input class="input-field" type="text" id="ota_token" placeholder="e.g. my-secret-token"></div>
<button class="btn btn-save" onclick="saveSecurity()">Save</button>
<div id="sec-msg" class="msg"></div>
</div>

<div id="debug" class="panel" role="tabpanel" aria-labelledby="tab-debug">
<div class="toggle"><input type="checkbox" id="dbg-serial" onchange="toggleDebug()"><label>Log inputs to serial (~2x/sec)</label></div>
<p style="font-size:0.75em;color:#666;margin-top:8px">Prints button, switch, and encoder state to the serial console.</p>
<h3 style="margin:16px 0 6px;color:#e94560;font-size:0.9em">Last boot</h3>
<div id="boot-log"><p style="font-size:0.8em;color:#666">Open this tab to load.</p></div>
</div>

<div id="nfc" class="panel" role="tabpanel" aria-labelledby="tab-nfc">
<h3 style="color:#e94560;font-size:0.95em;margin-bottom:8px">Card Sets</h3>
<div id="nfc-sets"><p style="font-size:0.8em;color:#666">Loading...</p></div>
<h3 style="margin-top:16px;color:#e94560;font-size:0.95em;margin-bottom:8px">Provisioning</h3>
<div id="nfc-prov">
<div class="field"><label>Card set</label><select class="input-field" id="prov-mode" onchange="provPopulateCards()"></select></div>
<div class="field"><label>Card</label><select class="input-field" id="prov-card"></select><p style="font-size:0.75em;color:#666;margin-top:4px">Choose &quot;&mdash; launcher &mdash;&quot; to write a mode-launcher tag with no card id.</p></div>
<button class="btn btn-primary" id="prov-write-btn" onclick="provStart()">Write next tag</button>
<button class="btn" id="prov-cancel-btn" onclick="provCancel()" style="display:none;background:#555;color:#fff;margin-top:8px">Cancel</button>
<div id="prov-status" style="text-align:center;padding:10px;margin-top:10px;border-radius:6px;background:#16213e;font-size:0.85em;color:#aaa">Loading status&hellip;</div>
</div>
<h3 style="margin-top:16px;color:#e94560;font-size:0.95em;margin-bottom:8px">UID Cache</h3>
<div id="nfc-cache"><p style="font-size:0.8em;color:#666">Loading...</p></div>
</div>

<div id="wifi" class="panel" role="tabpanel" aria-labelledby="tab-wifi">
<div id="wifi-status" style="font-size:0.85em;color:#aaa;margin-bottom:10px"></div>
<div class="field"><label>Mode</label><select class="input-field" id="wifi_mode"><option value="ap">Access Point</option><option value="sta">Connect to network</option></select></div>
<div class="field"><label>SSID</label><input class="input-field" type="text" id="wifi_ssid"></div>
<div class="field"><label>Password</label><input class="input-field" type="password" id="wifi_pass" placeholder="Type a new password to replace"><p id="wifi-pass-hint" style="font-size:0.75em;color:#666;margin-top:4px"></p></div>
<div class="field"><label>Hostname</label><input class="input-field" type="text" id="hostname" placeholder="bodn"><p style="font-size:0.75em;color:#666;margin-top:4px">Device will be reachable at <span id="hostname-preview">bodn</span>.local</p></div>
<button class="btn btn-primary" onclick="saveWifi()">Save &amp; Reboot</button>
<div id="wifi-msg" class="msg"></div>
</div>

<script>
function show(id){
var tab=document.getElementById('tab-'+id);
document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
document.querySelectorAll('.tab').forEach(t=>{t.classList.remove('active');t.setAttribute('aria-selected','false');t.tabIndex=-1;});
document.getElementById(id).classList.add('active');
if(tab){tab.classList.add('active');tab.setAttribute('aria-selected','true');tab.tabIndex=0;tab.scrollIntoView({block:'nearest',inline:'nearest'});}
if(id==='history')loadHistory();
if(id==='stats')loadStats();
if(id==='debug')loadBootLog();
if(id==='nfc')loadNFC();
if(id==='wifi')loadWifiStatus();
}
document.querySelector('.tabs').addEventListener('keydown',function(e){
var tabs=Array.prototype.slice.call(document.querySelectorAll('.tab'));
var i=tabs.indexOf(document.activeElement);
if(i<0)return;
var next=-1;
if(e.key==='ArrowRight')next=(i+1)%tabs.length;
else if(e.key==='ArrowLeft')next=(i-1+tabs.length)%tabs.length;
else if(e.key==='Home')next=0;
else if(e.key==='End')next=tabs.length-1;
if(next>=0){e.preventDefault();tabs[next].focus();tabs[next].click();}
});
function updRv(el,id,suf){document.getElementById(id).textContent=el.value+suf}
function badgeClass(s){
if(s==='PLAYING')return'playing';
if(s==='WARN_5'||s==='WARN_2'||s==='WINDDOWN')return'warn';
if(s==='SLEEPING')return'sleeping';
if(s==='COOLDOWN')return'cooldown';
if(s==='LOCKDOWN')return'lockdown';
return'idle';
}
function fmtTime(s){
var m=Math.floor(s/60),sec=s%60;
return m+':'+(sec<10?'0':'')+sec;
}
async function refresh(){
try{
var r=await fetch('/api/status');var d=await r.json();
var b=document.getElementById('state-badge');
b.textContent=d.state;b.className='badge '+badgeClass(d.state);
document.getElementById('s-count').textContent=d.sessions_today;
document.getElementById('s-max').textContent=d.sessions_remaining+d.sessions_today;
var tLbl=document.getElementById('time-label'),tBar=document.getElementById('time-bar'),tText=document.getElementById('time-text');
var inBreak=(d.state==='WINDDOWN'||d.state==='SLEEPING'||d.state==='COOLDOWN');
if(inBreak&&d.cooldown_remaining_s>0){
var totS=(d.break_s||0)+30;
var cpct=totS>0?Math.round(d.cooldown_remaining_s*100/totS):0;
tLbl.textContent='Break remaining';
tBar.style.width=cpct+'%';tBar.style.background='#8e44ad';
tText.textContent=fmtTime(d.cooldown_remaining_s);
}else{
var pct=0,maxS=d.max_session_s||1200;
if(d.time_remaining_s>0)pct=Math.round(d.time_remaining_s*100/maxS);
tLbl.textContent='Time remaining';
tBar.style.width=pct+'%';tBar.style.background='';
tText.textContent=d.time_remaining_s>0?fmtTime(d.time_remaining_s):'--';
}
var rb=document.getElementById('resume-btn');if(rb)rb.style.display=inBreak?'':'none';
document.getElementById('lockdown-btn').textContent=d.state==='LOCKDOWN'?'Unlock':'Lockdown';
var tc=document.getElementById('temp-card'),tv=document.getElementById('temp-val');
var bc=document.getElementById('bat-card'),bv=document.getElementById('bat-val'),bl=document.getElementById('bat-lbl');
var sa=document.getElementById('safety-alert');sa.style.display='none';
if(d.temp_c!=null){tc.style.display='';tv.textContent=d.temp_c+'\u00b0C';
var ts=d.temp_status||'ok';
tc.style.borderLeft=ts==='critical'?'4px solid #e94560':ts==='warn'?'4px solid #f39c12':'4px solid #27ae60';
tv.style.color=ts==='critical'?'#e94560':ts==='warn'?'#f39c12':'#27ae60';
}else{tc.style.display='none'}
if(d.bat_pct!=null){bc.style.display='';bv.textContent=d.bat_pct+'%';
bl.textContent='Battery'+(d.bat_charging?' \u26a1':'');
var bs=d.bat_status||'ok';
bc.style.borderLeft=bs==='critical'||bs==='shutdown'?'4px solid #e94560':bs==='warn'?'4px solid #f39c12':'4px solid #27ae60';
bv.style.color=bs==='critical'||bs==='shutdown'?'#e94560':bs==='warn'?'#f39c12':'#27ae60';
}else if(d.bat_charging){bc.style.display='';bv.textContent='USB';bv.style.color='#27ae60';
bl.textContent='Battery \u26a1';bc.style.borderLeft='4px solid #27ae60';
}else{bc.style.display='none'}
var alert='';
if((d.temp_status||'')==='critical')alert='\u26a0 OVERHEATING \u2014 LEDs and backlight disabled. Let the device cool down.';
else if((d.bat_status||'')==='critical')alert='\u26a0 BATTERY CRITICAL \u2014 LEDs disabled. Please charge the device now.';
else if((d.bat_status||'')==='shutdown')alert='\u26a0 BATTERY EMPTY \u2014 Device is sleeping to protect the battery. Plug in charger.';
else if((d.temp_status||'')==='warn')alert='\u26a0 Device is warm. LED brightness reduced.';
else if((d.bat_status||'')==='warn')alert='\u26a0 Battery is getting low. LED brightness reduced.';
if(alert){sa.style.display='block';sa.textContent=alert;
var sev=(d.temp_status==='critical'||d.bat_status==='critical'||d.bat_status==='shutdown');
sa.style.background=sev?'#e94560':'#f39c12';sa.style.color=sev?'#fff':'#000';}
}catch(e){}
}
async function loadSettings(){
try{
var r=await fetch('/api/settings');var d=await r.json();
// Build timezone select options
var tzEl=document.getElementById('tz_offset');
if(tzEl&&!tzEl.options.length){for(var o=-12;o<=14;o++){var op=document.createElement('option');op.value=o;op.textContent='UTC'+(o>=0?'+':'')+o;tzEl.appendChild(op);}}
['max_session_min','max_sessions_day','break_min','volume'].forEach(function(k){
var el=document.getElementById(k);if(el&&d[k]!=null)el.value=d[k];
});
['quiet_start','quiet_end','wifi_ssid','wifi_mode','ui_pin','ota_token','language','hostname'].forEach(function(k){
var el=document.getElementById(k);if(el&&d[k]!=null)el.value=d[k]||'';
});
if(tzEl&&d.tz_offset!=null)tzEl.value=d.tz_offset;
var se=document.getElementById('sessions-enabled');if(se)se.checked=d.sessions_enabled!==false;
var ae=document.getElementById('audio_enabled');if(ae)ae.value=d.audio_enabled===false?'false':'true';
updRv(document.getElementById('max_session_min'),'rv-sess',' min');
updRv(document.getElementById('max_sessions_day'),'rv-maxs','');
updRv(document.getElementById('break_min'),'rv-brk',' min');
updRv(document.getElementById('volume'),'rv-vol','%');
// Load modes (visibility + limits) from API
try{
var mr=await fetch('/api/modes');var modes=await mr.json();
var vc=document.getElementById('mode-vis');
var mc=document.getElementById('mode-limits');
var ml=d.mode_limits||{};
if(vc)vc.innerHTML='';
if(mc)mc.innerHTML='';
modes.forEach(function(m){
// Visibility toggle
if(vc){
var row=document.createElement('div');row.className='toggle';
var cb=document.createElement('input');cb.type='checkbox';cb.id='mv_'+m.name;cb.checked=m.visible;
var lb=document.createElement('label');lb.textContent=m.name;
row.appendChild(cb);row.appendChild(lb);vc.appendChild(row);
}
// Per-mode limit
if(mc){
var row2=document.createElement('div');row2.className='mode-row';
var v=ml[m.name];var val=(v!=null&&v!==undefined)?v:'';
row2.innerHTML='<label>'+m.name+'</label><input type="number" min="0" id="ml_'+m.name+'" value="'+val+'" placeholder="--"><span class="hint">min</span>';
mc.appendChild(row2);
}
});
window._modeNames=modes.map(function(m){return m.name});
}catch(e){window._modeNames=[];}
}catch(e){}
}
async function saveSettings(){
var body={};
['max_session_min','max_sessions_day','break_min'].forEach(function(k){
body[k]=parseInt(document.getElementById(k).value);
});
['quiet_start','quiet_end'].forEach(function(k){
var v=document.getElementById(k).value.trim();
body[k]=v||null;
});
var langEl=document.getElementById('language');if(langEl)body.language=langEl.value;
var tzEl2=document.getElementById('tz_offset');if(tzEl2)body.tz_offset=parseInt(tzEl2.value);
var aeEl=document.getElementById('audio_enabled');if(aeEl)body.audio_enabled=aeEl.value==='true';
var volEl=document.getElementById('volume');if(volEl)body.volume=parseInt(volEl.value);
// Collect hidden modes
var hidden=[];
(window._modeNames||[]).forEach(function(m){
var cb=document.getElementById('mv_'+m);
if(cb&&!cb.checked)hidden.push(m);
});
body.hidden_modes=hidden;
// Collect per-mode limits
var ml={};
(window._modeNames||[]).forEach(function(m){
var el=document.getElementById('ml_'+m);
if(el&&el.value!=='')ml[m]=parseInt(el.value);
});
body.mode_limits=ml;
var r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
var msg=document.getElementById('limits-msg');
msg.className=r.ok?'msg ok':'msg err';
msg.textContent=r.ok?'Saved!':'Error';
setTimeout(function(){msg.className='msg'},2000);
}
async function toggleLockdown(){
await fetch('/api/lockdown',{method:'POST'});
refresh();
}
async function resumeNow(){
await fetch('/api/resume',{method:'POST'});
refresh();
}
async function loadHistory(){
try{
var r=await fetch('/api/history');var d=await r.json();
var tb=document.getElementById('hist-body');tb.innerHTML='';
d.reverse();
d.forEach(function(s){
var tr=document.createElement('tr');
var mn={'free_play':'Free','sound_mixer':'Mixer','recorder':'Rec','sequencer':'Seq'};
tr.innerHTML='<td>'+s.date+'</td><td>'+(s.start_time||'--')+'</td><td>'+(s.duration_min||'--')+' min</td><td>'+(mn[s.mode]||s.mode||'--')+'</td>';
tb.appendChild(tr);
});
if(!d.length)tb.innerHTML='<tr><td colspan="4" style="text-align:center;color:#aaa">No sessions yet</td></tr>';
}catch(e){}
}
var _suggestions={};
async function loadStats(){
try{
var r=await fetch('/api/stats');var d=await r.json();
document.getElementById('st-avg-sess').textContent=d.avg_session_min+' min';
document.getElementById('st-avg-day').textContent=d.avg_daily_play_min+' min';
document.getElementById('st-total-sess').textContent=d.total_sessions;
document.getElementById('st-days').textContent=d.total_days;
// Daily chart
var dc=document.getElementById('daily-chart');dc.innerHTML='';
var maxM=0;(d.daily_totals||[]).forEach(function(t){if(t.play_min>maxM)maxM=t.play_min});
(d.daily_totals||[]).forEach(function(t){
var pct=maxM>0?Math.round(t.play_min*100/maxM):0;
dc.innerHTML+='<div class="bar-row"><span class="bar-label">'+t.date.slice(5)+'</span><div class="bar-fill" style="width:'+pct+'%"></div><span class="bar-val">'+t.play_min+'m / '+t.sessions+'x</span></div>';
});
// Mode chart
var mc=document.getElementById('mode-chart');mc.innerHTML='';
var mb=d.mode_breakdown||{};var maxMo=0;for(var k in mb)if(mb[k]>maxMo)maxMo=mb[k];
var names={'free_play':'Free Play','sound_mixer':'Sound Mixer','recorder':'Recorder','sequencer':'Sequencer'};
for(var k in mb){
var pct=maxMo>0?Math.round(mb[k]*100/maxMo):0;
mc.innerHTML+='<div class="bar-row"><span class="bar-label">'+(names[k]||k)+'</span><div class="bar-fill" style="width:'+pct+'%;background:#2980b9"></div><span class="bar-val">'+mb[k]+' min</span></div>';
}
// Suggestions
var sg=d.suggestions||{};_suggestions=sg;
var sb=document.getElementById('suggest-box');
var st=document.getElementById('suggest-text');
if(d.total_sessions>0){
sb.style.display='block';
st.innerHTML='Session: <b>'+sg.max_session_min+' min</b>, Max/day: <b>'+sg.max_sessions_day+'</b>';
if(sg.note)st.innerHTML+='<br><span style="color:#f39c12;font-size:0.85em">'+sg.note+'</span>';
}else{sb.style.display='none'}
}catch(e){}
}
async function applySuggestions(){
if(!_suggestions.max_session_min)return;
var body={max_session_min:_suggestions.max_session_min,max_sessions_day:_suggestions.max_sessions_day};
await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
loadSettings();loadStats();
}
async function saveSecurity(){
var body={ui_pin:document.getElementById('ui_pin').value.trim(),
ota_token:document.getElementById('ota_token').value.trim()};
var r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
var msg=document.getElementById('sec-msg');
msg.className=r.ok?'msg ok':'msg err';
msg.textContent=r.ok?'Saved!':'Error';
setTimeout(function(){msg.className='msg'},2000);
if(r.ok&&body.ui_pin){document.cookie='bodn_pin='+body.ui_pin+';path=/;SameSite=Strict'}
}
async function loadWifiStatus(){
var st=document.getElementById('wifi-status');
var hint=document.getElementById('wifi-pass-hint');
var pw=document.getElementById('wifi_pass');
var ssid=document.getElementById('wifi_ssid');
try{
var r=await fetch('/api/wifi/status');var d=await r.json();
var parts=[];
if(d.connected){
parts.push('Currently connected to <b style="color:#27ae60">'+(d.live_ssid||'(unknown SSID)')+'</b>');
if(d.ip&&d.ip!=='0.0.0.0')parts.push('IP <code>'+d.ip+'</code>');
}else if((d.wifi_mode||'')==='ap'){
parts.push('Running in <b>Access Point</b> mode');
if(d.ip&&d.ip!=='0.0.0.0')parts.push('IP <code>'+d.ip+'</code>');
}else{
parts.push('Not connected');
}
if(st)st.innerHTML=parts.join(' &middot; ');
// If no SSID is stored but the radio is associated, prefill the input
// with the live SSID so the user doesn't have to re-type it.
if(ssid&&!ssid.value&&d.live_ssid)ssid.value=d.live_ssid;
if(hint)hint.textContent=d.wifi_pass_set?'Password is stored. Leave blank to keep it; type a new one to replace.':'No password stored.';
if(pw)pw.placeholder=d.wifi_pass_set?'Leave blank to keep current password':'Enter network password';
}catch(e){if(st)st.textContent='WiFi status unavailable.';}
}
async function saveWifi(){
var hn=document.getElementById('hostname').value.trim()||'bodn';
var body={wifi_mode:document.getElementById('wifi_mode').value,
wifi_ssid:document.getElementById('wifi_ssid').value,
hostname:hn};
// Only send wifi_pass when the user actually typed a new one. Sending an
// empty string would wipe the stored password on the device.
var pw=document.getElementById('wifi_pass').value;
if(pw)body.wifi_pass=pw;
var r=await fetch('/api/wifi',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
var msg=document.getElementById('wifi-msg');
msg.className=r.ok?'msg ok':'msg err';
msg.textContent=r.ok?'Saved! Rebooting...':'Error';
}
async function toggleSessions(){
var el=document.getElementById('sessions-enabled');
var body={sessions_enabled:el.checked};
await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
refresh();
}
async function toggleDebug(){
var r=await fetch('/api/debug/toggle',{method:'POST'});
var d=await r.json();
document.getElementById('dbg-serial').checked=d.debug_input;
}
async function loadDebugState(){
try{
var r=await fetch('/api/settings');var d=await r.json();
document.getElementById('dbg-serial').checked=!!d.debug_input;
}catch(e){}
}
async function loadBootLog(){
var el=document.getElementById('boot-log');
try{
var r=await fetch('/api/boot-log');var d=await r.json();
if(d.error){el.innerHTML='<p style="font-size:0.8em;color:#666">'+d.error+'</p>';return;}
var col={'ok':'#27ae60','warn':'#f39c12','fail':'#e94560','skip':'#555'};
var html='<div style="display:flex;gap:6px;flex-wrap:wrap;margin:8px 0">';
(d.steps||[]).forEach(function(s){
var c=col[s.result]||'#555';
html+='<span style="padding:3px 8px;border-radius:10px;font-size:0.78em;font-weight:bold;background:'+c+'33;color:'+c+';border:1px solid '+c+'">'+s.key+' '+s.result+'</span>';
});
html+='</div><table style="width:100%;border-collapse:collapse;font-size:0.8em;margin-top:4px"><tbody>';
if(d.ts){var dt=new Date(d.ts*1000);html+='<tr><td style="color:#aaa;padding:3px 6px;width:80px">Time</td><td style="padding:3px 6px">'+dt.toLocaleString()+'</td></tr>';}
if(d.ip)html+='<tr><td style="color:#aaa;padding:3px 6px">IP</td><td style="padding:3px 6px">'+d.ip+'</td></tr>';
if(d.bat)html+='<tr><td style="color:#aaa;padding:3px 6px">Battery</td><td style="padding:3px 6px">'+d.bat+'</td></tr>';
if(d.free_kb!=null)html+='<tr><td style="color:#aaa;padding:3px 6px">Free RAM</td><td style="padding:3px 6px">'+d.free_kb+' KB</td></tr>';
if(d.i2c&&d.i2c.length)html+='<tr><td style="color:#aaa;padding:3px 6px">I2C</td><td style="padding:3px 6px">'+d.i2c.join(', ')+'</td></tr>';
if(d.hw){var hws=[];for(var k in d.hw){hws.push('<span style="color:'+(d.hw[k]?'#27ae60':'#e94560')+'">'+k+':'+(d.hw[k]?'\u2713':'\u2717')+'</span>')}html+='<tr><td style="color:#aaa;padding:3px 6px">Hardware</td><td style="padding:3px 6px">'+hws.join('&nbsp;&nbsp;')+'</td></tr>';}
html+='</tbody></table>';
el.innerHTML=html;
}catch(e){el.innerHTML='<p style="font-size:0.8em;color:#e94560">Failed to load boot log.</p>';}
}
var provSets={};
var provPollTimer=null;
async function loadNFC(){
try{
var r=await fetch('/api/nfc/sets');var sets=await r.json();
var el=document.getElementById('nfc-sets');
if(sets.error){el.innerHTML='<p style="color:#e94560">'+sets.error+'</p>';}
else if(!sets.length){el.innerHTML='<p style="color:#aaa;font-size:0.8em">No card sets found on SD card.</p>';}
else{
var html='';
sets.forEach(function(s){
html+='<div style="background:#16213e;border-radius:8px;padding:10px;margin:6px 0">';
html+='<strong style="color:#e94560">'+s.mode+'</strong>';
html+=' <span style="color:#aaa;font-size:0.8em">v'+s.version+' &middot; '+s.card_count+' cards &middot; '+s.dimensions.join(', ')+'</span>';
html+='</div>';
});
el.innerHTML=html;
}
await provLoadSets(sets);
}catch(e){document.getElementById('nfc-sets').innerHTML='<p style="color:#e94560;font-size:0.8em">Error loading card sets.</p>';}
try{
var cr=await fetch('/api/nfc/cache');var cache=await cr.json();
var ce=document.getElementById('nfc-cache');
var keys=Object.keys(cache);
if(!keys.length){ce.innerHTML='<p style="color:#aaa;font-size:0.8em">Empty (no tags scanned yet).</p>';}
else{
var html='<table style="width:100%;border-collapse:collapse;font-size:0.8em"><thead><tr><th style="text-align:left;padding:4px;color:#aaa">UID</th><th style="text-align:left;padding:4px;color:#aaa">Mode</th><th style="text-align:left;padding:4px;color:#aaa">Card</th></tr></thead><tbody>';
keys.forEach(function(uid){html+='<tr><td style="font-family:monospace;padding:4px">'+uid+'</td><td style="padding:4px">'+cache[uid].mode+'</td><td style="padding:4px">'+cache[uid].id+'</td></tr>';});
html+='</tbody></table>';
ce.innerHTML=html;
}
}catch(e){}
provStartPolling();
}
async function provLoadSets(sets){
var sel=document.getElementById('prov-mode');
if(!sel)return;
if(!sets||!sets.length){sel.innerHTML='<option value="">(no card sets found)</option>';document.getElementById('prov-card').innerHTML='';return;}
if(sel.options.length===sets.length&&sel.value)return;
sel.innerHTML='';
sets.forEach(function(s){var o=document.createElement('option');o.value=s.mode;o.textContent=s.mode+' ('+s.card_count+')';sel.appendChild(o);});
await provPopulateCards();
}
async function provPopulateCards(){
var mode=document.getElementById('prov-mode').value;
var cardSel=document.getElementById('prov-card');
if(!mode){cardSel.innerHTML='';return;}
if(!provSets[mode]){
try{var r=await fetch('/api/nfc/set/'+encodeURIComponent(mode));provSets[mode]=await r.json();}
catch(e){cardSel.innerHTML='<option value="">(error loading set)</option>';return;}
}
var cs=provSets[mode];
cardSel.innerHTML='';
var launch=document.createElement('option');launch.value='';launch.textContent='— launcher —';cardSel.appendChild(launch);
(cs.cards||[]).forEach(function(c){var o=document.createElement('option');o.value=c.id;var lbl=c.label_sv||c.label_en||c.id;o.textContent=c.id+' ('+lbl+')';cardSel.appendChild(o);});
}
function provRender(s){
var el=document.getElementById('prov-status');
var btn=document.getElementById('prov-write-btn');
var cancel=document.getElementById('prov-cancel-btn');
if(!el)return;
var msg='',colour='#16213e',txt='#aaa';
if(s.reader_available===false){msg='NFC reader not detected.';colour='#16213e';txt='#e94560';btn.disabled=true;}
else if(s.owner==='device'){msg='Device screen is using the reader. Close it on the device to write from here.';colour='#16213e';txt='#f39c12';btn.disabled=true;}
else if(s.state==='armed'||s.state==='writing'){msg=(s.state==='armed'?'Hold a tag on the reader…':'Writing…')+' ('+s.mode+(s.card_id?'/'+s.card_id:'')+')';colour='#0f3460';txt='#e94560';btn.disabled=true;}
else if(s.state==='ok'){msg='Tag written: '+s.mode+(s.card_id?'/'+s.card_id:'')+'.';colour='#1a3a1a';txt='#27ae60';btn.disabled=false;}
else if(s.state==='fail'){msg='Write failed'+(s.error?': '+s.error:'')+'.';colour='#3a1a1a';txt='#e94560';btn.disabled=false;}
else{msg='Ready.';colour='#16213e';txt='#aaa';btn.disabled=false;}
el.style.background=colour;el.style.color=txt;el.textContent=msg;
cancel.style.display=(s.owner==='web'&&(s.state==='armed'||s.state==='writing'))?'block':'none';
}
async function provPoll(){
try{var r=await fetch('/api/nfc/provision/status');var s=await r.json();provRender(s);}
catch(e){/* drop a single poll */}
}
function provStartPolling(){
if(provPollTimer)return;
provPoll();
provPollTimer=setInterval(provPoll,1000);
}
async function provStart(){
var mode=document.getElementById('prov-mode').value;
var card=document.getElementById('prov-card').value;
if(!mode)return;
var body={mode:mode};
if(card)body.card_id=card;
try{
var r=await fetch('/api/nfc/provision/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
if(!r.ok){var err=await r.json().catch(function(){return{error:'HTTP '+r.status};});provRender({reader_available:true,state:'fail',error:err.error||('HTTP '+r.status)});return;}
}catch(e){provRender({reader_available:true,state:'fail',error:String(e)});return;}
provPoll();
}
async function provCancel(){
try{await fetch('/api/nfc/provision/cancel',{method:'POST'});}catch(e){}
provPoll();
}
var hnEl=document.getElementById('hostname');
if(hnEl)hnEl.addEventListener('input',function(){document.getElementById('hostname-preview').textContent=this.value.trim()||'bodn'});
loadSettings();loadDebugState();refresh();setInterval(refresh,5000);
</script>
</body>
</html>
"""


def _precompute_gzip(s):
    """Compress a string once at import time for HTTP Content-Encoding: gzip.

    WiFi + TCP drain() is the dominant cost when a parent opens the web UI
    while the child is playing; sending ~10 KB instead of ~35 KB cuts radio
    time and lets the async loop yield back to game tasks faster. Runs once
    at module import — later requests just send these bytes.
    """
    import io

    raw = s.encode("utf-8") if isinstance(s, str) else s
    try:
        import deflate  # MicroPython >= 1.21

        buf = io.BytesIO()
        d = deflate.DeflateIO(buf, deflate.GZIP)
        # Stock ESP32 MicroPython at ROM_LEVEL_EXTRA_FEATURES ships the
        # deflate module for decompression only; DeflateIO.write doesn't
        # exist. Fall back to serving raw HTML — the caller checks for
        # None and picks the uncompressed branch.
        d.write(raw)
        d.close()
        return buf.getvalue()
    except (ImportError, AttributeError):
        try:
            import gzip  # CPython (host tests)

            return gzip.compress(raw)
        except ImportError:
            return None


HTML_GZ = _precompute_gzip(HTML)
