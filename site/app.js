/* Oil Sentinel: zero-CDN, accessible, no API keys. Figures sourced from generated data.json. */
'use strict';
const $ = id => document.getElementById(id);
const state = { snapshot:null, series:'us_crude', view:'level', chart:null, worker:null, loadedAt:0 };
const num = (v,d=2) => typeof v==='number'&&Number.isFinite(v)?v.toFixed(d):'—';
const sign = (v,d=2) => typeof v==='number'&&Number.isFinite(v)?(v>0?'+':'')+v.toFixed(d):'—';
const niceDate = s => {if(!s)return '—';const d=new Date(s.slice(0,10)+'T12:00:00Z');return isNaN(d)?'—':d.toLocaleDateString('en-US',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});};
const weekday = s => {if(!s)return '—';const d=new Date(s.slice(0,10)+'T12:00:00Z');return isNaN(d)?'—':d.toLocaleDateString('en-US',{day:'numeric',month:'short',timeZone:'UTC'});};
const escapeHtml = input => String(input??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = raw => /^https:\/\//i.test(String(raw||''))?String(raw):'#';
const diffClass = v => typeof v!=='number'?'':v>0?'negative':v<0?'positive':'neutral';
const changeText = value => typeof value === 'number'?`${sign(value,3)}M bbl this week`:'Change unavailable';
function setText(id,text){const el=$(id);if(el)el.textContent=text;}
function setClassText(id,text,cls){const el=$(id);if(el){el.textContent=text;el.classList.remove('positive','negative','neutral');if(cls)el.classList.add(cls);}}
function showTab(tab){document.querySelectorAll('.tab').forEach(b=>{const on=b.dataset.tab===tab;b.classList.toggle('active',on);b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;});document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id==='panel-'+tab));}

const RESUME_REFRESH_MS=60*1000;
const BUILD=document.querySelector('meta[name="build"]')?.content||'dev';
function registerWorker(){
  const local=location.hostname==='localhost'||location.hostname==='127.0.0.1';
  if(!('serviceWorker'in navigator)||(location.protocol!=='https:'&&!local))return;
  const hadController=!!navigator.serviceWorker.controller;
  let reloading=false;
  // A new deploy activates a new worker; reload once so page, scripts and styles all match it.
  navigator.serviceWorker.addEventListener('controllerchange',()=>{
    if(!hadController||reloading)return;
    reloading=true;location.reload();
  });
  navigator.serviceWorker.register('./sw.js',{updateViaCache:'none'}).then(reg=>{state.worker=reg;reg.update().catch(()=>{});}).catch(()=>{});
}

const MIN_SPIN_MS=600;
const TOAST_MS=3200;
function toast(text,kind){
  const t=$('toast');if(!t)return;
  t.textContent=text;t.className='toast show'+(kind?' '+kind:'');
  clearTimeout(toast.timer);toast.timer=setTimeout(()=>{t.className='toast';},TOAST_MS);
}
function updatedText(iso){
  const d=new Date(iso||'');if(isNaN(d))return 'unknown time';
  const mins=Math.round((Date.now()-d.getTime())/60000);
  if(mins<1)return 'just now';if(mins<60)return `${mins} min ago`;
  const hrs=Math.round(mins/60);if(hrs<24)return `${hrs} h ago`;
  return d.toLocaleDateString('en-US',{day:'numeric',month:'short'});
}

async function loadData(manual=false){
  const refresh=$('refresh');
  if(refresh.disabled)return;
  refresh.disabled=true;refresh.classList.add('spinning');refresh.setAttribute('aria-busy','true');
  const started=Date.now(),before=state.snapshot?.generated_at;
  if(manual)state.worker?.update().catch(()=>{});
  let ok=true,offline=false;
  try{
    const response=await fetch(new URL('./data.json',window.location.href),{cache:'no-store'});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const data=await response.json();
    if(data.schema_version!==1)throw new Error('Unsupported snapshot schema');
    state.snapshot=data;
    offline=response.headers.get('X-Oil-Sentinel-Offline')==='1';
    if(!offline)state.loadedAt=Date.now();
  }catch(error){
    ok=false;
    const n=$('notice');
    if(state.snapshot){
      // Keep what is on screen; just say the refresh failed.
      n.textContent='Could not reach the server, so this is the last data loaded. Tap Refresh to try again.';n.className='notice error';
    }else{
      n.textContent='No data could be loaded. Check your connection and tap Refresh.';n.className='notice error';
      setText('asof-date','Unavailable');setText('data-age','Feed not reachable');setText('fc-track','Waiting for data.');setText('fc-week','UNAVAILABLE');
    }
  }
  if(ok)render();
  if(offline){const n=$('notice');n.textContent='You are offline, so this is the last data saved on this phone. Tap Refresh when you are back online.';n.className='notice error';}
  // Keep the spinner visible long enough to see that something happened.
  await new Promise(r=>setTimeout(r,Math.max(0,MIN_SPIN_MS-(Date.now()-started))));
  refresh.disabled=false;refresh.classList.remove('spinning');refresh.removeAttribute('aria-busy');
  if(!manual)return;
  if(!ok||offline)toast('No connection. Showing the last data saved.','error');
  else if(before&&before!==state.snapshot.generated_at)toast('New data loaded.','good');
  else toast(`Up to date. Last server update ${updatedText(state.snapshot.generated_at)}.`);
}

