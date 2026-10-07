/* Keep the dynamically refreshed headline intact, except its final comma. */
(() => {
  const start = () => {
    const headline = document.getElementById('index-punchline');
    if (!headline) return;
    const trimComma = () => {
      const text = headline.textContent;
      const trimmed = text.replace(/,\s*$/, '');
      if (trimmed !== text) headline.textContent = trimmed;
    };
    trimComma();
    new MutationObserver(trimComma).observe(headline, {
      childList: true, characterData: true, subtree: true
    });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else start();
})();
