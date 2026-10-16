fetch('/storybook-default.json').then(response => response.json()).then(doc => {
  const screen=document.getElementById('screen'); screen.dataset.theme=doc.theme;
  renderStorybook(screen,doc,message => { document.getElementById('preview-notice').textContent=message; });
}).catch(() => { document.getElementById('preview-notice').textContent='Design preview unavailable'; });
