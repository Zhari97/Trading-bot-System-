const esc=v=>String(v??'—').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const date=v=>v?new Date(v).toLocaleString('it-IT'):'—';
const badge=v=>`<span class="badge ${String(v).replace(' ','-')}">${esc(v)}</span>`;

function card(m){
  return `<article class="card"><h3>${esc(m.pair)}</h3><div class="price">${esc(m.price)}</div>${badge(m.classification)} <b>${esc(m.direction)}</b>${m.counter_trend?'<p class="warn">⚠ CONTRO-TREND</p>':''}<div class="metrics"><div>SCORE<b>${esc(m.score)}/100</b></div><div>CONFLUENZA<b>${esc(m.confluence)}%</b></div><div>RSI<b>${esc(m.rsi)}</b></div><div>TREND<b>${esc(m.categories?.trend)}</b></div><div>MOMENTUM<b>${esc(m.categories?.momentum)}</b></div><div>SETUP<b>${esc(m.categories?.setup)}</b></div><div>PESO LONG<b>${esc(m.weights?.long)}</b></div><div>PESO SHORT<b>${esc(m.weights?.short)}</b></div></div><small>${date(m.timestamp)}</small></article>`;
}

function graph(h){
  if(!Array.isArray(h)||!h.length)return;
  document.querySelector('#chart').innerHTML=`<polyline class="line" points="${h.slice(-60).map((x,i)=>`${i*(700/Math.max(1,h.slice(-60).length-1))},${170-x.score*1.6}`).join(' ')}"/>`;
}

async function refresh(){
  const [s,m,h,x]=await Promise.all(['/api/status','/api/markets','/api/history','/api/signals'].map(u=>fetch(u).then(r=>{
    if(!r.ok) throw new Error(`${u}: HTTP ${r.status}`);
    return r.json();
  })));

  // API responses are already the stored values: markets is an object,
  // history/signals are arrays. Keep compatibility with wrapped responses too.
  const markets=Array.isArray(m)?m:(m?.markets&&typeof m.markets==='object'?m.markets:m);
  const history=Array.isArray(h)?h:(Array.isArray(h?.history)?h.history:[]);
  const signals=Array.isArray(x)?x:(Array.isArray(x?.signals)?x.signals:[]);
  const a=Object.values(markets||{});

  const timeframe=s?.timeframe_minutes!=null?`${s.timeframe_minutes}m`:'—';
  document.querySelector('#timeframe').textContent=timeframe;
  document.querySelector('#updated').textContent=date(s?.updated_at);

  if(a.length){
    document.querySelector('#markets').innerHTML=a.map(card).join('');
    const q=a[0];
    document.querySelector('#engine').innerHTML=`Direzione: <b>${esc(q.direction)}</b><br>Trend: <b>${esc(q.categories?.trend)}</b> · Momentum: <b>${esc(q.categories?.momentum)}</b> · Setup: <b>${esc(q.categories?.setup)}</b><br>Score: <b>${esc(q.score)}</b> · Confluenza: <b>${esc(q.confluence)}%</b><br>GUARD-RAIL V2.2: <b>${esc(q.guard_rail?.status)}</b> ${esc(q.guard_rail?.reason)}`;
  } else {
    document.querySelector('#markets').innerHTML='<p>Nessuna analisi persistita.</p>';
    document.querySelector('#engine').innerHTML='In attesa di analisi reale.';
  }

  document.querySelector('#telegram').innerHTML=`Configurato: <b>${s?.telegram?.configured?'SI':'NO'}</b><br>Ultimo alert: <b>${esc(s?.telegram?.last_alert?.telegram||'Non disponibile')}</b>`;
  document.querySelector('#signals').innerHTML=signals.map(q=>`<tr><td>${date(q.timestamp)}</td><td>${esc(q.pair)}</td><td>${badge(q.classification)}</td><td>${esc(q.direction)}</td><td>${esc(q.score)}</td><td>${esc(q.confluence)}%</td><td>${esc(q.guard_rail?.status)}</td><td>${esc(q.telegram)}</td></tr>`).join('')||'<tr><td colspan="8">Nessun dato persistito.</td></tr>';
  graph(history);
}

refresh().catch(err=>{
  console.error('Dashboard refresh error',err);
  document.querySelector('#engine').textContent='Errore caricamento dati dashboard.';
  document.querySelector('#telegram').textContent='Errore caricamento dati dashboard.';
});
setInterval(()=>refresh().catch(err=>console.error('Dashboard refresh error',err)),30000);
