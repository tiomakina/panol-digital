#!/usr/bin/env python3
"""
Pañol 360 — Suite de pruebas automatizadas de QA
Corre desde dentro del contenedor backend o en la red Docker interna.

Uso en el servidor:
  docker exec panol-digital-backend-1 python3 /tmp/qa_test.py

O copiando primero:
  docker cp scripts/qa_test.py panol-digital-backend-1:/tmp/qa_test.py
  docker exec panol-digital-backend-1 python3 /tmp/qa_test.py
"""
import urllib.request
import urllib.error
import urllib.parse
import json
import sys
import datetime
import os

BASE = "http://localhost:8000"
TENANT = "vms-ingenieria"
OUTPUT_FILE = "/tmp/qa_results.json"   # archivo de resultados para copiar después

results = []

# ── Limpiar rate limit en Redis antes de correr ──────────────────────────────
# Evita que el bucket de 127.0.0.1 (desde dentro del contenedor) bloquee
# los intentos de login del test y distorsione los resultados.
def _clear_rate_limits():
    try:
        import redis as _redis
        r = _redis.from_url("redis://redis:6379/0", decode_responses=True)
        keys = r.keys("ratelimit:login:*") + r.keys("ratelimit:2fa:*")
        if keys:
            r.delete(*keys)
            print(f"  [setup] Limpiados {len(keys)} buckets de rate limit en Redis")
        else:
            print("  [setup] Rate limit: ningún bucket previo en Redis")
    except Exception as ex:
        print(f"  [setup] No se pudo limpiar rate limit (continúa igualmente): {ex}")

_clear_rate_limits()

def req(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json", "Cookie": f"panol_tenant={TENANT}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except Exception:
                # Respuesta no-JSON (ej: /health devuelve texto plano "ok")
                return resp.status, {"_text": raw.decode(errors="replace")}
    except urllib.error.HTTPError as e:
        try: body_data = json.loads(e.read())
        except: body_data = {}
        return e.code, body_data
    except Exception as ex:
        return 0, {"error": str(ex)}

def test(name, passed, detail=""):
    mark = "✅ PASS" if passed else "❌ FAIL"
    results.append({"name": name, "passed": passed, "detail": detail})
    print(f"{mark}  {name}")
    if detail: print(f"       → {detail}")
    return passed

def login(rut, password):
    """
    El endpoint /api/v1/auth/login usa OAuth2PasswordRequestForm:
    - Content-Type: application/x-www-form-urlencoded  (no JSON)
    - campo 'username' = el RUT  (el backend lo convierte a formato canónico)
    - campo 'password' = la contraseña
    """
    url = BASE + "/api/v1/auth/login"
    form = urllib.parse.urlencode({"username": rut, "password": password}).encode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": f"panol_tenant={TENANT}",
    }
    r = urllib.request.Request(url, data=form, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("access_token"), resp.status, data.get("detail", "")
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read())
        except: body = {}
        detail = body.get("detail", str(body))
        return None, e.code, detail
    except Exception as ex:
        return None, 0, str(ex)

print("\n" + "═"*62)
print("  Pañol 360 — Suite de QA automatizada")
print(f"  Tenant: {TENANT}  |  Base: {BASE}")
print("═"*62 + "\n")

# ─── 1. Autenticación ────────────────────────────────────────────────────────
print("── AUTENTICACIÓN ─────────────────────────────────────────")

tk_j, st_j, det_j = login("1-9", "Admin123!")
test("Login Jefe  (1-9 / Admin123!)", bool(tk_j), f"status={st_j} {'OK' if tk_j else det_j}")

tk_e, st_e, det_e = login("2-7", "Admin123!")
test("Login Encargado (2-7 / Admin123!)", bool(tk_e), f"status={st_e} {'' if tk_e else det_e}")

tk_m, st_m, det_m = login("3-5", "Admin123!")
test("Login Mecánico (3-5 / Admin123!)", bool(tk_m), f"status={st_m} {'' if tk_m else det_m}")

_, st, det = login("1-9", "MalaClave!")
test("Contraseña incorrecta → 401", st == 401, f"status={st} detail={det}")

_, st, _ = login("99-0", "Admin123!")
test("RUT inexistente → 401", st == 401, f"status={st}")

st, _ = req("GET", "/api/v1/tools")
test("Sin token → 401 en endpoint protegido", st == 401, f"status={st}")

