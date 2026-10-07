/* Optional demo gateway. The live site's application and data stay independent. */
(() => {
  'use strict';
  if (window.top !== window || location.pathname !== '/') return;
  // Separate modern stylesheet by default; ?style=classique restores the original.
  if (new URL(location.href).searchParams.get('style') !== 'classique') {
    const theme = document.createElement('link');
    theme.rel = 'stylesheet'; theme.href = '/demo/site-modern.css';
    theme.id = 'nd-modern-theme';
    theme.addEventListener('load', () => document.documentElement.classList.add('nd-modern'));
    document.head.append(theme);
  }
  const brand = document.querySelector('.masthead .brand');
  if (!brand || document.getElementById('nd-demo-open')) return;
  const storageKey = 'nos-deniers-demo-dismissed';
  let frame = null, panel = null, readyTimer = null, inertBefore = [];
  const button = document.createElement('button');
  button.id = 'nd-demo-open'; button.type = 'button';
  button.className = 'nd-demo-open'; button.textContent = '▶ Démo';
  button.setAttribute('aria-haspopup', 'dialog');
  button.setAttribute('aria-expanded', 'false');
  brand.insertAdjacentElement('afterend', button);

  function remember() { try { sessionStorage.setItem(storageKey, '1'); } catch (_) {} }
  function close(rememberChoice = true, focusButton = true) {
    if (readyTimer !== null) clearTimeout(readyTimer);
    readyTimer = null;
    // Removing the frame also stops its voice and its timers.
    if (panel) panel.remove();
    panel = null; frame = null;
    for (const [element, previous] of inertBefore) element.inert = previous;
    inertBefore = [];
    document.documentElement.classList.remove('nd-demo-opened');
    button.setAttribute('aria-expanded', 'false');
    button.removeAttribute('aria-busy');
    if (rememberChoice) remember();
    if (focusButton) button.focus({preventScroll:true});
  }
  function open() {
    if (frame) return;
    panel = document.createElement('section');
    panel.id = 'nd-demo-layer'; panel.className = 'nd-demo-layer';
    panel.hidden = true; panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', 'Visite guidée de Nos Deniers');
    frame = document.createElement('iframe');
    frame.title = 'Démonstration de Nos Deniers — quatre parcours guidés';
    frame.src = '/demo/'; frame.allow = 'autoplay';
    frame.addEventListener('error', () => close(false, false));
    panel.append(frame); document.body.append(panel);
    button.setAttribute('aria-busy', 'true');
    // Keep the actual site available if the optional demo fails to load.
    readyTimer = setTimeout(() => close(false, false), 20000);
  }
  window.addEventListener('message', event => {
    if (!frame || event.origin !== location.origin || event.source !== frame.contentWindow) return;
    if (event.data?.type === 'nos-deniers-demo:ready') {
      clearTimeout(readyTimer); readyTimer = null;
      if (panel.hidden) {
        inertBefore = Array.from(document.body.children).filter(element => element !== panel)
          .map(element => [element, element.inert]);
        for (const [element] of inertBefore) element.inert = true;
      }
      panel.hidden = false;
      document.documentElement.classList.add('nd-demo-opened');
      button.setAttribute('aria-expanded', 'true');
      button.removeAttribute('aria-busy'); frame.focus();
    } else if (event.data?.type === 'nos-deniers-demo:close') close();
    else if (event.data?.type === 'nos-deniers-demo:error') close(false, false);
  });
  button.addEventListener('click', open);
  let dismissed = false;
  try { dismissed = sessionStorage.getItem(storageKey) === '1'; } catch (_) {}
  const url = new URL(location.href);
  if (url.searchParams.get('demo') === 'off') {
    dismissed = true; remember(); url.searchParams.delete('demo');
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
  }
  if (!dismissed) open();
})();
