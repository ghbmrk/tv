const el = id => document.getElementById(id);
let current = null;
let lastReceipt = null;
let inFlight = null;
const status = message => { el('status').textContent = message; };
async function api(path, data) {
  const response = await fetch(`/api/${path}`, {
    method: data ? 'POST' : 'GET',
    headers: {Authorization: `Bearer ${el('token').value}`, ...(data ? {'Content-Type': 'application/json'} : {})},
    ...(data ? {body: JSON.stringify(data)} : {})
  });
  const result = await response.json();
  if (!response.ok) { const error = Error(result.error); error.status = response.status; throw error; }
  return result;
}
function render(doc) {
  const screen = el('screen');
  screen.replaceChildren();
  screen.dataset.theme = doc.theme;
  screen.style.fontSize = `${doc.settings.text_scale}em`;
  const heading = document.createElement('h2');
  heading.textContent = doc.title;
  screen.append(heading);
  for (const section of doc.sections) {
    const title = document.createElement('h3');
    title.textContent = section.title;
    const items = document.createElement('div');
    items.className = section.layout;
    for (const item of section.items.filter(item => item.visible)) {
      const button = document.createElement('button');
      button.className = 'tile';
      button.textContent = item.title;
      button.onclick = () => status(`Preview only: ${item.kind} “${item.title}”. Use the native Android shell to launch installed apps.`);
      items.append(button);
    }
    screen.append(title, items);
  }
}
async function load() {
  current = await api('state');
  el('document').value = JSON.stringify(current.experience, null, 2);
  render(current.experience);
  status(`Saved revision ${current.revision}. No TV is connected.`);
}
const edit = () => ({request_id: crypto.randomUUID(), base_revision: current.revision, experience: JSON.parse(el('document').value)});
function action(id, fn) {
  el(id).onclick = async () => {
    for (const button of document.querySelectorAll('nav button, #connect')) button.disabled = true;
    try { await fn(); } catch (error) { status(error.message); }
    finally { for (const button of document.querySelectorAll('nav button, #connect')) button.disabled = false; }
  };
}
action('connect', load);
action('preview', async () => { if (!current) throw Error('Connect first.'); const result = await api('preview', edit()); render(result.experience); status(`Unsaved preview; changed fields: ${result.changed_fields.join(', ') || 'none'}`); });
async function effect(operation, request) {
  if (inFlight && (inFlight.operation !== operation || JSON.stringify(inFlight.request) !== JSON.stringify(request))) {
    throw Error('An earlier effect is unconfirmed. Retry that exact operation before starting another.');
  }
  inFlight ??= {operation, request};
  let receipt;
  try { receipt = await api(operation, request); }
  catch (error) {
    if (error.status && error.status < 500) { inFlight = null; throw error; }
    receipt = await api(`receipts/${request.request_id}`).catch(() => null);
    if (!receipt) throw Error('Result unconfirmed. Retry the same operation to reconcile it.');
  }
  inFlight = null;
  return receipt;
}
action('apply', async () => {
  if (!current) throw Error('Connect first.');
  const candidate = JSON.parse(el('document').value);
  if (inFlight && JSON.stringify(inFlight.request.experience) !== JSON.stringify(candidate)) throw Error('An earlier effect is unconfirmed. Retry that exact operation first.');
  lastReceipt = await effect('apply', inFlight?.request ?? edit());
  await load();
  status(`Applied revision ${lastReceipt.revision}; read-back complete.`);
});
action('undo', async () => {
  if (!lastReceipt) throw Error('No edit from this session to undo.');
  const request = inFlight?.operation === 'undo' ? inFlight.request : {request_id: crypto.randomUUID(), base_revision: lastReceipt.revision, restore_revision: lastReceipt.previous_revision};
  const receipt = await effect('undo', request);
  lastReceipt = null;
  await load();
  status(`Restored prior experience as revision ${receipt.revision}.`);
});
action('export', async () => {
  if (!current) throw Error('Connect first.');
  const saved = await api('state');
  const url = URL.createObjectURL(new Blob([JSON.stringify(saved.experience, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'experience.json'; link.click(); URL.revokeObjectURL(url);
  status(`Exported saved revision ${saved.revision}. Unsaved preview changes are excluded.`);
});
el('screen').addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
  const tiles = [...el('screen').querySelectorAll('button')];
  if (!tiles.length) return;
  const index = tiles.indexOf(document.activeElement);
  const delta = ['ArrowLeft', 'ArrowUp'].includes(event.key) ? -1 : 1;
  tiles[(index + delta + tiles.length) % tiles.length].focus(); event.preventDefault();
});