# ─── 2. Dashboard ────────────────────────────────────────────────────────────
print("\n── DASHBOARD ─────────────────────────────────────────────")
if tk_j:
    st, d = req("GET", "/api/v1/dashboard/stats", token=tk_j)
    test("Stats dashboard (Jefe)", st == 200, f"tools={d.get('total_tools')} loans={d.get('active_loans')} overdue={d.get('overdue_loans')}")
    test("inventory_value presente para Jefe", "inventory_value" in d, f"valor={d.get('inventory_value')}")

if tk_m:
    st, d = req("GET", "/api/v1/dashboard/stats", token=tk_m)
    test("Stats dashboard (Mecánico)", st == 200, f"status={st}")
    test("[RBAC] inventory_value OCULTO para Mecánico", not d.get("inventory_value"), f"valor={d.get('inventory_value')}")

# ─── 3. Herramientas ─────────────────────────────────────────────────────────
print("\n── HERRAMIENTAS ──────────────────────────────────────────")
if tk_j:
    st, d = req("GET", "/api/v1/tools", token=tk_j)
    tools = d if isinstance(d, list) else d.get("items", [])
    test("Listar herramientas (Jefe)", st == 200, f"count={len(tools)}")

    # Obtener IDs de tablas maestras
    _, cats  = req("GET", "/api/v1/lookups/categories", token=tk_j)
    _, brands = req("GET", "/api/v1/lookups/brands", token=tk_j)
    _, locs   = req("GET", "/api/v1/lookups/locations", token=tk_j)
    cat_id   = cats[0]["id"]   if isinstance(cats, list)   and cats   else None
    brand_id = brands[0]["id"] if isinstance(brands, list) and brands else None
    loc_id   = locs[0]["id"]   if isinstance(locs, list)   and locs   else None

    nueva = {"code":"QA-AUTO-001","name":"Herramienta QA Automatizada",
             "serial_number":"SN-QA-001","status":"available","purchase_price":25000,
             "category_id":cat_id,"brand_id":brand_id,"location_id":loc_id}
    st, d = req("POST", "/api/v1/tools", body=nueva, token=tk_j)
    created_id = d.get("id") if st in (200,201) else None
    test("Crear herramienta (Jefe)", st in (200,201), f"status={st} id={created_id}")

if tk_m:
    st, _ = req("POST", "/api/v1/tools", body={"code":"X","name":"X","status":"available"}, token=tk_m)
    test("[RBAC] Mecánico NO puede crear herramienta", st == 403, f"status={st}")

# ─── 4. Préstamos ────────────────────────────────────────────────────────────
print("\n── PRÉSTAMOS ─────────────────────────────────────────────")
if tk_j:
    st, d = req("GET", "/api/v1/loans", token=tk_j)
    loans = d if isinstance(d,list) else []
    test("Listar préstamos (Jefe)", st == 200, f"count={len(loans)}")

if tk_m:
    st, d = req("GET", "/api/v1/loans", token=tk_m)
    loans_m = d if isinstance(d,list) else []
    test("Mecánico ve préstamos (solo los suyos)", st == 200, f"count={len(loans_m)}")

# ─── 5. Usuarios ─────────────────────────────────────────────────────────────
print("\n── USUARIOS ──────────────────────────────────────────────")
if tk_j:
    st, d = req("GET", "/api/v1/users", token=tk_j)
    users = d if isinstance(d,list) else []
    test("Listar usuarios (Jefe)", st == 200, f"count={len(users)}")
    roles = {u.get("role") for u in users if "role" in u}
    print(f"       → Roles en el sistema: {', '.join(sorted(roles))}")
    has_full_names = all(u.get("full_name") for u in users[:3])
    test("Usuarios tienen nombre completo (no solo ID)", has_full_names)

if tk_m:
    st, _ = req("POST", "/api/v1/users", body={"rut":"98-7","full_name":"Test","password":"Test123!","role":"mecanico"}, token=tk_m)
    test("[RBAC] Mecánico NO puede crear usuario", st in (403,422), f"status={st}")

# ─── 6. Tablas maestras ──────────────────────────────────────────────────────
print("\n── TABLAS MAESTRAS ───────────────────────────────────────")
if tk_j:
    for path, lbl in [("/api/v1/lookups/categories","Categorías"),("/api/v1/lookups/brands","Marcas"),
                      ("/api/v1/lookups/locations","Ubicaciones"),("/api/v1/lookups/suppliers","Proveedores")]:
        st, d = req("GET", path, token=tk_j)
        count = len(d) if isinstance(d,list) else "?"
        test(f"Listar {lbl}", st == 200, f"count={count}")

