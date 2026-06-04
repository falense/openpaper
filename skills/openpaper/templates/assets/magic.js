/* OpenPaper — paint-gated "ink" trigger.
   Adds `.inked` to <html> only once the page is actually painting (double
   rAF). Frozen/off-screen iframes never fire it, so the headline stays in its
   visible base state instead of being stuck mid-write. */
(function () {
  function go() {
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        document.documentElement.classList.add('inked');
      });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', go);
  } else {
    go();
  }
})();
