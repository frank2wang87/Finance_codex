let state = null;
let refreshing = false;
let editingTransactionId = null;
const $ = (id) => document.getElementById(id);
const fmt = (n, digits = 2) => Number(n || 0).toLocaleString('zh-CN', {minimumFractionDigits: digits, maximumFractionDigits: digits});
const yuan = (n) => `¥ ${fmt(n)}`;
const signedClass = (n) => Number(n) < 0 ? 'negative' : 'positive';
const escapeHtml = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nowLocal = () => {const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0,16)};

async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers: {'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作失败');
  return data;
}

function notice(message, bad = false) {
  const box = $('notice'); box.textContent = message; box.className = `notice ${bad ? 'bad' : 'good'}`;
  clearTimeout(notice.timer); notice.timer = setTimeout(() => box.classList.add('hidden'), 6000);
}

function setState(next) {
  state = next;
  render();
  $('setupModal').classList.toggle('hidden', next.initialized);
}

function render() {
  if (!state) return;
  const p = state.portfolio;
  $('equity').textContent = yuan(p.equity);
  $('contributions').textContent = yuan(p.contributions);
  $('profit').textContent = yuan(p.profit); $('profit').className = `summary-value ${signedClass(p.profit)}`;
  $('returnRate').textContent = `${fmt(p.return_rate)}%`; $('returnRate').className = `summary-value ${signedClass(p.return_rate)}`;
  $('cash').textContent = yuan(p.cash);
  $('interest').textContent = yuan(p.interest);
  $('cashRateText').textContent = `${fmt((state.assets.find(a => a.kind === 'cash')?.annual_rate || 0) * 100)}%`;
  $('cashRateForm').elements.rate.value = (state.assets.find(a => a.kind === 'cash')?.annual_rate || 0) * 100;
  renderSelects(); renderPositions(); renderAllocation(); renderTransactions(); renderCharts(); renderDaily();
}

function renderPositions() {
  const assets = Object.fromEntries(state.assets.map(a => [a.id, a]));
  const rows = state.portfolio.positions.filter(x => assets[x.id]?.is_active || x.quantity > 0);
  const cashPrincipal = state.portfolio.cash - state.portfolio.interest;
  const cashRow = `<tr class="cash-position"><td><div class="asset-name">余额宝</div><div class="muted">CASH · 未投资资金 · 模拟年化 ${escapeHtml($('cashRateText').textContent)}</div></td>
    <td>—</td><td>—</td><td>—</td><td><b>${yuan(state.portfolio.cash)}</b><div class="muted">本金 ${yuan(cashPrincipal)}</div></td>
    <td class="${signedClass(state.portfolio.interest)}">${yuan(state.portfolio.interest)}</td><td>—</td>
    <td class="${signedClass(state.portfolio.interest)}"><b>${yuan(state.portfolio.interest)}</b><div class="muted">模拟累计利息</div></td><td>—</td><td>—</td></tr>`;
  $('positionRows').innerHTML = cashRow + rows.map(x => `<tr>
    <td><div class="asset-name">${escapeHtml(x.name)}</div><div class="muted">${escapeHtml(x.code)}${x.code === 'Au9999' ? ' · 元/克' : ''}${assets[x.id]?.is_active ? '' : ' · 已取消关注（仍持有）'}</div></td>
    <td>${fmt(x.quantity, 4)}</td><td>${x.quantity ? fmt(x.average_cost, 4) : '—'}</td>
    <td><b>${x.price == null ? '—' : fmt(x.price, x.code === 'Au9999' ? 2 : 4)}</b><div class="muted">${escapeHtml(x.quote_source)}${x.quote_time ? ' · ' + escapeHtml(x.quote_time.slice(5,16).replace('T',' ')) : ''}</div></td>
    <td><b>${yuan(x.market_value)}</b><div class="muted">成本 ${yuan(x.cost)}</div></td>
    <td class="${signedClass(x.realized)}">${yuan(x.realized)}</td><td class="${signedClass(x.unrealized)}">${yuan(x.unrealized)}</td>
    <td class="${signedClass(x.profit)}"><b>${yuan(x.profit)}</b><div>${fmt(x.return_rate)}%</div></td>
    <td><button class="text-button edit" data-target="${x.id}">${state.targets?.[String(x.id)] == null ? '设置目标' : fmt(state.targets[String(x.id)])+'%'}</button></td>
    <td><button class="text-button" data-${assets[x.id]?.is_active ? 'asset-delete' : 'asset-restore'}="${x.id}">${assets[x.id]?.is_active ? '删除标的' : '恢复关注'}</button></td></tr>`).join('');
}

