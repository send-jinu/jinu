const $ = (selector) => document.querySelector(selector);
const money = (value) => value == null ? '미제공' : `${Math.round(value).toLocaleString('ko-KR')}원`;
const count = (value) => value == null ? '미제공' : Math.round(value).toLocaleString('ko-KR');
let latest = null;

function setMessage(text, type = '') {
  const node = $('#message'); node.textContent = text; node.className = `message ${type}`;
}

function activateTab(name) {
  document.querySelectorAll('.tab').forEach((tab) => tab.classList.toggle('is-active', tab.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach((panel) => { panel.hidden = panel.id !== `panel-${name}`; panel.classList.toggle('is-active', panel.id === `panel-${name}`); });
  if (name === 'settings') refreshKeyStatus();
}

document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => activateTab(tab.dataset.tab)));
const currentYear = new Date().getFullYear();
for (let year = currentYear; year >= currentYear - 10; year -= 1) $('#year').insertAdjacentHTML('beforeend', `<option value="${year}">${year}년</option>`);
$('#year').value = String(currentYear - 1);

async function refreshKeyStatus() {
  try { const data = await fetch('/api/config/status', { cache: 'no-store' }).then((r) => r.json()); $('#key-status').textContent = data.configured ? '● 인증키가 등록되어 있습니다.' : '○ 인증키를 등록해 주세요.'; $('#key-status').className = `key-status ${data.configured ? 'ok' : ''}`; } catch (_) { $('#key-status').textContent = '상태를 확인할 수 없습니다.'; }
}

$('#key-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const key = $('#api-key').value.trim(); if (!key) return;
  const button = event.target.querySelector('button'); button.disabled = true;
  try { const response = await fetch('/api/config/key', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({apiKey: key}) }); const data = await response.json(); if (!response.ok) throw new Error(data.error || '등록에 실패했습니다.'); $('#api-key').value = ''; $('#key-status').textContent = '● 현재 서버에 등록했습니다. 이제 매출을 조회할 수 있습니다.'; $('#key-status').className = 'key-status ok'; } catch (error) { $('#key-status').textContent = error.message; $('#key-status').className = 'key-status error'; } finally { button.disabled = false; }
});

$('#search-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const brand = $('#brand').value.trim(); const year = $('#year').value; if (!brand) return;
  setMessage('공정거래위원회 공시 API에서 자료를 가져오는 중입니다…'); $('#results').hidden = true;
  try { const response = await fetch(`/api/franchise?${new URLSearchParams({brand, year})}`, {cache: 'no-store'}); const data = await response.json(); if (!response.ok) throw new Error(data.error || '조회에 실패했습니다.'); latest = data; render(data); if (!data.rows.length) setMessage('해당 기준연도에 일치하는 공시 레코드가 없습니다. 브랜드명이나 연도를 바꿔 다시 검색해 보세요.', 'warning'); else setMessage('조회가 완료되었습니다.', 'success'); } catch (error) { setMessage(error.message, 'error'); }
});

function render(data) {
  $('#results').hidden = false; $('#result-title').textContent = `${data.requested_brand} · ${data.year}년`; $('#source-line').textContent = `출처: ${data.source} · 기준연도 ${data.year} · ${data.source_url}`;
  const first = data.rows.find((row) => row.annual_sales_won != null) || data.rows[0] || {};
  $('#annual').textContent = money(first.annual_sales_won); $('#monthly').textContent = money(first.monthly_sales_won); $('#area-sales').textContent = money(first.area_sales_won); $('#area-source').textContent = first.area_sales_source || '미제공';
  $('#region-body').innerHTML = data.regions.length ? data.regions.map((r) => `<tr><td>${escapeHtml(r.region)}</td><td>${count(r.store_count)}개</td><td>${money(r.average_annual_sales_won)}</td><td>${money(r.average_annual_sales_won == null ? null : r.average_annual_sales_won / 12)}</td></tr>`).join('') : '<tr><td colspan="4" class="empty">지역별 자료가 없습니다.</td></tr>';
  $('#raw-body').innerHTML = data.rows.length ? data.rows.slice(0, 100).map((r) => `<tr><td>${escapeHtml(r.brand)}</td><td>${escapeHtml(r.region)}</td><td>${money(r.annual_sales_won)}</td><td>${money(r.monthly_sales_won)}</td><td>${money(r.area_sales_won)}<small>${escapeHtml(r.area_sales_source)}</small></td></tr>`).join('') : '<tr><td colspan="5" class="empty">API가 반환한 자료가 없습니다.</td></tr>';
}
function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char])); }
$('#download').addEventListener('click', () => { if (!latest) return; const params = new URLSearchParams({brand: latest.requested_brand, year: latest.year}); window.location.href = `/api/franchise.csv?${params}`; });
refreshKeyStatus();
