// Optional UI only. Collection and rendering are pure Python; no requests or inference.
const provider = document.querySelector('#provider-filter');
const type = document.querySelector('#type-filter');
const search = document.querySelector('#plan-search');
const rows = [...document.querySelectorAll('tr[data-provider]')];
function filterPlans() {
  let count = 0;
  for (const row of rows) {
    const match = (!provider.value || row.dataset.provider === provider.value) &&
      (!type.value || row.dataset.kind === type.value) &&
      row.textContent.toLowerCase().includes(search.value.toLowerCase().trim());
    row.hidden = !match;
    if (match) count++;
  }
  document.querySelector('#result-count').textContent = `${count} plans`;
  document.querySelector('#no-results').hidden = count !== 0;
}
if (provider && type && search) {
  provider.addEventListener('change', filterPlans);
  type.addEventListener('change', filterPlans);
  search.addEventListener('input', filterPlans);
}
for (const node of document.querySelectorAll('[data-collected]')) {
  const age = (Date.now() - Date.parse(node.dataset.collected)) / 3600000;
  if (!Number.isFinite(age) || age > Number(node.dataset.maxAge)) {
    node.classList.add('stale');
    node.textContent = 'This snapshot is overdue for verification. Prices may be outdated; check the official source before ordering.';
  }
}