function displayAIResult(el, content) {
  let obj;
  try {obj=JSON.parse(content.replace(/^\s*```(?:json)?\s*/i,'').replace(/\s*```\s*$/,''))} catch (_) {}
  el.replaceChildren();el.classList.remove('hidden');el.classList.add('ai-cards');
  if(!obj || !Array.isArray(obj.assets)) {const pre=document.createElement('pre');pre.className='ai-result';pre.textContent=content;el.append(pre);return}
  if(obj.summary){const summary=document.createElement('div');summary.className='ai-summary';summary.textContent=String(obj.summary);el.append(summary)}
  for(const item of obj.assets){
    if(!item || typeof item!=='object') continue;
    const card=document.createElement('article');card.className='ai-card';
    const header=document.createElement('div');header.className='ai-card-head';
    const title=document.createElement('strong');title.textContent=[item.name,item.code].filter(x=>typeof x==='string').join(' · ')||'标的分析';
    const decision=document.createElement('span');decision.className='ai-decision';decision.textContent=String(item.decision||'待评估');
    header.append(title,decision);card.append(header);
    for(const [label,key] of [['走势情景','trend'],['条件性买卖节点','levels'],['判断依据','reason'],['风险与缺失数据','risk']]){
      if(item[key] == null) continue;
      const block=document.createElement('div'),heading=document.createElement('b'),body=document.createElement('p');
      heading.textContent=label;body.textContent=Array.isArray(item[key])?item[key].join('；'):String(item[key]);
      block.append(heading,body);card.append(block);
    }
    el.append(card);
  }
  if(!el.children.length){el.textContent=content}
}
function renderDaily() {
  const d=state.daily;if(!d)return;
  $('dailyDate').textContent=d.date+' · 当日';
  $('dailyTotal').textContent=d.total===null?'待补全':yuan(d.total);
  $('dailyNote').textContent=d.missing ? `已知部分 ${yuan(d.known_total)}（含余额宝当日利息），${d.missing} 个标的数据不足；不代表完整总盈亏。` : `含余额宝当日模拟利息 ${yuan(d.cash_interest)}；按昨收、当日报价与交易现金流估算。`;
  $('dailyRows').innerHTML=d.items.length?d.items.map(x=>`<tr><td>${escapeHtml(x.name)} · ${escapeHtml(x.code)}</td><td class="${x.profit===null?'muted':signedClass(x.profit)}">${x.profit===null?'数据不足':yuan(x.profit)}</td><td>${x.prev_close == null?'—':fmt(x.prev_close,4)}</td><td>${escapeHtml(x.quote_time||'—')}</td><td>${escapeHtml(x.reason||'已计算')}</td></tr>`).join(''):'<tr><td colspan="5" class="empty">今日无持仓或买卖记录</td></tr>';
}

function renderAllocation() {
  const colors = ['#56a78b','#f3ac69','#698bc7','#a97bbd','#d5c660','#df7d7c','#6eafb7'];
  const entries = [{name:'余额宝现金', value:state.portfolio.cash}, ...state.portfolio.positions.filter(x => x.market_value > 0).map(x => ({name:x.name,value:x.market_value}))].filter(x => x.value > 0);
  const total = entries.reduce((sum,x) => sum + x.value,0);
  let progress = 0;
  const stops = entries.map((x,i) => {const start = progress; progress += x.value / total * 100; return `${colors[i % colors.length]} ${start}% ${progress}%`});
  $('donut').style.background = stops.length ? `conic-gradient(${stops.join(',')})` : '#e8eeec';
  $('holdingCount').textContent = state.portfolio.positions.filter(x => x.quantity > 0).length;
  $('allocationLegend').innerHTML = entries.length ? entries.map((x,i) => `<div><span class="legend-name"><i style="background:${colors[i % colors.length]}"></i>${escapeHtml(x.name)}</span><span>${fmt(x.value / total * 100,1)}%<b>${yuan(x.value)}</b></span></div>`).join('') : '<div class="muted">尚无资产数据</div>';
}

