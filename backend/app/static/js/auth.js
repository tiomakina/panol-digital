/**
 * Auth helper compartido — el sistema usa JWT en localStorage (no cookies de
 * sesión), así que cada pantalla protegida necesita: 1) verificar que haya
 * token al cargar, 2) mandarlo en cada request a la API, 3) mandar a /login
 * si el servidor dice que expiró. Este archivo centraliza esas tres cosas
 * para que no se repita (y se olvide) en cada template.
 */

const ACCESS_TOKEN_KEY = 'panol-access-token';
const REFRESH_TOKEN_KEY = 'panol-refresh-token';

function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function clearSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

/** Redirige a /login si no hay token guardado. Llamar al iniciar cada página protegida. */
function requireAuth() {
  if (!getAccessToken()) {
    window.location.href = '/login';
    return false;
  }
  return true;
}

/**
 * fetch() con el header Authorization ya puesto. Si la API responde 401
 * (token vencido o revocado), limpia la sesión y manda a /login.
 */
async function authFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    clearSession();
    window.location.href = '/login';
  }
  return res;
}

/**
 * Devuelve el usuario autenticado (para mostrar/ocultar acciones según su
 * rol en la UI — la autorización real siempre la hace el backend, esto es
 * solo para no mostrar botones que el usuario no puede usar).
 */
async function getCurrentUser() {
  const res = await authFetch('/api/v1/auth/me');
  if (!res.ok) return null;
  return res.json();
}

const ROLE_RANK = { jefe: 3, encargado: 2, mecanico: 1 };

/** ¿El rol del usuario alcanza el mínimo requerido? (jefe > encargado > mecanico) */
function hasRole(user, minRole) {
  if (!user) return false;
  return (ROLE_RANK[user.role] || 0) >= (ROLE_RANK[minRole] || 0);
}

// HTMX no sabe nada de localStorage — sin esto, cualquier hx-get/hx-post a
// un endpoint de la API que requiera login llegaría sin el header y el
// usuario vería un error 401 en vez del contenido.
document.addEventListener('htmx:configRequest', (event) => {
  const token = getAccessToken();
  if (token) event.detail.headers['Authorization'] = `Bearer ${token}`;
});

document.addEventListener('htmx:responseError', (event) => {
  if (event.detail.xhr.status === 401) {
    clearSession();
    window.location.href = '/login';
  }
});