function render(){
  const s=state.snapshot; if(!s)return;
  const e=s.eia||{}, series=e.series||{}, c=series.cushing, us=series.us_crude;
  setText('asof-date',niceDate(us?.as_of));
  const days=us?.as_of?Math.floor((Date.now()-new Date(us.as_of+'T23:59:59Z').getTime())/86400000):null;
  setText('data-age',days===null?'No verified date':days<0?'As reported':`${days} day${days===1?'':'s'} since week end`);
  const n=$('notice');
  if(s.snapshot_mode==='demo') {n.className='notice demo';n.textContent='DEMO / HISTORICAL SNAPSHOT — figures are from the week ending 30 October 2026, NOT current inventory. Deploy the app and run its refresh workflow for updated figures.';}
  else if(e.status!=='live') {n.className='notice error';n.textContent='PARTIAL / STALE — official EIA data could not be verified on this build. The figures below may be old. No live inventory conclusion should be drawn.';}
  else if(s.satellite?.status!=='live') {n.className='notice';n.textContent='EIA stocks refreshed. Satellite scene discovery is temporarily unavailable; any displayed imagery may be older.';}
  else if(days!==null && days>12) {n.className='notice demo';n.textContent='Official EIA data looks old. Check the source publication date before using it; clicking Refresh checks the last published snapshot, not the EIA server directly.';}
  else {n.className='notice';n.textContent=`Latest automated snapshot: ${niceDate((s.generated_at||'').slice(0,10))}. Stock figures represent week ending ${niceDate(us?.as_of)}. Satellite scenes are dated independently.`;}
  setText('us-value',num(us?.mb,2));setClassText('us-change',changeText(us?.week_change_mb),diffClass(us?.week_change_mb));
  setText('cushing-value',num(c?.mb,2));setClassText('cushing-change',changeText(c?.week_change_mb),diffClass(c?.week_change_mb));
  const sat=s.satellite||{}, scene=(sat.scenes||[])[0];
  setText('sat-date',scene?weekday(scene.date):'Unavailable');
  setText('sat-cloud',scene?`Scene cloud ${scene.cloud_percent==null?'unknown':num(scene.cloud_percent,1)+'%'}`:'No pass found');
  const m=s.market||{};
  if(m.status==='available'){
    setText('wti-price','$'+num(m.price_usd));setText('wti-contract',(m.contract||'Futures')+' · '+(m.session_date||''));
    setClassText('wti-change',typeof m.change_pct==='number'?`${sign(m.change_pct)}% · indicative`:'Indicative, delayed quote',m.change_pct>0?'positive':m.change_pct<0?'negative':null);
  }else{setText('wti-price','—');setText('wti-contract','No optional market feed');setText('wti-change','Check your broker for live USOIL');}
  const signal=e.status==='live'?e.signal:{key:'unavailable',title:'No live confirmation',message:'Underlying data could not be refreshed.'};
  setText('signal-title',signal?.title||'No validated signal');setText('signal-explainer',signal?.message||'');
  setText('signal-icon',['loosening','lean-loosening'].includes(signal?.key)?'↑':['tightening','lean-tightening'].includes(signal?.key)?'↓':'≈');
  const chip=$('signal-chip'); chip.textContent=signal?.key==='unavailable'?'UNVERIFIED':['loosening','lean-loosening'].includes(signal?.key)?'STOCK BUILD':['tightening','lean-tightening'].includes(signal?.key)?'STOCK DRAW':'MIXED';
  chip.className='chip'+(['loosening','lean-loosening'].includes(signal?.key)?' risk':signal?.key==='mixed'?' caution':'');
  for(const [id,key] of [['q-us','us_crude'],['q-cushing','cushing'],['q-gasoline','gasoline'],['q-distillate','distillate']]){
    const val=series[key]?.week_change_mb;setClassText(id,typeof val==='number'?sign(val,3)+'M':'—',diffClass(val));
  }
  renderForecast();renderNextReport();drawChart();renderScenes();renderBrief();renderProvenance();compareExpectation();
}