# ─── 7. Reportes ─────────────────────────────────────────────────────────────
print("\n── REPORTES ──────────────────────────────────────────────")
if tk_j:
    for path, lbl in [("/api/v1/reports/inventory","Inventario"),
                      ("/api/v1/reports/loans","Préstamos"),
                      ("/api/v1/reports/maintenance","Mantenimiento")]:
        st, _ = req("GET", path, token=tk_j)
        test(f"Reporte {lbl} (Jefe)", st == 200, f"status={st}")

if tk_m:
    st, _ = req("GET", "/api/v1/reports/inventory", token=tk_m)
    test("[RBAC] Reporte denegado para Mecánico", st == 403, f"status={st}")

# ─── 8. Notificaciones ───────────────────────────────────────────────────────
print("\n── NOTIFICACIONES ────────────────────────────────────────")
if tk_j:
    st, d = req("GET", "/api/v1/notifications/config", token=tk_j)
    test("Config notificaciones", st == 200, f"email={d.get('email_enabled')} wa={d.get('whatsapp_enabled')}")

    st, d = req("GET", "/api/v1/notifications/whatsapp/status", token=tk_j)
    test("Estado WhatsApp", st == 200, f"state={d.get('state')} connected={d.get('connected')}")

    st, d = req("GET", "/api/v1/notifications/log", token=tk_j)
    log_count = d.get("count", 0) if st == 200 else "?"
    test("Log de notificaciones", st == 200, f"entradas={log_count}")

# ─── 9. Respaldo ─────────────────────────────────────────────────────────────
print("\n── RESPALDO ──────────────────────────────────────────────")
if tk_j:
    st, d = req("GET", "/api/v1/backup", token=tk_j)
    test("Listar backups (Jefe)", st == 200, f"count={len(d) if isinstance(d,list) else '?'}")

if tk_m:
    st, _ = req("GET", "/api/v1/backup", token=tk_m)
    test("[RBAC] Backup denegado para Mecánico", st == 403, f"status={st}")

# ─── 10. Mantenimiento ───────────────────────────────────────────────────────
print("\n── MANTENIMIENTO ─────────────────────────────────────────")
if tk_j:
    st, d = req("GET", "/api/v1/maintenance", token=tk_j)
    count = len(d) if isinstance(d,list) else d.get("total","?")
    test("Listar mantenimiento (Jefe)", st == 200, f"count={count}")

# ─── 11. Cajas ───────────────────────────────────────────────────────────────
print("\n── CAJAS ─────────────────────────────────────────────────")
if tk_j:
    st, d = req("GET", "/api/v1/toolboxes", token=tk_j)
    count = len(d) if isinstance(d,list) else "?"
    test("Listar cajas (Jefe)", st == 200, f"count={count}")

# ─── 12. Health ──────────────────────────────────────────────────────────────
print("\n── SISTEMA ───────────────────────────────────────────────")
st, d = req("GET", "/health")
test("Health check", st == 200, f"status={st} body={d.get('_text','')[:20]}")

# Verificar que proxy-headers funciona (IP real, no Docker IP)
if tk_j:
    # Leer la IP que el backend ve en request.client.host
    # Si --proxy-headers funciona, debería ser la IP real del cliente, no 172.x.x.x
    st, d = req("GET", "/api/v1/auth/me", token=tk_j)
    test("Endpoint /me accesible (verifica JWT)", st == 200, f"user={d.get('full_name','?')} role={d.get('role','?')}")

# ─── Resumen ─────────────────────────────────────────────────────────────────
print("\n" + "═"*62)
total = len(results)
passed = sum(1 for r in results if r["passed"])
failed = total - passed
print(f"  RESULTADO: {passed}/{total} pruebas OK  |  {failed} fallidas")
print("═"*62)

if failed:
    print("\n❌ FALLIDAS:")
    for r in results:
        if not r["passed"]:
            print(f"  • {r['name']}")
            if r["detail"]: print(f"    {r['detail']}")
print()

# ─── Guardar resultados a archivo JSON ───────────────────────────────────────
output = {
    "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "tenant": TENANT,
    "base_url": BASE,
    "summary": {"total": total, "passed": passed, "failed": failed,
                 "pct": round(passed / total * 100) if total else 0},
    "results": results,
}
try:
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"📄 Resultados guardados en {OUTPUT_FILE}")
    print(f"   Para copiar al host: docker cp panol-digital-backend-1:{OUTPUT_FILE} ./qa_results.json")
except Exception as ex:
    print(f"  [warn] No se pudo guardar resultados: {ex}")

sys.exit(0 if failed == 0 else 1)
