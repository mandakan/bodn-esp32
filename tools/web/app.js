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
if(e.key==='ArrowRight'||e.key==='ArrowDown')next=(i+1)%tabs.length;
else if(e.key==='ArrowLeft'||e.key==='ArrowUp')next=(i-1+tabs.length)%tabs.length;
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
if(d.temp_c!=null){tc.style.display='';tv.textContent=d.temp_c+'°C';
var ts=d.temp_status||'ok';
tc.style.borderLeft=ts==='critical'?'4px solid #e94560':ts==='warn'?'4px solid #f39c12':'4px solid #27ae60';
tv.style.color=ts==='critical'?'#e94560':ts==='warn'?'#f39c12':'#27ae60';
}else{tc.style.display='none'}
if(d.bat_pct!=null){bc.style.display='';bv.textContent=d.bat_pct+'%';
bl.textContent='Battery'+(d.bat_charging?' ⚡':'');
var bs=d.bat_status||'ok';
bc.style.borderLeft=bs==='critical'||bs==='shutdown'?'4px solid #e94560':bs==='warn'?'4px solid #f39c12':'4px solid #27ae60';
bv.style.color=bs==='critical'||bs==='shutdown'?'#e94560':bs==='warn'?'#f39c12':'#27ae60';
}else if(d.bat_charging){bc.style.display='';bv.textContent='USB';bv.style.color='#27ae60';
bl.textContent='Battery ⚡';bc.style.borderLeft='4px solid #27ae60';
}else{bc.style.display='none'}
var alert='';
if((d.temp_status||'')==='critical')alert='⚠ OVERHEATING — LEDs and backlight disabled. Let the device cool down.';
else if((d.bat_status||'')==='critical')alert='⚠ BATTERY CRITICAL — LEDs disabled. Please charge the device now.';
else if((d.bat_status||'')==='shutdown')alert='⚠ BATTERY EMPTY — Device is sleeping to protect the battery. Plug in charger.';
else if((d.temp_status||'')==='warn')alert='⚠ Device is warm. LED brightness reduced.';
else if((d.bat_status||'')==='warn')alert='⚠ Battery is getting low. LED brightness reduced.';
if(alert){sa.style.display='block';sa.textContent=alert;
var sev=(d.temp_status==='critical'||d.bat_status==='critical'||d.bat_status==='shutdown');
sa.style.background=sev?'#e94560':'#f39c12';sa.style.color=sev?'#fff':'#000';}
}catch(e){}
}
async function loadSettings(){
try{
var r=await fetch('/api/settings');var d=await r.json();
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
try{
var mr=await fetch('/api/modes');var modes=await mr.json();
var vc=document.getElementById('mode-vis');
var mc=document.getElementById('mode-limits');
var ml=d.mode_limits||{};
if(vc)vc.innerHTML='';
if(mc)mc.innerHTML='';
modes.forEach(function(m){
if(vc){
var row=document.createElement('div');row.className='toggle';
var cb=document.createElement('input');cb.type='checkbox';cb.id='mv_'+m.name;cb.checked=m.visible;
var lb=document.createElement('label');lb.textContent=m.name;
row.appendChild(cb);row.appendChild(lb);vc.appendChild(row);
}
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
var hidden=[];
(window._modeNames||[]).forEach(function(m){
var cb=document.getElementById('mv_'+m);
if(cb&&!cb.checked)hidden.push(m);
});
body.hidden_modes=hidden;
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
var dc=document.getElementById('daily-chart');dc.innerHTML='';
var maxM=0;(d.daily_totals||[]).forEach(function(t){if(t.play_min>maxM)maxM=t.play_min});
(d.daily_totals||[]).forEach(function(t){
var pct=maxM>0?Math.round(t.play_min*100/maxM):0;
dc.innerHTML+='<div class="bar-row"><span class="bar-label">'+t.date.slice(5)+'</span><div class="bar-fill" style="width:'+pct+'%"></div><span class="bar-val">'+t.play_min+'m / '+t.sessions+'x</span></div>';
});
var mc=document.getElementById('mode-chart');mc.innerHTML='';
var mb=d.mode_breakdown||{};var maxMo=0;for(var k in mb)if(mb[k]>maxMo)maxMo=mb[k];
var names={'free_play':'Free Play','sound_mixer':'Sound Mixer','recorder':'Recorder','sequencer':'Sequencer'};
for(var k in mb){
var pct=maxMo>0?Math.round(mb[k]*100/maxMo):0;
mc.innerHTML+='<div class="bar-row"><span class="bar-label">'+(names[k]||k)+'</span><div class="bar-fill" style="width:'+pct+'%;background:#2980b9"></div><span class="bar-val">'+mb[k]+' min</span></div>';
}
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
if(d.hw){var hws=[];for(var k in d.hw){hws.push('<span style="color:'+(d.hw[k]?'#27ae60':'#e94560')+'">'+k+':'+(d.hw[k]?'✓':'✗')+'</span>')}html+='<tr><td style="color:#aaa;padding:3px 6px">Hardware</td><td style="padding:3px 6px">'+hws.join('&nbsp;&nbsp;')+'</td></tr>';}
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
catch(e){}
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