const MINUTE_MS=60*1000;
function untilText(ms){
  const mins=Math.round(ms/MINUTE_MS);
  if(mins<60)return `in ${mins} min`;
  const hrs=Math.floor(mins/60),rest=mins%60;
  if(hrs<48)return `in ${hrs} h${rest?` ${rest} min`:''}`;
  return `in ${Math.round(hrs/24)} days`;
}
function renderNextReport(){
  const s=state.snapshot||{},nxt=s.next_report||{};
  const at=new Date(nxt.release_utc||'');
  if(isNaN(at)){setText('next-when','Not known yet');setText('next-detail','');return;}
  const local=at.toLocaleString(undefined,{weekday:'short',day:'numeric',month:'short',hour:'numeric',minute:'2-digit'});
  setText('next-when',local);
  const why=nxt.holiday?` · moved for ${nxt.holiday}`:'';
  const week=`covers week ending ${weekday(nxt.week_ending)}`;
  const left=at.getTime()-Date.now();
  const status=left>0?untilText(left):'out now · the app picks it up within the hour';
  setText('next-detail',`${status} · ${week}${why} · ${nxt.release_eastern||''}`);
}

function renderForecast(){
  const s=state.snapshot||{},fc=s.forecast||{};
  const rangeText=f=>f&&typeof f.low_mb==='number'?`likely ${sign(f.low_mb,1)} to ${sign(f.high_mb,1)}M`:'';
  const valueText=f=>f&&typeof f.change_mb==='number'?`${sign(f.change_mb,1)}M`:'—';
  const live=fc.status==='live'&&s.snapshot_mode!=='demo';
  setText('fc-week',live&&fc.us_crude?.target_week?'FOR '+weekday(fc.us_crude.target_week).toUpperCase():'UNAVAILABLE');
  setClassText('fc-us',live?valueText(fc.us_crude):'—',live?diffClass(fc.us_crude?.change_mb):null);setText('fc-us-range',live?rangeText(fc.us_crude):'');
  setClassText('fc-cu',live?valueText(fc.cushing):'—',live?diffClass(fc.cushing?.change_mb):null);setText('fc-cu-range',live?rangeText(fc.cushing):'');
  setClassText('fc-out',live?valueText(fc.us_outlook):'—',live?diffClass(fc.us_outlook?.change_mb):null);setText('fc-out-range',live&&fc.us_outlook?`through ${weekday(fc.us_outlook.through_week)} · ${rangeText(fc.us_outlook)}`:'');
  if(!live){setText('fc-track',s.snapshot_mode==='demo'?'Forecasts appear once the live workflow has run.':(fc.reason||'Forecast unavailable on this build.'));setText('fc-last','');return;}
  const us=fc.us_crude.backtest,cu=fc.cushing.backtest,yr=d=>String(d||'').slice(0,4);
  setText('fc-track',`Tested on ${us.weeks} unseen weeks (${yr(us.from)}–${yr(us.to)}): typical miss US ±${num(us.mae_mb,1)}M (a no-change guess misses ±${num(us.naive_mae_mb,1)}M), Cushing ±${num(cu.mae_mb,2)}M (vs ±${num(cu.naive_mae_mb,2)}M). Right direction on moves over 1M: US ${Math.round(us.direction_hit*100)}%, Cushing ${Math.round(cu.direction_hit*100)}%. Ranges held ${Math.round(us.band_coverage*100)}% of weeks.`);
  const lw=fc.us_crude.last_week,lc=fc.cushing.last_week;
  setText('fc-last',lw&&typeof lw.forecast_mb==='number'?`Last report (${weekday(lw.week)}): US forecast ${sign(lw.forecast_mb,1)}M, actual ${sign(lw.actual_mb,1)}M · Cushing forecast ${sign(lc?.forecast_mb,1)}M, actual ${sign(lc?.actual_mb,1)}M.`:'');
}

function drawChart(){
  const series=state.snapshot?.eia?.series?.[state.series];
  setText('chart-title',state.series==='cushing'?'Cushing, Oklahoma':'US commercial crude');
  if(!state.chart)state.chart=new ForecastChart($('trend-chart'),$('chart-readout'),$('chart-table-body'));
  const fc=state.snapshot?.forecast;
  const live=fc?.status==='live'&&state.snapshot?.snapshot_mode!=='demo';
  state.chart.update(series,live?fc[state.series]:null,state.view);
  document.querySelector('.chart-legend').classList.toggle('no-forecast',!live);
  const hist=(series?.history||[]).slice(-27);
  setText('chart-range',hist.length>1?niceDate(hist[1].date)+' → '+(live&&fc[state.series]?.target_week?niceDate(fc[state.series].target_week)+' (forecast)':niceDate(hist[hist.length-1].date)):'No history');
}

