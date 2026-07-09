(function () {
  const root = document.documentElement;
  const toggle = document.getElementById('themeToggle');
  if (toggle) {
    toggle.addEventListener('click', async () => {
      const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try {
        await fetch('/api/theme', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ theme: next }),
        });
      } catch (e) { /* non-fatal */ }
    });
  }
})();

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