function renderSelects() {
  const held = new Set(state.portfolio.positions.filter(p => p.quantity > 0).map(p => p.id));
  const securities = state.assets.filter(a => a.kind === 'security' && (a.is_active || held.has(a.id)));
  for (const id of ['tradeAsset','quoteAsset','assetChartSelect']) {
    const el = $(id), old = el.value;
    el.innerHTML = securities.map(a => `<option value="${a.id}">${escapeHtml(a.name)} · ${escapeHtml(a.code)}</option>`).join('');
    if (securities.some(a => String(a.id) === old)) el.value = old;
    else if (id === 'assetChartSelect') {
      const held = state.portfolio.positions.find(p => p.quantity > 0);
      if (held) el.value = String(held.id);
    }
  }
  const filter = $('transactionFilter'), previous = filter.value;
  const historyAssets = state.assets.filter(a => a.kind === 'security' && state.transactions.some(t => t.asset_id === a.id));
  filter.innerHTML = '<option value="all">全部标的</option>' + historyAssets.map(a => `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join('');
  if (previous === 'all' || historyAssets.some(a => String(a.id) === previous)) filter.value = previous;
}

function renderTransactions() {
  const chosen = $('transactionFilter').value || 'all';
  const filtered = state.transactions.filter(t => chosen === 'all' || String(t.asset_id) === chosen).slice().reverse();
  const names = Object.fromEntries(state.assets.map(a => [a.id,a.name]));
  const snapshots = Object.fromEntries(state.portfolio.timeline.filter(p => p.tx_id != null).map(p => [p.tx_id,p]));
  const type = {buy:'买入',sell:'卖出',deposit:'入金',withdraw:'出金'};
  $('txCount').textContent = `共 ${filtered.length} 笔记录`;
  $('transactionRows').innerHTML = filtered.length ? filtered.map(t => {const point = snapshots[t.id], asset = point?.asset_states[String(t.asset_id)]; return `<tr><td>${escapeHtml(t.time.replace('T',' '))}</td><td><span class="tag ${t.type}">${type[t.type]}</span></td>
   <td>${escapeHtml(names[t.asset_id] || '余额宝现金')}</td><td>${t.price ? fmt(t.price,4) : '—'}</td><td>${t.quantity ? fmt(t.quantity,4) : '—'}</td><td>${t.fee ? yuan(t.fee) : '—'}</td>
   <td><b>${yuan(t.amount)}</b></td>
   <td>${asset ? `<b>${fmt(asset.quantity,4)} 份</b><div class="muted ${signedClass(asset.profit)}">收益 ${yuan(asset.profit)} · ${fmt(asset.return_rate)}%</div>` : '—'}</td>
   <td><b>${point ? yuan(point.equity) : '—'}</b><div class="muted ${signedClass(point?.profit)}">收益 ${point ? yuan(point.profit) : '—'} · ${point ? fmt(point.return_rate) : '0.00'}%</div></td>
   <td class="muted note-cell">${escapeHtml(t.note)}</td><td><div class="action-buttons"><button class="text-button edit" data-edit="${t.id}" aria-label="编辑记录">编辑</button><button class="text-button" data-delete="${t.id}" aria-label="删除记录">删除</button></div></td></tr>`}).join('') : '<tr><td colspan="11" class="empty">暂无交易记录</td></tr>';
}

function chart(el, points, key, color = '#2a8b70', unit = '') {
  if (!points.length) {el.innerHTML = '<div class="chart-empty">记录交易后会在这里显示资产曲线</div>'; return}
  const width = Math.max(el.clientWidth, 280), height = el.clientHeight || 275;
  const pad = {left:58,right:18,top:24,bottom:34}, w = width-pad.left-pad.right, h = height-pad.top-pad.bottom;
  const vals = points.map(p => Number(p[key] || 0));
  let min = Math.min(...vals), max = Math.max(...vals);
  const margin = Math.max((max-min)*0.16, Math.abs(max)*0.001, 1);
  min -= margin; max += margin;
  const coords = vals.map((v,i) => [pad.left + (points.length === 1 ? w/2 : i*w/(points.length-1)),pad.top + (max-v)/(max-min)*h]);
  const line = coords.map(([x,y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `M ${coords[0][0]},${pad.top+h} L ${coords.map(([x,y])=>`${x},${y}`).join(' L ')} L ${coords[coords.length-1][0]},${pad.top+h} Z`;
  const grid = [0,1,2,3,4].map(i => {const y = pad.top+i*h/4, value=max-i*(max-min)/4; return `<line x1="${pad.left}" x2="${width-pad.right}" y1="${y}" y2="${y}" stroke="#e9efec"/><text x="${pad.left-10}" y="${y+4}" text-anchor="end" fill="#8b9c97" font-size="11">${unit ? fmt(value,2)+unit : Math.round(value).toLocaleString('zh-CN')}</text>`}).join('');
  const dates = [0,Math.floor((points.length-1)/2),points.length-1].filter((x,i,a)=>a.indexOf(x)===i).map(i => `<text x="${coords[i][0]}" y="${height-8}" text-anchor="middle" fill="#8b9c97" font-size="11">${escapeHtml(points[i].time.slice(0,10))}</text>`).join('');
  const dots = coords.map(([x,y],i) => `<g class="portfolio-point" data-point="${i}" tabindex="0" role="button" aria-label="${escapeHtml(points[i].time.replace('T',' '))} 资产和收益"><circle cx="${x}" cy="${y}" r="${i===coords.length-1?5:4}" fill="${color}" stroke="white" stroke-width="2"/><circle cx="${x}" cy="${y}" r="13" fill="transparent"/></g>`).join('');
  const id = el.id+'Gradient';
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="资产与收益曲线"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop stop-color="${color}" stop-opacity=".18"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>${grid}<path d="${area}" fill="url(#${id})"/><polyline points="${line}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots}${dates}</svg><div class="chart-tooltip hidden" role="status"></div>`;
  const tooltip = el.querySelector('.chart-tooltip');
  el.querySelectorAll('.portfolio-point').forEach(dot => {
    const i = Number(dot.dataset.point), p = points[i];
    const show = () => {
      tooltip.innerHTML = `<strong>${escapeHtml(p.time.replace('T',' '))}${p.label === '当前' ? ' · 当前' : ''}</strong>
        <span>资产总值：${yuan(p.equity)}</span><span>累计收益：${yuan(p.profit)}</span>
        <span>收益率：${fmt(p.return_rate)}%</span>`;
      tooltip.classList.remove('hidden');
      tooltip.style.left = `${Math.max(8,Math.min(coords[i][0]+12,width-238))}px`;
      tooltip.style.top = `${Math.max(8,Math.min(coords[i][1]-18,height-112))}px`;
    };
    dot.addEventListener('mouseenter',show); dot.addEventListener('focus',show);
    dot.addEventListener('mouseleave',()=>tooltip.classList.add('hidden'));
    dot.addEventListener('blur',()=>tooltip.classList.add('hidden'));
  });
}

function assetQuantityChart(el, points) {
  if (!points.length) {el.innerHTML = '<div class="chart-empty">记录买卖后会显示持仓数量变化</div>'; return}
  const width = Math.max(el.clientWidth,280), height = el.clientHeight || 275;
  const pad = {left:58,right:18,top:25,bottom:36}, w = width-pad.left-pad.right, h = height-pad.top-pad.bottom;
  const max = Math.max(1,...points.map(p => p.quantity))*1.15;
  const x = i => pad.left + (points.length === 1 ? w/2 : i*w/(points.length-1));
  const y = v => pad.top + (max-Number(v || 0))/max*h;
  const grid = [0,1,2,3,4].map(i => {
    const gy=pad.top+i*h/4;
    return `<line x1="${pad.left}" x2="${width-pad.right}" y1="${gy}" y2="${gy}" stroke="#e9efec"/><text x="${pad.left-10}" y="${gy+4}" text-anchor="end" fill="#8b9c97" font-size="11">${fmt(max*(1-i/4),0)}</text>`;
  }).join('');
  const path = points.map((p,i) => i ? `H ${x(i)} V ${y(p.quantity)}` : `M ${x(i)} ${y(0)} V ${y(p.quantity)}`).join(' ');
  const markers = points.map((p,i) => p.trade ? `<g class="quantity-point" data-point="${i}" tabindex="0" role="button" aria-label="${p.trade.type === 'buy' ? '买入' : '卖出'} ${escapeHtml(p.time.replace('T',' '))}">
    <circle cx="${x(i)}" cy="${y(p.quantity)}" r="8" fill="${p.trade.type === 'buy' ? '#2a8b70' : '#d28467'}" stroke="white" stroke-width="2"/>
    <text x="${x(i)}" y="${y(p.quantity)-14}" text-anchor="middle" fill="${p.trade.type === 'buy' ? '#2a8b70' : '#d28467'}" font-size="11" font-weight="700">${p.trade.type === 'buy' ? '买' : '卖'}</text>
    <circle cx="${x(i)}" cy="${y(p.quantity)}" r="17" fill="transparent"/></g>` : '').join('');
  const dates = [0,Math.floor((points.length-1)/2),points.length-1].filter((v,i,a)=>a.indexOf(v)===i)
    .map(i=>`<text x="${x(i)}" y="${height-8}" text-anchor="middle" fill="#8b9c97" font-size="11">${escapeHtml(points[i].time.slice(0,10))}</text>`).join('');
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="持仓数量变化曲线">${grid}<path d="${path}" fill="none" stroke="#2a8b70" stroke-width="3" stroke-linejoin="round"/>${markers}${dates}</svg><div class="chart-tooltip hidden" role="status"></div>`;
  const tooltip = el.querySelector('.chart-tooltip');
  el.querySelectorAll('.quantity-point').forEach(marker => {
    const i=Number(marker.dataset.point), p=points[i], t=p.trade;
    const show=()=>{
      tooltip.innerHTML = `<strong>${t.type === 'buy' ? '买入' : '卖出'} · ${escapeHtml(p.time.replace('T',' '))}</strong>
        <span>买卖数量：${fmt(t.quantity,4)}</span><span>成交单价：${fmt(t.price,4)}</span>
        <span>交易金额：${yuan(t.amount)}</span><span>手续费：${yuan(t.fee)}</span>
        <span>交易后持仓数量：${fmt(p.quantity,4)}</span><span>交易后持仓市值：${yuan(p.value)}</span>
        <span>累计盈亏：${yuan(p.profit)}（${fmt(p.return_rate)}%）</span>
        <span>已实现：${yuan(p.realized)} · 浮动：${yuan(p.unrealized)}</span>`;
      tooltip.classList.remove('hidden');
      tooltip.style.left = `${Math.max(8,Math.min(x(i)+12,width-238))}px`;
      tooltip.style.top = `${Math.max(8,Math.min(y(p.quantity)-38,height-242))}px`;
    };
    marker.addEventListener('mouseenter',show);marker.addEventListener('focus',show);
    marker.addEventListener('mouseleave',()=>tooltip.classList.add('hidden'));
    marker.addEventListener('blur',()=>tooltip.classList.add('hidden'));
  });
}

function assetCombinedChart(el, legend, points) {
  if (!points.length) {
    el.innerHTML = '<div class="chart-empty">记录该标的买卖后会显示走势</div>';
    legend.innerHTML = '';
    return;
  }
  const profits = [
    {key:'profit', name:'累计盈亏', color:'#2a8b70', axis:'left'},
    {key:'realized', name:'已实现收益', color:'#698bc7', axis:'left'},
    {key:'unrealized', name:'浮动盈亏', color:'#e5a45d', axis:'left'},
  ];
  const series = profits;
  const width = Math.max(el.clientWidth, 280), height = el.clientHeight || 320;
  const pad = {left:58,right:18,top:24,bottom:36};
  const w = width-pad.left-pad.right, h = height-pad.top-pad.bottom;
  const bounds = values => {
    let min = Math.min(0,...values), max = Math.max(0,...values);
    const margin = Math.max((max-min)*.16,Math.abs(max)*.001,1);
    return [min-margin,max+margin];
  };
  const [leftMin,leftMax] = bounds(profits.flatMap(s => points.map(p => Number(p[s.key] || 0))));
  const x = i => pad.left + (points.length === 1 ? w/2 : i*w/(points.length-1));
  const y = value => pad.top + (leftMax-Number(value || 0))/(leftMax-leftMin)*h;
  const grid = [0,1,2,3,4].map(i => {
    const gy = pad.top+i*h/4;
    const leftValue = leftMax-i*(leftMax-leftMin)/4;
    return `<line x1="${pad.left}" x2="${width-pad.right}" y1="${gy}" y2="${gy}" stroke="#e9efec"/>
      <text x="${pad.left-9}" y="${gy+4}" text-anchor="end" fill="#8b9c97" font-size="11">${Math.round(leftValue).toLocaleString('zh-CN')}</text>`;
  }).join('');
  const lines = series.map(s => {
    const coords = points.map((p,i) => `${x(i).toFixed(1)},${y(p[s.key]).toFixed(1)}`).join(' ');
    return `<polyline points="${coords}" fill="none" stroke="${s.color}" stroke-width="${s.key === 'profit' ? 3 : 2.5}" stroke-linejoin="round" stroke-linecap="round"/>`;
  }).join('');
  const dates = [0,Math.floor((points.length-1)/2),points.length-1]
    .filter((v,i,a) => a.indexOf(v)===i)
    .map(i => `<text x="${x(i)}" y="${height-8}" text-anchor="middle" fill="#8b9c97" font-size="11">${escapeHtml(points[i].time.slice(0,10))}</text>`).join('');
  const markers = points.map((p,i) => {
    if (!p.trade) return '';
    const cy = y(p.profit);
    return `<g class="trade-point" data-point="${i}" tabindex="0" role="button" aria-label="${p.trade.type === 'buy' ? '买入' : '卖出'} ${escapeHtml(p.time.replace('T',' '))}">
      <line x1="${x(i)}" x2="${x(i)}" y1="${pad.top}" y2="${pad.top+h}" stroke="#b9cfc3" stroke-dasharray="3 5"/>
      <circle cx="${x(i)}" cy="${cy}" r="7" fill="${p.trade.type === 'buy' ? '#2a8b70' : '#d28467'}" stroke="white" stroke-width="2"/>
      <circle cx="${x(i)}" cy="${cy}" r="14" fill="transparent"/></g>`;
  }).join('');
  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="累计、已实现与浮动盈亏曲线">${grid}<line x1="${pad.left}" x2="${width-pad.right}" y1="${y(0)}" y2="${y(0)}" stroke="#c9d8d0" stroke-dasharray="4 4"/>${lines}${markers}${dates}</svg><div class="chart-tooltip hidden" role="status"></div>`;
  legend.innerHTML = series.map(s => `<span><i style="background:${s.color}"></i>${s.name}</span>`).join('') + '<span><i class="legend-trade"></i>买卖节点</span>';
  const tooltip = el.querySelector('.chart-tooltip');
  const show = i => {
    const p = points[i], t = p.trade;
    tooltip.innerHTML = `<strong>${t.type === 'buy' ? '买入' : '卖出'} · ${escapeHtml(p.time.replace('T',' '))}</strong>
      <span>数量：${fmt(t.quantity,4)}</span><span>单价：${fmt(t.price,4)}</span>
      <span>交易金额：${yuan(t.amount)}</span><span>交易后持仓市值：${yuan(p.value)}</span>
      <span>交易后持仓数量：${fmt(p.quantity,4)}</span>
      <span>累计盈亏：${yuan(p.profit)}（${fmt(p.return_rate)}%）</span>
      <span>已实现：${yuan(p.realized)} · 浮动：${yuan(p.unrealized)}</span>`;
    tooltip.classList.remove('hidden');
    tooltip.style.left = `${Math.max(8,Math.min(x(i)+12,width-238))}px`;
    tooltip.style.top = `${Math.max(8,Math.min(y(p.profit)-35,height-210))}px`;
  };
  el.querySelectorAll('.trade-point').forEach(marker => {
    const i = Number(marker.dataset.point);
    marker.addEventListener('mouseenter', () => show(i));
    marker.addEventListener('focus', () => show(i));
    marker.addEventListener('mouseleave', () => tooltip.classList.add('hidden'));
    marker.addEventListener('blur', () => tooltip.classList.add('hidden'));
  });
}

function renderAssetTrades(id) {
  const trades = state.transactions.filter(t => String(t.asset_id) === id && (t.type === 'buy' || t.type === 'sell')).slice().reverse();
  const snapshots = Object.fromEntries(state.portfolio.timeline.filter(p => p.tx_id != null).map(p => [p.tx_id,p]));
  $('assetTradeCount').textContent = `买入含手续费，卖出为净到账 · 共 ${trades.length} 笔`;
  $('assetTradeRows').innerHTML = trades.length ? trades.map(t => {
    const after = snapshots[t.id]?.asset_states[id];
    return `<tr><td>${escapeHtml(t.time.replace('T',' '))}</td><td><span class="tag ${t.type}">${t.type === 'buy' ? '买入' : '卖出'}</span></td>
      <td>${fmt(t.quantity,4)}</td><td>${fmt(t.price,4)}</td><td><b>${yuan(t.amount)}</b></td><td>${yuan(t.fee)}</td>
      <td>${after ? fmt(after.quantity,4) : '—'}</td><td class="${signedClass(after?.profit)}">${after ? yuan(after.profit) : '—'}</td>
      <td><button class="text-button edit" data-edit="${t.id}" aria-label="编辑记录">编辑</button></td></tr>`;
  }).join('') : '<tr><td colspan="9" class="empty">该标的暂无买卖记录</td></tr>';
}

function renderCharts() {
  if (!state) return;
  chart($('mainChart'), state.portfolio.timeline, $('chartMetric').value);
  const id = $('assetChartSelect').value;
  const position = state.portfolio.positions.find(x => String(x.id) === id);
  if (!position) {assetQuantityChart($('assetQuantityChart'), []); assetCombinedChart($('assetChart'), $('assetChartLegend'), []); $('assetStats').innerHTML=''; renderAssetTrades(id); return}
  const firstTrade = state.transactions.find(t => String(t.asset_id) === id && (t.type === 'buy' || t.type === 'sell'));
  const trades = Object.fromEntries(state.transactions.filter(t => String(t.asset_id) === id && (t.type === 'buy' || t.type === 'sell')).map(t => [t.id,t]));
  const points = firstTrade ? state.portfolio.timeline.filter(p => (p.tx_id != null && trades[p.tx_id]) || p.label === '当前').map(p => ({
    time:p.time, value:p.asset_states[id]?.value || 0, profit:p.asset_states[id]?.profit || 0,
    realized:p.asset_states[id]?.realized || 0, unrealized:p.asset_states[id]?.unrealized || 0,
    return_rate:p.asset_states[id]?.return_rate || 0, quantity:p.asset_states[id]?.quantity || 0,
    trade:trades[p.tx_id] || null,
  })) : [];
  assetQuantityChart($('assetQuantityChart'), points);
  assetCombinedChart($('assetChart'), $('assetChartLegend'), points);
  $('assetStats').innerHTML = `<div><small>当前市值</small><b>${yuan(position.market_value)}</b></div><div><small>已实现收益</small><b class="${signedClass(position.realized)}">${yuan(position.realized)}</b></div><div><small>浮动盈亏</small><b class="${signedClass(position.unrealized)}">${yuan(position.unrealized)}</b></div><div><small>累计盈亏 / 收益率</small><b class="${signedClass(position.profit)}">${yuan(position.profit)} · ${fmt(position.return_rate)}%</b></div>`;
  renderAssetTrades(id);
}

function openModal(id) {$(id).classList.remove('hidden')}
function closeModals() {for (const el of document.querySelectorAll('.modal-backdrop:not(#setupModal)')) el.classList.add('hidden')}
function tradeType() {return document.querySelector('input[name="type"]:checked').value}
function toggleTradeFields() {
  const type = tradeType(), cash = type === 'deposit' || type === 'withdraw', amountMode = $('inputMode').value === 'amount' && type === 'buy';
  for (const id of ['assetField','priceField','modeField','quantityField','feeField']) $(id).classList.toggle('hidden', cash || (id === 'quantityField' && amountMode));
  $('amountField').classList.toggle('hidden', !(cash || amountMode));
  $('modeField').classList.toggle('hidden', cash || type === 'sell');
  updatePreview();
}
function updatePreview() {
  const f = $('tradeForm').elements, type = tradeType(), price = Number(f.price.value), fee = Number(f.fee.value || 0), qty = Number(f.quantity.value), inputAmount = Number(f.amount.value);
  if (type === 'deposit' || type === 'withdraw') {$('tradePreview').textContent = inputAmount > 0 ? `${type === 'deposit' ? '现金增加' : '现金减少'} ${yuan(inputAmount)}` : '填写金额后保存'; return}
  if (!price) {$('tradePreview').textContent = '填写价格后自动计算金额'; return}
  if (type === 'buy' && $('inputMode').value === 'amount') {
    const quantity = inputAmount > fee ? (inputAmount-fee)/price : 0;
    $('tradePreview').textContent = quantity > 0 ? `预计买入 ${fmt(quantity,8)} 份 · 实际扣款按价格 × 数量 + 手续费计算` : '买入金额须大于手续费';
  } else $('tradePreview').textContent = qty > 0 ? `${type==='buy'?'预计扣款':'预计到账'} ${yuan(type==='buy' ? price*qty+fee : price*qty-fee)}` : '填写数量后自动计算金额';
}

function openNewTrade(type, title) {
  const form = $('tradeForm');
  form.reset(); editingTransactionId = null;
  form.elements.time.value = nowLocal();
  document.querySelector(`input[name="type"][value="${type}"]`).checked = true;
  $('tradeModalTitle').textContent = title;
  $('tradeSubmitBtn').textContent = '保存记录';
  toggleTradeFields(); openModal('tradeModal');
}

function openTradeEditor(id) {
  const tx = state.transactions.find(t => t.id === id);
  if (!tx) {notice('交易记录不存在，请刷新页面。', true); return}
  const form = $('tradeForm'), fields = form.elements;
  form.reset(); editingTransactionId = id;
  document.querySelector(`input[name="type"][value="${tx.type}"]`).checked = true;
  fields.time.value = tx.time.slice(0,16);
  fields.price.value = tx.price || '';
  fields.quantity.value = tx.quantity || '';
  fields.amount.value = tx.amount;
  fields.fee.value = tx.fee;
  fields.note.value = tx.note || '';
  $('inputMode').value = 'quantity';
  if (tx.asset_id != null) {
    const select = $('tradeAsset');
    if (![...select.options].some(o => Number(o.value) === tx.asset_id)) {
      const asset = state.assets.find(a => a.id === tx.asset_id);
      if (asset) select.add(new Option(`${asset.name} · ${asset.code}（已取消关注）`, String(asset.id)));
    }
    select.value = String(tx.asset_id);
  }
  $('tradeModalTitle').textContent = '编辑交易记录';
  $('tradeSubmitBtn').textContent = '保存修改';
  toggleTradeFields(); openModal('tradeModal');
}

async function submitForm(event, path, mapper, onSuccess) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {const result = await api(path, mapper(new FormData(form))); setState(result); form.reset(); onSuccess?.(); notice(result.quote_warning || '已保存，统计结果已更新。', Boolean(result.quote_warning))}
  catch (e) {notice(e.message, true)} finally {button.disabled = false}
}

