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
// Visual controls edit the same declarative document; saving still uses the revision API.
function populateEditor(doc) {
  const form = el('visual-editor'); const opened = new Set([...form.querySelectorAll('details[open]')].map(node => node.dataset.editorKey)); form.replaceChildren(); form.hidden = false;
  const update = (path, value) => {
    try {
      const next = JSON.parse(el('document').value);
      let target = next;
      for (const key of path.slice(0, -1)) target = target[key];
      target[path[path.length - 1]] = value;
      el('document').value = JSON.stringify(next, null, 2);
      el('preview-state').textContent = 'Unsaved edits';
      status('Changes are local and unsaved. Preview, then save when ready.');
    } catch { status('Correct the advanced document before using visual controls.'); }
  };
  const field = (parent, title, path, value, choices = null, numeric = false) => {
    const wrapper = document.createElement('div'); wrapper.className = 'field';
    const label = document.createElement('label'); label.textContent = title;
    const input = document.createElement(choices ? 'select' : 'input');
    input.setAttribute('aria-label', title);
    if (choices) for (const [key, name] of choices) { const option = document.createElement('option'); option.value = key; option.textContent = name; input.append(option); }
    else { input.type = numeric ? 'number' : 'text'; if (!numeric) input.maxLength = 120; }
    if (path.at(-1) === 'text_scale') { input.min = '0.8'; input.max = '1.6'; input.step = '0.1'; }
    if (path.at(-1) === 'artwork_interval_seconds') { input.min = '30'; input.max = '86400'; input.step = '1'; }
    input.value = value;
    input.oninput = () => update(path, numeric ? Number(input.value) : input.value);
    label.append(input); wrapper.append(label); parent.append(wrapper);
  };
  field(form, 'Home title', ['title'], doc.title);
  const pair = document.createElement('div'); pair.className = 'field-pair'; form.append(pair);
  field(pair, 'Appearance', ['theme'], doc.theme, [['storybook','Storybook'],['night','Forest night'],['warm','Warm earth'],['light','Soft daylight']]);
  field(pair, 'Text size', ['settings','text_scale'], doc.settings.text_scale, null, true);
  field(form, 'Artwork interval · seconds', ['settings','artwork_interval_seconds'], doc.settings.artwork_interval_seconds, null, true);
  const list = (parent, items, path) => items.forEach((item, index) => {
    const row = document.createElement('div'); row.className = 'entry-edit';
    const visible = document.createElement('input'); visible.type = 'checkbox'; visible.checked = item.visible; visible.setAttribute('aria-label', `Show ${item.title}`); visible.onchange = () => update([...path,index,'visible'],visible.checked);
    const title = document.createElement('input'); title.type = 'text'; title.value = item.title; title.maxLength = 120; title.setAttribute('aria-label', `Title for ${item.title}`); title.oninput = () => update([...path,index,'title'],title.value);
    row.append(visible,title);
    for (const [delta, name, symbol] of [[-1,'Move up','↑'],[1,'Move down','↓']]) {
      const button = document.createElement('button'); button.type = 'button'; button.textContent = symbol; button.setAttribute('aria-label', `${name} ${item.title}`); button.disabled = index+delta < 0 || index+delta >= items.length;
      button.onclick = () => {
        try {
          const next = JSON.parse(el('document').value); let entries = next;
          for (const key of path) entries = entries[key];
          if (index+delta < 0 || index+delta >= entries.length) return;
          [entries[index],entries[index+delta]] = [entries[index+delta],entries[index]];
          el('document').value = JSON.stringify(next,null,2); populateEditor(next);
          el('preview-state').textContent = 'Unsaved edits'; status('Arrangement updated. Preview before saving.');
          [...form.querySelectorAll('.entry-edit input[type=text]')].find(input => input.value === item.title)?.focus();
        } catch { status('Correct the advanced document before arranging items.'); }
      }; row.append(button);
    }
    parent.append(row);
    if (item.kind === 'movie') {
      const detail = document.createElement('div'); detail.className = 'movie-edit';
      field(detail, 'Poster for '+item.title, [...path,index,'poster'], item.poster);
      const provider = document.createElement('select'); provider.setAttribute('aria-label','Playback provider for '+item.title);
      for (const [id,title] of [['','No playback link'],['netflix','Netflix'],['prime_video','Prime Video'],['disney_plus','Disney+'],['youtube','YouTube']]) {
        const option = document.createElement('option'); option.value=id; option.textContent=title; provider.append(option);
      }
      provider.value = item.playback?.provider || '';
      const content = document.createElement('input'); content.type='text'; content.maxLength=64;
      content.setAttribute('aria-label','Exact content ID for '+item.title); content.value=item.playback?.content_id || ''; content.disabled=!provider.value;
      const changeLink = () => { content.disabled=!provider.value; update([...path,index,'playback'],provider.value?{provider:provider.value,content_id:content.value}:null); };
      provider.onchange=changeLink; content.oninput=changeLink;
      const remove = document.createElement('button'); remove.type='button'; remove.textContent='Remove movie'; remove.setAttribute('aria-label','Remove '+item.title);
      remove.onclick=() => {
        const next=JSON.parse(el('document').value); let entries=next; for(const key of path) entries=entries[key];
        entries.splice(index,1); el('document').value=JSON.stringify(next,null,2); populateEditor(next); status('Movie removed from the draft. Preview, then save.');
      };
      const upload=document.createElement('button'); upload.type='button'; upload.textContent='Choose local poster'; upload.setAttribute('aria-label','Choose local poster for '+item.title);
      const picker=document.createElement('input'); picker.type='file'; picker.accept='image/png'; picker.hidden=true;
      upload.onclick=() => picker.click();
      picker.onchange=async () => {
        const file=picker.files[0]; picker.value=''; if(!file) return;
        const actions=[...document.querySelectorAll('nav button, #connect')];
        try {
          if(!current || inFlight || file.size>8388608) throw Error('Poster unavailable, too large, or an edit is unconfirmed');
          form.inert=true; actions.forEach(b=>b.disabled=true);
          const bytes=await file.arrayBuffer();
          const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');
          const response=await fetch(`/api/assets/${digest}`,{method:'PUT',headers:{Authorization:`Bearer ${el('token').value}`,'Content-Type':'image/png'},body:bytes});
          if(!response.ok) throw Error('Poster refused: use a plain local RGB/RGBA PNG within the image limits');
          update([...path,index,'poster'],digest); populateEditor(JSON.parse(el('document').value)); status('Local poster added to the draft only. Preview, then save.');
        } catch(error) { status(error.message); }
        finally { form.inert=false; actions.forEach(b=>b.disabled=false); }
      };
      detail.append(provider,content,upload,picker,remove); parent.append(detail);
    }
  });
  for (const [index, section] of doc.sections.entries()) {
    const disclosure = document.createElement('details'); disclosure.className = 'section-editor'; const summary = document.createElement('summary'); summary.textContent = section.title + ' · ' + section.items.length + (section.items.length === 1 ? ' item' : ' items'); disclosure.append(summary); disclosure.dataset.editorKey = 'section:' + section.id; disclosure.open = opened.has(disclosure.dataset.editorKey);
    const group = document.createElement('fieldset'); group.className = 'editor-section'; const legend = document.createElement('legend'); legend.textContent = 'Section settings'; group.append(legend); disclosure.append(group);
    field(group,'Section title '+(index+1),['sections',index,'title'],section.title);
    field(group,'Section layout '+(index+1),['sections',index,'layout'],section.layout,[['row','Horizontal row'],['grid','Grid']]);
    list(group,section.items,['sections',index,'items']);
    if (doc.schema_version === 3) {
      const add=document.createElement('button'); add.type='button'; add.textContent='Add chosen movie'; add.disabled=section.items.length>=24;
      add.setAttribute('aria-label','Add chosen movie to '+section.title);
      add.onclick=() => {
        const next=JSON.parse(el('document').value);
        next.sections[index].items.push({id:'film_'+crypto.randomUUID().replaceAll('-',''),title:'Chosen movie',kind:'movie',target:'chosen_movie',visible:true,poster:'blank',playback:null});
        el('document').value=JSON.stringify(next,null,2); populateEditor(next); status('Movie added to the draft only. Set its title, local poster and optional explicit content link.');
      };
      group.append(add);
    }
    form.append(disclosure);
  }
  for (const [index, collection] of (doc.collections || []).entries()) {
    const disclosure = document.createElement('details'); disclosure.className = 'section-editor'; const summary = document.createElement('summary'); summary.textContent = collection.title + ' · collection'; disclosure.append(summary); disclosure.dataset.editorKey = 'collection:' + collection.id; disclosure.open = opened.has(disclosure.dataset.editorKey);
    const group = document.createElement('fieldset'); group.className = 'editor-section'; const legend = document.createElement('legend'); legend.textContent = 'Collection settings'; group.append(legend); disclosure.append(group);
    field(group,'Collection title '+(index+1),['collections',index,'title'],collection.title); list(group,collection.items,['collections',index,'items']); form.append(disclosure);
  }
}
el('visual-editor').addEventListener('submit', event => event.preventDefault());
el('document').addEventListener('change', () => { try { populateEditor(JSON.parse(el('document').value)); el('preview-state').textContent = 'Unsaved edits'; } catch { status('The advanced document contains invalid JSON.'); } });
let chromeTimer = null;
let renderGeneration = 0;
let slideshowTimer = null;
let view = null;
const imageUrls = new Map();
function render(doc, collectionId = null, artworkId = null, playing = false) {
  view = {doc, collectionId, artworkId, playing};
  clearTimeout(slideshowTimer); clearTimeout(chromeTimer);
  const generation = ++renderGeneration;
  const screen = el('screen');
  screen.replaceChildren(); screen.classList.remove('chrome-hidden','storybook'); screen.onkeydown = null; screen.onpointermove = null;
  screen.dataset.theme = doc.theme;
  screen.style.setProperty('--text-scale', doc.settings.text_scale);
  if (doc.theme === 'storybook' && !collectionId) { renderStorybook(screen,doc,status); return; }
  const heading = document.createElement('h2');
  const collection = (doc.collections || []).find(c => c.id === collectionId);
  const artwork = collection?.items.find(item => item.id === artworkId && item.visible && item.kind === 'artwork');
  heading.textContent = artwork?.title || collection?.title || doc.title;
  screen.append(heading);
  const button = (title, click) => {
    const result = document.createElement('button'); result.textContent = title; result.onclick = click; return result;
  };
  if (collectionId) { const home = button('Back to Home', () => render(doc)); home.className = 'art-back'; screen.append(home); }
  if (artwork) {
    heading.className = 'gallery-heading';
    const reveal = () => { screen.classList.remove('chrome-hidden'); clearTimeout(chromeTimer); chromeTimer = setTimeout(() => { if (!document.hidden && generation === renderGeneration) { screen.classList.add('chrome-hidden'); if (screen.contains(document.activeElement)) screen.focus({preventScroll:true}); } }, 6000); };
    screen.onpointermove = reveal;
    screen.onkeydown = event => {
      if (screen.classList.contains('chrome-hidden') && ['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Enter',' '].includes(event.key)) { event.preventDefault(); reveal(); controls.firstChild.focus(); return; }
      if (['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Enter',' '].includes(event.key)) reveal();
      if (event.key === 'Escape') { event.preventDefault(); render(doc,collectionId); }
    };
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
        reveal();
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
      button.className = 'tile'; button.dataset.target = item.target;
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
  populateEditor(current.experience); el('connection-panel').open = false; el('preview-state').textContent = 'Saved experience';
  render(current.experience);
  status(`Saved revision ${current.revision}. No TV is connected.`);
}
const edit = () => ({request_id: crypto.randomUUID(), base_revision: current.revision, experience: JSON.parse(el('document').value)});
function action(id, fn) {
  el(id).onclick = async () => {
    for (const button of document.querySelectorAll('nav button, #connect')) button.disabled = true;
    el('visual-editor').inert = true; el('document').disabled = true;
    try { await fn(); } catch (error) { status(error.message); }
    finally { el('visual-editor').inert = false; el('document').disabled = false; for (const button of document.querySelectorAll('nav button, #connect')) button.disabled = false; }
  };
}
action('connect', load);
action('preview', async () => { if (!current) throw Error('Connect first.'); const result = await api('preview', edit()); render(result.experience); el('preview-state').textContent = 'Unsaved preview'; status(`Unsaved preview; changed fields: ${result.changed_fields.join(', ') || 'none'}`); });
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
  el('visual-editor').inert = true; el('document').disabled = true;
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
    el('document').value = JSON.stringify(result.experience, null, 2); populateEditor(result.experience); el('preview-state').textContent = 'Unsaved preview';
    render(result.experience, tile.target);
    status('Artwork is ready to preview. Save changes to keep it; Undo restores the prior experience.');
  } catch (error) { status(error.message); }
  finally { el('visual-editor').inert = false; el('document').disabled = false; for (const b of document.querySelectorAll('nav button, #connect')) b.disabled = false; }
};
el('screen').addEventListener('keydown', event => {
  if (event.defaultPrevented) return;
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
  const tiles = [...el('screen').querySelectorAll('button')];
  if (!tiles.length) return;
  const index = tiles.indexOf(document.activeElement);
  const delta = ['ArrowLeft', 'ArrowUp'].includes(event.key) ? -1 : 1;
  tiles[(index + delta + tiles.length) % tiles.length].focus(); event.preventDefault();
});