function renderScenes(){
  const sat=state.snapshot?.satellite||{};const scenes=Array.isArray(sat.scenes)?sat.scenes:[];
  const gallery=$('scene-gallery'),list=$('scene-list');
  if(!scenes.length){gallery.innerHTML='<div class="empty-sat">No verified satellite acquisitions in the last 65 days. Try the Copernicus browser directly.</div>';list.innerHTML='<p class="small-muted">No passes available.</p>';return;}
  const selected=scenes.filter(s=>s.image).slice(0,2);
  // If cropping failed, preserve real dates but show clear placeholders, not synthetic imagery.
  const featured=selected.length?selected:scenes.slice(0,2);
  gallery.innerHTML=featured.map(scene=>{
    const image=scene.image&&/^images\/cushing-\d{4}-\d{2}-\d{2}\.png$/.test(scene.image)?`<img src="${scene.image}" alt="Actual Sentinel-2 crop near Cushing acquired ${escapeHtml(scene.date)}" loading="lazy">`:`<span>No downloadable crop available for this pass.<br>Open the full scene in Copernicus Browser.</span>`;
    return `<article class="scene-card"><div class="scene-photo">${image}</div><div class="scene-info"><strong>${escapeHtml(niceDate(scene.date))}</strong><p>Sentinel-2 · scene cloud ${scene.cloud_percent==null?'not reported':num(scene.cloud_percent,1)+'%'} · 10m ground sample</p><a href="${safeUrl(scene.copernicus_url)}" target="_blank" rel="noopener noreferrer">Inspect in Copernicus ↗</a></div></article>`;
  }).join('');
  list.innerHTML=scenes.slice(0,8).map(scene=>`<div class="data-row"><span>${escapeHtml(niceDate(scene.date))}<span class="muted"> · clouds ${scene.cloud_percent==null?'unknown':num(scene.cloud_percent,1)+'%'}</span></span><a href="${safeUrl(scene.stac_url||scene.copernicus_url)}" target="_blank" rel="noopener noreferrer">Metadata ↗</a></div>`).join('');
}

