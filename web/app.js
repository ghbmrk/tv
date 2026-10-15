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
let renderGeneration = 0;
let slideshowTimer = null;
let view = null;
const imageUrls = new Map();
function render(doc, collectionId = null, artworkId = null, playing = false) {
  view = {doc, collectionId, artworkId, playing};
  clearTimeout(slideshowTimer);
  const generation = ++renderGeneration;
  const screen = el('screen');
  screen.replaceChildren();
  screen.dataset.theme = doc.theme;
  screen.style.fontSize = `${doc.settings.text_scale}em`;
  const heading = document.createElement('h2');
  const collection = (doc.collections || []).find(c => c.id === collectionId);
  const artwork = collection?.items.find(item => item.id === artworkId && item.visible && item.kind === 'artwork');
  heading.textContent = artwork?.title || collection?.title || doc.title;
  screen.append(heading);
  const button = (title, click) => {
    const result = document.createElement('button'); result.textContent = title; result.onclick = click; return result;
  };
  if (collectionId) screen.append(button('Back to Home', () => render(doc)));
  if (artwork) {
    const items = collection.items.filter(i => i.visible && i.kind === 'artwork');
    const index = items.findIndex(i => i.id === artworkId);
    const image = document.createElement('img'); image.className = 'artwork'; image.alt = artwork.title;
    const controls = document.createElement('div'); controls.className = 'art-controls';
    controls.append(button('Back to collection', () => render(doc, collectionId)),
      button('Previous artwork', () => render(doc, collectionId, items[(index - 1 + items.length) % items.length].id, playing)),
      button(playing ? 'Pause slideshow' : 'Start slideshow', () => render(doc, collectionId, artworkId, !playing)),
      button('Next artwork', () => render(doc, collectionId, items[(index + 1) % items.length].id, playing)));
    screen.append(image, controls);
    (async () => {
      if (!imageUrls.has(artwork.target)) {
        const response = await fetch(`/api/assets/${artwork.target}`, {headers: {Authorization: `Bearer ${el('token').value}`}});
        if (!response.ok) throw Error('Local artwork unavailable');
        const url = URL.createObjectURL(await response.blob());
        if (generation !== renderGeneration) { URL.revokeObjectURL(url); return; }
        imageUrls.set(artwork.target, url);
        while (imageUrls.size > 2) { const key = imageUrls.keys().next().value; URL.revokeObjectURL(imageUrls.get(key)); imageUrls.delete(key); }
      }
      if (generation !== renderGeneration) return;
      image.onload = () => {
        if (generation === renderGeneration && playing && items.length > 1 && !document.hidden)
          slideshowTimer = setTimeout(() => render(doc, collectionId, items[(index + 1) % items.length].id, true), doc.settings.artwork_interval_seconds * 1000);
      };
      image.src = imageUrls.get(artwork.target);
    })().catch(error => { if (generation === renderGeneration) status(error.message); });
    controls.firstChild.focus();
    return;
  }
  const sections = collection ? [{title: 'Collection', layout: 'grid', items: collection.items}] : collectionId ? [] : doc.sections;
  if (collectionId && (!collection || !collection.items.some(i => i.visible))) {
    const empty = document.createElement('p'); empty.textContent = 'No visible items in this collection. Import artwork or edit its contents.'; screen.append(empty);
  }
  for (const section of sections) {
    const title = document.createElement('h3');
    title.textContent = section.title;
    const items = document.createElement('div');
    items.className = section.layout;
    for (const item of section.items.filter(item => item.visible)) {
      const button = document.createElement('button');
      button.className = 'tile';
      button.textContent = item.title;
      button.onclick = () => item.kind === 'collection' ? render(doc, item.target) : item.kind === 'artwork' ? render(doc, collectionId, item.id) : status(`Preview only: app “${item.title}”. Use the native Android shell to launch installed apps.`);
      items.append(button);
    }
    screen.append(title, items);
  }
  if (collectionId) screen.querySelector('button')?.focus();
}
document.addEventListener('visibilitychange', () => { if (view) render(view.doc, view.collectionId, view.artworkId, view.playing); });
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
  const response = await fetch('/api/export', {headers: {Authorization: `Bearer ${el('token').value}`}});
  if (!response.ok) throw Error('Saved experience export unavailable');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = 'experience.stv.zip'; document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
  status('Exported the saved experience and its artwork. Unsaved preview changes are excluded.');
});
action('artwork', async () => { if (!current || inFlight) throw Error('Connect and resolve pending changes first.'); el('artwork-file').click(); });
el('artwork-file').onchange = async () => {
  const file = el('artwork-file').files[0]; el('artwork-file').value = '';
  if (!file) return;
  for (const b of document.querySelectorAll('nav button, #connect')) b.disabled = true;
  try {
    if (!current || inFlight || file.size > 8388608) throw Error('Image unavailable, too large, or an edit is unconfirmed');
    const data = await file.arrayBuffer();
    const id = [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map(x => x.toString(16).padStart(2, '0')).join('');
    const response = await fetch(`/api/assets/${id}`, {method: 'PUT', headers: {Authorization: `Bearer ${el('token').value}`, 'Content-Type': 'image/png'}, body: data});
    if (!response.ok) throw Error('Import refused. Use a plain noninterlaced 8-bit RGB/RGBA PNG within the size limits.');
    const doc = JSON.parse(el('document').value);
    if (doc.schema_version === 1) {
      doc.schema_version = 2;
      doc.collections = [...new Map(doc.sections.flatMap(s => s.items).filter(i => i.kind === 'collection').map(i => [i.target, {id: i.target, title: i.title, items: []}])).values()];
    }
    const refs = doc.sections.flatMap(s => s.items);
    let tile = refs.find(i => i.kind === 'collection');
    if (!tile) {
      const section = doc.sections.find(s => s.items.length < 24);
      if (!section) throw Error('Make room for a collection tile first');
      tile = {id: 'art_' + crypto.randomUUID().replaceAll('-', ''), title: 'Local artwork', kind: 'collection', target: 'artwork', visible: true};
      section.items.push(tile);
    }
    let collection = doc.collections.find(c => c.id === tile.target);
    if (!collection) { collection = {id: tile.target, title: tile.title, items: []}; doc.collections.push(collection); }
    if (!collection.items.some(i => i.kind === 'artwork' && i.target === id)) collection.items.push({id: 'art_' + crypto.randomUUID().replaceAll('-', ''), title: `Local artwork ${collection.items.length + 1}`, kind: 'artwork', target: id, visible: true});
    const result = await api('preview', {request_id: crypto.randomUUID(), base_revision: current.revision, experience: doc});
    el('document').value = JSON.stringify(result.experience, null, 2);
    render(result.experience, tile.target);
    status('Unsaved artwork preview. Apply to save the collection; Undo restores the prior experience.');
  } catch (error) { status(error.message); }
  finally { for (const b of document.querySelectorAll('nav button, #connect')) b.disabled = false; }
};
el('screen').addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
  const tiles = [...el('screen').querySelectorAll('button')];
  if (!tiles.length) return;
  const index = tiles.indexOf(document.activeElement);
  const delta = ['ArrowLeft', 'ArrowUp'].includes(event.key) ? -1 : 1;
  tiles[(index + delta + tiles.length) % tiles.length].focus(); event.preventDefault();
});
