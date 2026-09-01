/**
 * Motor de tour guiado — vanilla JS, sin dependencias externas (coherente
 * con el resto del proyecto: nada de librerías vía CDN). Cada página
 * define sus propios pasos en `window.PANOL_TOUR_STEPS` (ver ejemplo abajo)
 * y el botón "¿Cómo uso esto?" del header (base.html) llama a
 * `panolTour.start()`.
 *
 * Formato de un paso:
 *   { selector: '#mi-boton', title: 'Nuevo usuario', text: 'Acá das de alta una cuenta.' }
 *
 * El motor resalta el elemento (recorta un hueco en un overlay oscuro),
 * le pone un globo con el texto al lado, y dos botones (Anterior/
 * Siguiente + Salir). Si un selector no existe en la página en ese
 * momento (ej. un botón que solo aparece según el rol), el paso se
 * saltea solo, no rompe el tour.
 */
(function () {
  const STORAGE_KEY_PREFIX = 'panol-tour-seen-';

  function panolTour() {
    let steps = [];
    let stepIndex = 0;
    let overlay, spotlight, popover;

    function build() {
      overlay = document.createElement('div');
      overlay.className = 'panol-tour-overlay';

      spotlight = document.createElement('div');
      spotlight.className = 'panol-tour-spotlight';

      popover = document.createElement('div');
      popover.className = 'panol-tour-popover';

      document.body.appendChild(overlay);
      document.body.appendChild(spotlight);
      document.body.appendChild(popover);

      overlay.addEventListener('click', stop);
    }

    function destroy() {
      [overlay, spotlight, popover].forEach((el) => el && el.remove());
      overlay = spotlight = popover = null;
      document.removeEventListener('keydown', onKeydown);
    }

    function onKeydown(e) {
      if (e.key === 'Escape') stop();
      if (e.key === 'ArrowRight') next();
      if (e.key === 'ArrowLeft') prev();
    }

    function findCurrentTarget() {
      // Salta pasos cuyo elemento no exista ahora mismo (ej. botones que
      // solo se ven para cierto rol, o un modal que no está abierto).
      while (stepIndex < steps.length) {
        const el = document.querySelector(steps[stepIndex].selector);
        if (el && el.offsetParent !== null) return el; // offsetParent null = oculto
        stepIndex += 1;
      }
      return null;
    }

    function render() {
      const target = findCurrentTarget();
      if (!target) {
        stop();
        return;
      }
      const step = steps[stepIndex];
      const rect = target.getBoundingClientRect();
      const pad = 6;

      target.scrollIntoView({ block: 'center', behavior: 'instant' });
      // Recalcular después del scroll
      requestAnimationFrame(() => {
        const r = target.getBoundingClientRect();
        spotlight.style.top = `${r.top - pad}px`;
        spotlight.style.left = `${r.left - pad}px`;
        spotlight.style.width = `${r.width + pad * 2}px`;
        spotlight.style.height = `${r.height + pad * 2}px`;

        popover.innerHTML = `
          <div class="panol-tour-popover-step">Paso ${stepIndex + 1} de ${steps.length}</div>
          <div class="panol-tour-popover-title">${escapeHtml(step.title || '')}</div>
          <div class="panol-tour-popover-text">${escapeHtml(step.text || '')}</div>
          <div class="panol-tour-popover-actions">
            <button type="button" data-action="exit">Salir</button>
            <div>
              <button type="button" data-action="prev" ${stepIndex === 0 ? 'disabled' : ''}>← Anterior</button>
              <button type="button" data-action="next">${stepIndex === steps.length - 1 ? 'Listo ✓' : 'Siguiente →'}</button>
            </div>
          </div>
        `;
        popover.querySelector('[data-action="exit"]').onclick = stop;
        popover.querySelector('[data-action="prev"]').onclick = prev;
        popover.querySelector('[data-action="next"]').onclick = next;

        // Posicionar el globo debajo del elemento si hay espacio, si no arriba.
        const popRect = popover.getBoundingClientRect();
        let top = r.bottom + 14;
        if (top + popRect.height > window.innerHeight - 12) {
          top = Math.max(12, r.top - popRect.height - 14);
        }
        let left = Math.min(Math.max(12, r.left), window.innerWidth - popRect.width - 12);
        popover.style.top = `${top}px`;
        popover.style.left = `${left}px`;
      });
    }

    function next() {
      if (stepIndex >= steps.length - 1) {
        stop();
        return;
      }
      stepIndex += 1;
      render();
    }

    function prev() {
      if (stepIndex === 0) return;
      stepIndex -= 1;
      render();
    }

    function stop() {
      destroy();
    }

    function start(newSteps, opts) {
      opts = opts || {};
      if (!newSteps || newSteps.length === 0) return;
      steps = newSteps;
      stepIndex = 0;
      build();
      document.addEventListener('keydown', onKeydown);
      render();
      if (opts.key) {
        try { localStorage.setItem(STORAGE_KEY_PREFIX + opts.key, '1'); } catch (e) { /* localStorage bloqueado, no pasa nada */ }
      }
    }

    function hasSeen(key) {
      try { return localStorage.getItem(STORAGE_KEY_PREFIX + key) === '1'; } catch (e) { return true; }
    }

    return { start, stop, hasSeen };
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  window.panolTour = panolTour();
})();
