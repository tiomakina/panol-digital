/**
 * Service Worker de Pañol v2.0 — cachea el "app shell" (JS/CSS/íconos) para
 * que la app instalada abra rápido y muestre un aviso claro si no hay
 * conexión, en vez de la pantalla de error genérica del navegador.
 *
 * A propósito NO cachea nada bajo /api/ — el inventario, los préstamos y
 * todo lo demás siempre tienen que venir en vivo del servidor.
 */
const CACHE_NAME = 'panol-shell-v3';  // incrementar al actualizar archivos estáticos
const APP_SHELL = [
  '/static/vendor/htmx.min.js',
  '/static/vendor/alpine.min.js',
  '/static/vendor/chart.umd.js',
  '/static/js/auth.js',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/offline.html',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin) return; // no tocar CDNs/orígenes externos
  if (url.pathname.startsWith('/api/')) return;     // la API siempre en vivo, nunca cacheada

  // Navegación a una pantalla (click en un link, F5, etc.): red primero;
  // si no hay conexión, mostrar la página offline en vez del error del navegador.
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match('/static/offline.html')));
    return;
  }

  // Assets propios (vendor JS, CSS, íconos): cache primero, red de respaldo.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
  }
});