document.addEventListener('DOMContentLoaded', async () => {


  const settingsIds=['aiBase','aiModel','prefMonths','prefDrawdown','prefPosition','prefCash','aiPreference'];
  for(const id of settingsIds){try{const v=localStorage.getItem('v2_'+id);if(v!==null) $(id).value=v}catch(_){}}
  $('openAISettings').onclick=()=>openModal('aiSettingsModal');
  $('aiSettingsForm').onsubmit=e=>{e.preventDefault();for(const id of settingsIds){try{localStorage.setItem('v2_'+id,$(id).value)}catch(_){}}closeModals();notice('模型与投资偏好已保存，Key 仅保留在本页面。')};
  function getPreferences(){return {holding_months:$('prefMonths').value,max_drawdown_pct:$('prefDrawdown').value,max_position_pct:$('prefPosition').value,min_cash_pct:$('prefCash').value,notes:$('aiPreference').value}}
  async function generateAI(mode,assetId=null){
    if(!$('aiSettingsForm').reportValidity() || !$('aiKey').value.trim()){openModal('aiSettingsModal');notice('请检查设置并填写 API Key。',true);return}
    const buttons=[$('aiDaily'),$('aiWeekly'),$('aiAsset')],single=mode==='asset',status=$(single?'aiAssetStatus':'aiStatus'),result=$(single?'aiAssetResult':'aiResult');
    buttons.forEach(b=>b.disabled=true);status.textContent='正在生成，请稍候…';result.classList.add('hidden');
    try {const r=await api('/api/ai/analyze',{mode,asset_id:assetId,base_url:$('aiBase').value,model:$('aiModel').value,api_key:$('aiKey').value,preferences:getPreferences()});status.textContent='数据截至 '+r.as_of.replace('T',' ')+' · 起始 '+r.period_start.replace('T',' ')+' · 模型 '+r.model;displayAIResult(result,r.content)}
    catch(e){status.textContent='生成失败：'+e.message}
    finally{buttons.forEach(b=>b.disabled=false)}
  }
  $('aiDaily').onclick=()=>generateAI('daily');$('aiWeekly').onclick=()=>generateAI('weekly');
  $('aiAsset').onclick=()=>generateAI('asset',$('assetChartSelect').value);
  $('assetChartSelect').addEventListener('change',()=>{$('aiAssetResult').classList.add('hidden');$('aiAssetStatus').textContent=''});

  $('todayLabel').textContent = new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'long',day:'numeric',weekday:'long'}).format(new Date());
  $('setupForm').elements.time.value = nowLocal(); $('tradeForm').elements.time.value = nowLocal();
  $('newTradeBtn').onclick = () => openNewTrade('buy', '记录一笔交易');
  $('addCapitalBtn').onclick = () => openNewTrade('deposit', '追加总资产');
  $('addAssetBtn').onclick = () => openModal('assetModal');
  document.querySelectorAll('.close-modal').forEach(b => b.onclick = closeModals);
  document.querySelectorAll('.modal-backdrop').forEach(b => b.onclick = e => {if(e.target === b && b.id !== 'setupModal') closeModals()});
  $('setupForm').onsubmit = e => submitForm(e,'/api/initialize',f=>({amount:f.get('amount'),time:f.get('time')}));
  $('tradeForm').onsubmit = e => {
    const txId = editingTransactionId;
    submitForm(e,txId == null ? '/api/transactions' : '/api/transactions/update',f=>({id:txId,type:f.get('type'),asset_id:f.get('asset_id'),time:f.get('time'),price:f.get('price'),quantity:f.get('quantity'),fee:f.get('fee'),amount:f.get('amount'),input_mode:f.get('input_mode'),note:f.get('note')}),()=>{editingTransactionId=null;closeModals();$('tradeForm').elements.time.value=nowLocal();toggleTradeFields()});
  };
  $('assetForm').onsubmit = e => submitForm(e,'/api/assets',f=>({name:f.get('name'),code:f.get('code')}),closeModals);
  $('quoteForm').onsubmit = e => submitForm(e,'/api/quotes/manual',f=>({asset_id:f.get('asset_id'),price:f.get('price'),prev_close:f.get('prev_close'),time:nowLocal()}),closeModals);
  $('cashRateForm').onsubmit = e => submitForm(e,'/api/settings/cash-rate',f=>({annual_rate:Number(f.get('rate'))/100}),closeModals);
  $('tradeTypes').onchange = toggleTradeFields; $('inputMode').onchange = toggleTradeFields;
  $('tradeForm').oninput = updatePreview;
  $('chartMetric').onchange = renderCharts; $('assetChartSelect').onchange = renderCharts; $('transactionFilter').onchange = renderTransactions;
  $('transactionRows').onclick = async e => {
    const edit = e.target.closest('[data-edit]');
    if (edit) {openTradeEditor(Number(edit.dataset.edit)); return}
    const b=e.target.closest('[data-delete]'); if(!b) return;
    if(!confirm('确定删除这笔记录？删除后会重新计算全部持仓和收益。')) return;
    try {setState(await api('/api/transactions/delete',{id:Number(b.dataset.delete)})); notice('记录已删除。')} catch(err){notice(err.message,true)}
  };
  $('assetTradeRows').onclick = e => {const edit=e.target.closest('[data-edit]'); if(edit) openTradeEditor(Number(edit.dataset.edit))};
  $('positionRows').addEventListener('click',async e=>{
    const b=e.target.closest('[data-target]');if(!b)return;
    const id=Number(b.dataset.target),current=state.targets[String(id)];
    const value=prompt('请输入目标仓位比例（%），留空清除。所有标的合计不能超过 100%。',current == null ? '' : String(current));
    if(value===null)return;
    try {setState(await api('/api/targets',{asset_id:id,target_pct:value.trim()}));notice('目标仓位已保存。')} catch(err){notice(err.message,true)}
  });
  $('positionRows').onclick = async e => {
    const remove = e.target.closest('[data-asset-delete]'), restore = e.target.closest('[data-asset-restore]');
    if (!remove && !restore) return;
    const id = Number((remove || restore).dataset[remove ? 'assetDelete' : 'assetRestore']);
    if (remove) {
      const hasHistory = state.transactions.some(t => t.asset_id === id);
      const message = hasHistory ? '此标的有交易记录。移除关注后会保留历史；如仍有持仓，它会继续显示直到卖出。确定移除？' : '确定删除这个标的？';
      if (!confirm(message)) return;
    }
    try {setState(await api(restore ? '/api/assets/restore' : '/api/assets/delete',{id})); notice(restore ? '已恢复关注。' : '标的已移除。')}
    catch(err) {notice(err.message,true)}
  };
  async function refreshQuotes(showNotice = true) {
    if (refreshing) return;
    refreshing = true; $('refreshBtn').disabled = true; $('refreshBtn').textContent = '更新中…';
    try {
      const result = await api('/api/quotes/refresh', {});
      setState(result.state);
      if (showNotice) notice(result.errors.length ? `部分行情未更新：${result.errors.join('；')}` : '行情已更新。', result.errors.length > 0);
    } catch (e) {if (showNotice) notice(e.message, true)}
    finally {refreshing = false; $('refreshBtn').disabled = false; $('refreshBtn').textContent = '↻ 更新行情'}
  }
  $('refreshBtn').onclick = () => refreshQuotes(true);
  window.addEventListener('resize',()=>renderCharts());
  try {setState(await api('/api/state'));toggleTradeFields();refreshQuotes(false)} catch(e){notice(e.message,true)}
  setInterval(()=>{if(state && !document.hidden) refreshQuotes(false)},60000);
});
