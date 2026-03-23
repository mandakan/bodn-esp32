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
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;max-width:480px;margin:0 auto;padding:16px}
h1{text-align:center;color:#e94560;margin-bottom:8px;font-size:1.5em}
.tabs{display:flex;gap:4px;margin-bottom:16px}
.tab{flex:1;padding:10px;text-align:center;background:#16213e;border:none;color:#aaa;border-radius:8px 8px 0 0;cursor:pointer;font-size:0.9em}
.tab.active{background:#0f3460;color:#e94560;font-weight:bold}
.panel{display:none;background:#0f3460;border-radius:0 0 8px 8px;padding:16px}
.panel.active{display:block}
.badge{display:inline-block;padding:4px 12px;border-radius:12px;font-weight:bold;font-size:0.9em}
.badge.playing{background:#27ae60;color:#fff}
.badge.idle{background:#555;color:#ccc}
.badge.warn{background:#f39c12;color:#000}
.badge.sleeping{background:#2980b9;color:#fff}
.badge.lockdown{background:#e94560;color:#fff}
.badge.cooldown{background:#8e44ad;color:#fff}
.stat{margin:12px 0}
.stat label{display:block;font-size:0.8em;color:#aaa;margin-bottom:4px}
.stat .val{font-size:1.3em;font-weight:bold}
.progress{background:#16213e;border-radius:6px;height:20px;overflow:hidden;margin-top:4px}
.progress .bar{height:100%;background:#27ae60;transition:width 1s}
.field{margin:14px 0}
.field label{display:block;font-size:0.85em;color:#aaa;margin-bottom:6px}
.field input[type=range]{width:100%}
.field .rv{float:right;font-weight:bold;color:#e94560}
.toggle{display:flex;align-items:center;gap:10px;margin:14px 0}
.toggle input{width:20px;height:20px}
.btn{display:block;width:100%;padding:12px;margin-top:12px;border:none;border-radius:8px;font-size:1em;cursor:pointer}
.btn-danger{background:#e94560;color:#fff}
.btn-primary{background:#2980b9;color:#fff}
.btn-save{background:#27ae60;color:#fff}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #16213e;font-size:0.85em}
th{color:#aaa}
.input-field{width:100%;padding:8px;background:#16213e;border:1px solid #333;color:#e0e0e0;border-radius:6px;margin-top:4px}
.msg{text-align:center;padding:8px;margin:8px 0;border-radius:6px;display:none}
.msg.ok{display:block;background:#27ae60;color:#fff}
.msg.err{display:block;background:#e94560;color:#fff}
.bar-chart{margin:12px 0}
.bar-row{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:0.85em}
.bar-row .bar-label{width:70px;color:#aaa;text-align:right}
.bar-row .bar-fill{height:16px;background:#e94560;border-radius:3px;min-width:2px}
.bar-row .bar-val{color:#e0e0e0;font-size:0.8em}
.stat-card{background:#16213e;border-radius:8px;padding:12px;margin:8px 0;text-align:center}
.stat-card .val{font-size:1.5em;font-weight:bold;color:#e94560}
.stat-card .lbl{font-size:0.75em;color:#aaa;margin-top:2px}
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.suggest-box{background:#1a3a1a;border:1px solid #27ae60;border-radius:8px;padding:12px;margin:12px 0}
.suggest-box .title{color:#27ae60;font-weight:bold;margin-bottom:6px}
.mode-row{display:flex;align-items:center;gap:8px;margin:8px 0}
.mode-row label{flex:1;font-size:0.85em;color:#aaa}
.mode-row input{width:70px;padding:6px;background:#16213e;border:1px solid #333;color:#e0e0e0;border-radius:6px;text-align:center}
.mode-row .hint{font-size:0.7em;color:#666}
</style>
</head>
<body>
<h1>Bodn</h1>
<div class="tabs">
<button class="tab active" onclick="show('dash')">Dashboard</button>
<button class="tab" onclick="show('limits')">Limits</button>
<button class="tab" onclick="show('history')">History</button>
<button class="tab" onclick="show('stats')">Stats</button>
<button class="tab" onclick="show('wifi')">WiFi</button>
<button class="tab" onclick="show('security')">Security</button>
<button class="tab" onclick="show('debug')">Debug</button>
</div>

<div id="dash" class="panel active">
<div style="text-align:center;margin-bottom:12px">
<span id="state-badge" class="badge idle">IDLE</span>
</div>
<div class="stat"><label>Sessions today</label><span id="s-count" class="val">0</span> / <span id="s-max" class="val">5</span></div>
<div class="stat"><label>Time remaining</label><div class="progress"><div id="time-bar" class="bar" style="width:0%"></div></div><div id="time-text" style="text-align:center;font-size:0.85em;margin-top:4px">--</div></div>
<div class="toggle"><input type="checkbox" id="sessions-enabled" checked onchange="toggleSessions()"><label>Session limits enabled</label></div>
<div id="temp-card" class="stat-card" style="display:none"><div class="val" id="temp-val">--</div><div class="lbl">Temperature</div></div>
<button class="btn btn-danger" id="lockdown-btn" onclick="toggleLockdown()">Lockdown</button>
</div>

<div id="limits" class="panel">
<div class="field"><label>Session length <span class="rv" id="rv-sess">20 min</span></label><input type="range" id="max_session_min" min="1" max="60" value="20" oninput="updRv(this,'rv-sess',' min')"></div>
<div class="field"><label>Max sessions/day <span class="rv" id="rv-maxs">5</span></label><input type="range" id="max_sessions_day" min="1" max="20" value="5" oninput="updRv(this,'rv-maxs','')"></div>
<div class="field"><label>Break between sessions <span class="rv" id="rv-brk">15 min</span></label><input type="range" id="break_min" min="1" max="60" value="15" oninput="updRv(this,'rv-brk',' min')"></div>
<div class="field"><label>Quiet start (HH:MM, empty=off)</label><input class="input-field" type="text" id="quiet_start" placeholder="21:00"></div>
<div class="field"><label>Quiet end (HH:MM)</label><input class="input-field" type="text" id="quiet_end" placeholder="07:00"></div>
<div class="field"><label>Device language</label><select id="language" class="input-field"><option value="sv">Svenska</option><option value="en">English</option></select></div>
<h3 style="margin-top:16px;color:#e94560;font-size:0.95em">Per-mode limits</h3>
<p style="font-size:0.75em;color:#666;margin:4px 0">Minutes per session. Empty = use global. 0 = unlimited.</p>
<div id="mode-limits"></div>
<button class="btn btn-save" onclick="saveSettings()">Save</button>
<div id="limits-msg" class="msg"></div>
</div>

<div id="history" class="panel">
<table><thead><tr><th>Date</th><th>Start</th><th>Duration</th><th>Mode</th></tr></thead><tbody id="hist-body"></tbody></table>
</div>

<div id="stats" class="panel">
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

<div id="security" class="panel">
<div class="field"><label>Web UI PIN (empty = no login required)</label><input class="input-field" type="password" id="ui_pin" maxlength="8" inputmode="numeric" placeholder="e.g. 1234"></div>
<div class="field"><label>OTA token (empty = no token required)</label><input class="input-field" type="text" id="ota_token" placeholder="e.g. my-secret-token"></div>
<button class="btn btn-save" onclick="saveSecurity()">Save</button>
<div id="sec-msg" class="msg"></div>
</div>

<div id="debug" class="panel">
<div class="toggle"><input type="checkbox" id="dbg-serial" onchange="toggleDebug()"><label>Log inputs to serial (~2x/sec)</label></div>
<p style="font-size:0.75em;color:#666;margin-top:8px">Prints button, switch, and encoder state to the serial console.</p>
</div>

<div id="wifi" class="panel">
<div class="field"><label>Mode</label><select class="input-field" id="wifi_mode"><option value="ap">Access Point</option><option value="sta">Connect to network</option></select></div>
<div class="field"><label>SSID</label><input class="input-field" type="text" id="wifi_ssid"></div>
<div class="field"><label>Password</label><input class="input-field" type="password" id="wifi_pass"></div>
<button class="btn btn-primary" onclick="saveWifi()">Save &amp; Reboot</button>
<div id="wifi-msg" class="msg"></div>
</div>

<script>
function show(id){
document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
document.getElementById(id).classList.add('active');
event.target.classList.add('active');
if(id==='history')loadHistory();
if(id==='stats')loadStats();
}
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
var pct=0,maxS=d.max_session_s||1200;
if(d.time_remaining_s>0)pct=Math.round(d.time_remaining_s*100/maxS);
document.getElementById('time-bar').style.width=pct+'%';
document.getElementById('time-text').textContent=d.time_remaining_s>0?fmtTime(d.time_remaining_s):'--';
document.getElementById('lockdown-btn').textContent=d.state==='LOCKDOWN'?'Unlock':'Lockdown';
var tc=document.getElementById('temp-card'),tv=document.getElementById('temp-val');
if(d.temp_c!=null){tc.style.display='';tv.textContent=d.temp_c+'\u00b0C';
tc.style.borderLeft=d.temp_status==='critical'?'4px solid #e94560':d.temp_status==='warn'?'4px solid #f39c12':'4px solid #27ae60';
}else{tc.style.display='none'}
}catch(e){}
}
async function loadSettings(){
try{
var r=await fetch('/api/settings');var d=await r.json();
['max_session_min','max_sessions_day','break_min'].forEach(function(k){
var el=document.getElementById(k);if(el&&d[k]!=null)el.value=d[k];
});
['quiet_start','quiet_end','wifi_ssid','wifi_pass','wifi_mode','ui_pin','ota_token','language'].forEach(function(k){
var el=document.getElementById(k);if(el&&d[k]!=null)el.value=d[k]||'';
});
var se=document.getElementById('sessions-enabled');if(se)se.checked=d.sessions_enabled!==false;
updRv(document.getElementById('max_session_min'),'rv-sess',' min');
updRv(document.getElementById('max_sessions_day'),'rv-maxs','');
updRv(document.getElementById('break_min'),'rv-brk',' min');
// Load mode limits
var ml=d.mode_limits||{};
var mc=document.getElementById('mode-limits');
if(mc){mc.innerHTML='';
var modes=['free_play','sound_mixer','recorder','sequencer'];
var names={'free_play':'Free Play','sound_mixer':'Sound Mixer','recorder':'Recorder','sequencer':'Sequencer'};
modes.forEach(function(m){
var row=document.createElement('div');row.className='mode-row';
var v=ml[m];var val=(v!=null&&v!==undefined)?v:'';
row.innerHTML='<label>'+names[m]+'</label><input type="number" min="0" id="ml_'+m+'" value="'+val+'" placeholder="--"><span class="hint">min</span>';
mc.appendChild(row);
});}
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
var ml={};
['free_play','sound_mixer','recorder','sequencer'].forEach(function(m){
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
async function saveWifi(){
var body={wifi_mode:document.getElementById('wifi_mode').value,
wifi_ssid:document.getElementById('wifi_ssid').value,
wifi_pass:document.getElementById('wifi_pass').value};
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
loadSettings();loadDebugState();refresh();setInterval(refresh,5000);
</script>
</body>
</html>
"""
