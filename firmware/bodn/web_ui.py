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
</style>
</head>
<body>
<h1>Bodn</h1>
<div class="tabs">
<button class="tab active" onclick="show('dash')">Dashboard</button>
<button class="tab" onclick="show('limits')">Limits</button>
<button class="tab" onclick="show('history')">History</button>
<button class="tab" onclick="show('wifi')">WiFi</button>
<button class="tab" onclick="show('security')">Security</button>
</div>

<div id="dash" class="panel active">
<div style="text-align:center;margin-bottom:12px">
<span id="state-badge" class="badge idle">IDLE</span>
</div>
<div class="stat"><label>Sessions today</label><span id="s-count" class="val">0</span> / <span id="s-max" class="val">5</span></div>
<div class="stat"><label>Time remaining</label><div class="progress"><div id="time-bar" class="bar" style="width:0%"></div></div><div id="time-text" style="text-align:center;font-size:0.85em;margin-top:4px">--</div></div>
<button class="btn btn-danger" id="lockdown-btn" onclick="toggleLockdown()">Lockdown</button>
</div>

<div id="limits" class="panel">
<div class="field"><label>Session length <span class="rv" id="rv-sess">20 min</span></label><input type="range" id="max_session_min" min="1" max="60" value="20" oninput="updRv(this,'rv-sess',' min')"></div>
<div class="field"><label>Max sessions/day <span class="rv" id="rv-maxs">5</span></label><input type="range" id="max_sessions_day" min="1" max="20" value="5" oninput="updRv(this,'rv-maxs','')"></div>
<div class="field"><label>Break between sessions <span class="rv" id="rv-brk">15 min</span></label><input type="range" id="break_min" min="1" max="60" value="15" oninput="updRv(this,'rv-brk',' min')"></div>
<div class="field"><label>Quiet start (HH:MM, empty=off)</label><input class="input-field" type="text" id="quiet_start" placeholder="21:00"></div>
<div class="field"><label>Quiet end (HH:MM)</label><input class="input-field" type="text" id="quiet_end" placeholder="07:00"></div>
<button class="btn btn-save" onclick="saveSettings()">Save</button>
<div id="limits-msg" class="msg"></div>
</div>

<div id="history" class="panel">
<table><thead><tr><th>Date</th><th>Start</th><th>Duration</th></tr></thead><tbody id="hist-body"></tbody></table>
</div>

<div id="security" class="panel">
<div class="field"><label>Web UI PIN (empty = no login required)</label><input class="input-field" type="password" id="ui_pin" maxlength="8" inputmode="numeric" placeholder="e.g. 1234"></div>
<div class="field"><label>OTA token (empty = no token required)</label><input class="input-field" type="text" id="ota_token" placeholder="e.g. my-secret-token"></div>
<button class="btn btn-save" onclick="saveSecurity()">Save</button>
<div id="sec-msg" class="msg"></div>
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
}catch(e){}
}
async function loadSettings(){
try{
var r=await fetch('/api/settings');var d=await r.json();
['max_session_min','max_sessions_day','break_min'].forEach(function(k){
var el=document.getElementById(k);if(el&&d[k]!=null)el.value=d[k];
});
['quiet_start','quiet_end','wifi_ssid','wifi_pass','wifi_mode','ui_pin','ota_token'].forEach(function(k){
var el=document.getElementById(k);if(el&&d[k]!=null)el.value=d[k]||'';
});
updRv(document.getElementById('max_session_min'),'rv-sess',' min');
updRv(document.getElementById('max_sessions_day'),'rv-maxs','');
updRv(document.getElementById('break_min'),'rv-brk',' min');
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
d.forEach(function(s){
var tr=document.createElement('tr');
tr.innerHTML='<td>'+s.date+'</td><td>'+(s.start_time||'--')+'</td><td>'+(s.duration_min||'--')+' min</td>';
tb.appendChild(tr);
});
if(!d.length)tb.innerHTML='<tr><td colspan="3" style="text-align:center;color:#aaa">No sessions yet</td></tr>';
}catch(e){}
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
loadSettings();refresh();setInterval(refresh,5000);
</script>
</body>
</html>
"""