function briefText(){
  const s=state.snapshot||{},e=s.eia||{},sr=e.series||{},us=sr.us_crude,cu=sr.cushing;
  if(!us||!cu)return 'Oil Sentinel. EIA inventory values are unavailable; no inference can be made.';
  const prefix=s.snapshot_mode==='demo'?'Oil Sentinel demo, historical figures only. ':e.status!=='live'?'Oil Sentinel; inventory feed might be stale. ':'Oil Sentinel inventory update. ';
  const sig=e.status==='live'?e.signal?.title:'No live confirmation';
  const sat=s.satellite?.latest_scene_date;
  return `${prefix}EIA week ending ${us.as_of}. US commercial crude ${num(us.mb)} million barrels, weekly change ${sign(us.week_change_mb)} million. Cushing ${num(cu.mb)} million barrels, weekly change ${sign(cu.week_change_mb)} million. Inventory assessment: ${sig||'unavailable'}. ${forecastSentence(s)}${sat?`Latest available Sentinel 2 scene dated ${sat}.`:'No recent Sentinel 2 scene confirmed.'} Inventory figures alone do not tell us when to trade WTI.`;
}
function forecastSentence(s){
  const fc=s.forecast||{};
  if(fc.status!=='live'||s.snapshot_mode==='demo'||!fc.us_crude||!fc.cushing)return '';
  const us=fc.us_crude,cu=fc.cushing;
  return `Forecast for the report covering week ending ${us.target_week}: US crude ${sign(us.change_mb,1)} million, likely between ${sign(us.low_mb,1)} and ${sign(us.high_mb,1)}. Cushing ${sign(cu.change_mb,1)} million. `;
}
function renderBrief(){
  const loc=window.location;
  const hosted=loc.protocol==='https:'||loc.protocol==='http:';
  const url=hosted?new URL('./briefing.txt',loc.href).href:'Publish on GitHub Pages to obtain your HTTPS briefing URL.';
  setText('briefing-url',url);setText('briefing-preview',briefText());
  $('copy-url').disabled=!hosted;
  setText('shortcut-status',hosted?'The text file refreshes whenever the free automation successfully republishes the dashboard.':'This local preview is for inspection. Siri needs a hosted HTTPS address.');
}
function renderProvenance(){
  const s=state.snapshot||{};
  const times=(s.eia?.series)||{};
  const lines=[`Mode: ${s.snapshot_mode||'unknown'}`,`Generated UTC: ${s.generated_at||'unknown'}`,`EIA status: ${s.eia?.status||'unavailable'}`,`US stock week: ${times.us_crude?.as_of||'unavailable'}`,`Cushing stock week: ${times.cushing?.as_of||'unavailable'}`,`Satellite catalogue: ${s.satellite?.status||'unavailable'}`,`Latest satellite scene: ${s.satellite?.latest_scene_date||'unavailable'}`,`Forecast: ${s.forecast?.status||'unavailable'}`,`App build: ${BUILD}`,`WTI reference: ${s.market?.status||'unavailable'}`,`Errors: ${(s.errors||[]).join('; ')||'none'}`,`Data refresh: automatic GitHub Action; click Refresh re-reads published file.`];
  setText('provenance',lines.join('\n'));
}
function compareExpectation(){
  const e=state.snapshot?.eia||{},actual=e.series?.us_crude?.week_change_mb;
  const input=$('expectation').value.trim();
  if(!input){setText('expect-result','Enter a forecasted inventory CHANGE (not total stocks). Negative = expected draw.');return;}
  const exp=Number(input);
  if(!Number.isFinite(exp)||typeof actual!=='number'){setText('expect-result','Cannot compare: invalid expectation or missing official release.');return;}
  if(e.status!=='live'||state.snapshot.snapshot_mode==='demo'){setText('expect-result',`Historical illustration only: EIA ${sign(actual,3)}M vs expected ${sign(exp,3)}M. Not today's release.`);return;}
  const surprise=actual-exp;
  const word=Math.abs(surprise)<.05?'Essentially in line with expectation':surprise>0?'More inventory than expected — potentially bearish WTI':'Less inventory than expected — potentially bullish WTI';
  setText('expect-result',`${word}. Actual ${sign(actual,3)}M; forecast ${sign(exp,3)}M; surprise ${sign(surprise,3)}M barrels.`);
}
async function copyText(text){
  try{await navigator.clipboard.writeText(text);return true;}catch(e){
    try{const box=document.createElement('textarea');box.value=text;box.style.position='fixed';box.style.opacity='0';document.body.appendChild(box);box.select();const result=document.execCommand('copy');box.remove();return result;}catch(e2){return false;}
  }
}
function initialize(){
  document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>showTab(b.dataset.tab)));
  document.querySelectorAll('.toggle-btn').forEach(b=>b.addEventListener('click',()=>{
    const group=b.dataset.series?'series':'view';
    if(group==='series')state.series=b.dataset.series;else state.view=b.dataset.view;
    document.querySelectorAll(`.toggle-btn[data-${group}]`).forEach(x=>{const on=x===b;x.classList.toggle('selected',on);x.setAttribute('aria-pressed',String(on));});
    drawChart();
  }));
  document.querySelector('.tabs').addEventListener('keydown',e=>{
    if(e.key!=='ArrowRight'&&e.key!=='ArrowLeft')return;
    const tabs=[...document.querySelectorAll('.tab')],i=tabs.findIndex(t=>t.classList.contains('active'));
    const next=tabs[(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length];showTab(next.dataset.tab);next.focus();
  });
  $('refresh').addEventListener('click',()=>loadData(true));
  try{const saved=localStorage.getItem('oilSentinelExpectation');if(saved!==null)$('expectation').value=saved;}catch(e){}
  $('expectation').addEventListener('input',compareExpectation);
  $('save-expect').addEventListener('click',()=>{try{localStorage.setItem('oilSentinelExpectation',$('expectation').value);}catch(e){}compareExpectation();});
  $('copy-url').addEventListener('click',async()=>{if($('copy-url').disabled)return;const ok=await copyText($('briefing-url').textContent);$('copy-url').textContent=ok?'Copied ✓':'Copy failed';});
  $('copy-brief').addEventListener('click',async()=>{const ok=await copyText(briefText());$('copy-brief').textContent=ok?'Copied ✓':'Copy failed';});
  registerWorker();
  // Home-screen apps resume instead of reloading: check for fresh data and a new version on return.
  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState!=='visible')return;
    if(Date.now()-state.loadedAt>RESUME_REFRESH_MS)loadData();
    state.worker?.update().catch(()=>{});
  });
  loadData();
  setInterval(()=>{if(state.snapshot)renderNextReport();},MINUTE_MS);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initialize);else initialize();
