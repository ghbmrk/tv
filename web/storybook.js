// Local manual curation only. No recommendation request, timer, hover video, or media element.
const storyPosters = ['princess_frog','kung_fu_panda','balto','little_mermaid','hunchback','land_before_time'];
const storyMarks = {
  netflix: '<path fill="#ae4835" d="M28 0h14v70H28zm32 0h14v70H60z"/><path fill="#c25840" d="M28 0h16l30 70H58z"/>',
  disney_plus: '<path d="M15 65V45h10V31l5-9 5 9v14h9V16L50 0l6 16v29h9V31l5-9 5 9v14h10v20z"/><path d="M4 22Q50-19 96 22" fill="none" stroke="currentColor" stroke-width="2"/>',
  youtube: '<rect width="100" height="70" rx="12" fill="#ae4937"/><path d="M42 18l27 17-27 17z"/>',
  prime_video: '<path d="M8 34C30 60 68 63 90 30 68 45 35 48 8 34zM76 25l20-1-5 22-4-14z"/>',
  hulu: '<path d="M25 0h15v27c28-11 38 1 38 18v25H62V45c0-11-22-9-22 1v24H25z"/>',
  apple_tv: '<path d="M52 19C65 8 87 21 76 34c-8 8 0 14 4 15-7 23-17 24-28 17-12 9-26-1-30-23-4-19 11-31 30-24zM51 14C49 1 64-4 67 0c0 8-7 14-16 14z"/>'
};
function renderStorybook(screen, doc, status) {
  screen.classList.add('storybook');
  let remembered = screen.dataset.focusedTile;
  const rows = [];
  for (const section of doc.sections) {
    const row = document.createElement('div'); row.className = 'story-row'; row.dataset.movies = section.items.some(i => i.kind === 'movie'); row.dataset.layout = section.layout;
    const buttons = [];
    for (const tile of section.items.filter(i => i.visible)) {
      const button = document.createElement('button'); button.className = 'story-tile'; button.dataset.target = tile.target; button.dataset.id = tile.id;
      button.setAttribute('aria-label', tile.title); button.dataset.kind = tile.kind;
      if (tile.kind === 'movie') {
        button.classList.add('story-poster');
        const index = storyPosters.indexOf(tile.poster);
        if (index >= 0) { button.style.backgroundImage = 'url(/storybook/posters.png)'; button.style.backgroundPosition = `${index % 3 * 50}% ${Math.floor(index / 3) * 100}%`; }
        else loadStoryPoster(button, tile.poster, status);
        button.setAttribute('aria-description', tile.playback ? 'Playback unavailable: stop-at-end provider integration is not qualified' : 'Playback link not configured');
        button.onclick = () => status(tile.playback ? `Chosen movie playback unavailable: stop-at-end provider integration is not qualified. No provider opened.` : `Choose an explicit playback link for ${tile.title}. No recommendation screen opened.`);
      } else {
        const svg = document.createElementNS('http://www.w3.org/2000/svg','svg'); svg.setAttribute('viewBox','0 0 100 70'); svg.setAttribute('aria-hidden','true');
        // Only fixed, source-controlled vector paths enter innerHTML, never document data.
        svg.innerHTML = storyMarks[tile.target] || '<path d="M10 5h30v25H10zm50 0h30v25H60zM10 45h30v25H10zm50 0h30v25H60z"/>';
        button.append(svg); button.onclick = () => status(`Preview only: ${tile.title}. No app or provider content opened.`);
      }
      button.onfocus = () => { screen.dataset.focusedTile = tile.id; button.scrollIntoView({block:'nearest',inline:'nearest'}); };
      buttons.push(button); row.append(button);
    }
    rows.push(buttons); screen.append(row);
  }
  screen.onkeydown = event => {
    let r = rows.findIndex(row => row.includes(document.activeElement)); if (r < 0) return;
    let c = rows[r].indexOf(document.activeElement);
    if (event.key === 'ArrowLeft') c--;
    else if (event.key === 'ArrowRight') c++;
    else if (event.key === 'ArrowUp') r--;
    else if (event.key === 'ArrowDown') r++;
    else return;
    event.preventDefault(); const row = rows[Math.max(0,Math.min(rows.length-1,r))]; row?.[Math.max(0,Math.min(row.length-1,c))]?.focus();
  };
  if (screen.contains(document.activeElement) || !document.activeElement || document.activeElement === document.body)
    (rows.flat().find(b => b.dataset.id === remembered) || rows[0]?.[2] || rows.flat()[0])?.focus({preventScroll:true});
}
async function loadStoryPoster(button, digest, status) {
  if (!/^[a-f0-9]{64}$/.test(digest || '')) return;
  try {
    const response = await fetch(`/api/assets/${digest}`, {headers:{Authorization:`Bearer ${document.getElementById('token').value}`}});
    if (!response.ok) throw Error('Local movie poster unavailable');
    const url = URL.createObjectURL(await response.blob());
    if (!button.isConnected) { URL.revokeObjectURL(url); return; }
    const image = document.createElement('img'); image.alt = ''; image.src = url; image.onload = () => URL.revokeObjectURL(url); image.onerror = () => URL.revokeObjectURL(url); button.append(image);
  } catch (error) { status(error.message); }
}
