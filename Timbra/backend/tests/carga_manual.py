"""Prueba de carga: N cuentas a la vez timbrando (PAC demo), bajando PDF, subiendo XML y leyendo el resumen.
Corre contra un servidor con datos NUEVOS en el puerto 8013 (DATA_DIR vacío, PROGRAMADOR=False); NUNCA contra el real.
Uso: .venv\Scripts\python tests\carga_manual.py [cuentas] [facturas_por_cuenta]
Resultado del 13-oct-2026 (10 cuentas x 20 facturas, PAC simulado de 1.5 s): 0 errores, timbrar p95 3.2 s."""
import statistics, sys, threading, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import httpx

from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from test_v5_clientes import rfc_moral  # noqa: E402
from test_w6_xml import efirma_de_prueba  # noqa: E402

B = "http://127.0.0.1:8013/api"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
F = int(sys.argv[2]) if len(sys.argv) > 2 else 20
tiempos = defaultdict(list)
errores = defaultdict(list)
candado = threading.Lock()


def llamar(c, que, metodo, ruta, **kw):
    t0 = time.perf_counter()
    try:
        r = c.request(metodo, B + ruta, **kw)
        ok = r.status_code < 300
        detalle = None if ok else f"{r.status_code} {r.text[:160]}"
    except httpx.HTTPError as e:
        r, ok, detalle = None, False, f"{type(e).__name__}: {e}"
    with candado:
        tiempos[que].append(time.perf_counter() - t0)
        if not ok:
            errores[que].append(detalle)
    return r if ok else None


c0 = httpx.Client(timeout=120)
for _ in range(60):
    try:
        if c0.get(B + "/health").status_code == 200:
            break
    except httpx.HTTPError:
        time.sleep(1)
adm = {"Authorization": "Bearer " + c0.post(B + "/auth/login", json={"email": "rick@erickddp.com", "password": "cambiame"}).json()["token"]}

print(f"Preparando {N} cuentas…")
cuentas = []
for i in range(N):
    usuario = f"carga{i:02d}"
    c0.post(B + "/auth/usuarios", headers=adm, json={"email": f"{usuario}@prueba.mx", "usuario": usuario, "nombre": usuario, "password": "claveLarga1"})
    h = {"Authorization": "Bearer " + c0.post(B + "/auth/login", json={"email": usuario, "password": "claveLarga1"}).json()["token"]}
    rfc = rfc_moral(200 + i)
    e = c0.post(B + "/emisores", headers=h, json={"rfc": rfc, "nombre": f"EMPRESA CARGA {i:02d}", "regimen_fiscal": "601", "lugar_expedicion": "42501"})
    e = e.json() if e.status_code == 200 else next(x for x in c0.get(B + "/emisores", headers=h).json() if x["rfc"] == rfc)
    cer, key = efirma_de_prueba(rfc, csd=True)
    r = c0.post(B + f"/emisores/{e['id']}/csd", headers=h, files={"cer": ("a.cer", cer), "key": ("a.key", key)}, data={"password": "12345678a"})
    assert r.status_code == 200, r.text
    cuentas.append((h, e))

CONCEPTO = [{"clave_prod_serv": "84111506", "clave_unidad": "E48", "descripcion": "SERVICIO DE CARGA", "cantidad": "1", "valor_unitario": "1000",
             "objeto_imp": "02", "impuestos": [{"tipo": "traslado", "impuesto": "002", "factor": "Tasa", "tasa": "0.16"}]}]


def trabajo(h, e):
    c = httpx.Client(timeout=180)
    hechas = []
    for k in range(F):
        r = llamar(c, "timbrar", "POST", "/facturas", headers=h, json={"emisor_id": e["id"], "publico_general": True, "forma_pago": "01",
                                                                        "metodo_pago": "PUE", "conceptos": CONCEPTO})
        if r:
            hechas.append(r.json())
        if k % 5 == 0:
            llamar(c, "resumen", "GET", f"/dashboard?emisor_id={e['id']}", headers=h)
            llamar(c, "lista facturas", "GET", f"/facturas?emisor_id={e['id']}&limit=50", headers=h)
    for f in hechas[:3]:
        llamar(c, "pdf", "GET", f"/facturas/{f['id']}/pdf", headers=h)
    # sus propios XML al módulo de XML del SAT, y el Excel
    xmls = []
    for f in hechas[:10]:
        r = llamar(c, "bajar xml", "GET", f"/facturas/{f['id']}/xml", headers=h)
        if r:
            xmls.append(("archivos", (f"{f['uuid']}.xml", r.content, "application/xml")))
    if xmls:
        llamar(c, "subir xml", "POST", f"/xml/subir?emisor_id={e['id']}", headers=h, files=xmls)
    llamar(c, "excel xml", "POST", "/xml/excel", headers=h, json={"emisor_id": e["id"]})
    return hechas


print(f"Arranca: {N} cuentas × {F} facturas, todas a la vez")
t0 = time.perf_counter()
with ThreadPoolExecutor(N) as ex:
    resultados = list(ex.map(lambda x: trabajo(*x), cuentas))
total = time.perf_counter() - t0

print(f"\nTiempo total: {total:.1f} s")
print(f"{'operación':16} {'veces':>6} {'media':>7} {'p95':>7} {'máx':>7}  errores")
for que, ts in tiempos.items():
    ts = sorted(ts)
    p95 = ts[int(len(ts) * 0.95) - 1] if len(ts) > 1 else ts[0]
    print(f"{que:16} {len(ts):6} {statistics.mean(ts):7.2f} {p95:7.2f} {ts[-1]:7.2f}  {len(errores[que])}")
for que, es in errores.items():
    for d in sorted(set(es))[:4]:
        print(f"  ! {que}: {d}")

# folios: ninguno repetido por emisor
for (h, e), hechas in zip(cuentas, resultados):
    folios = [f"{f['serie']}{f['folio']}" for f in hechas]
    if len(folios) != len(set(folios)):
        print(f"  ! FOLIOS REPETIDOS en {e['rfc']}: {len(folios) - len(set(folios))}")
    lista = c0.get(B + f"/facturas?emisor_id={e['id']}&limit=1000", headers=h).json()
    if len(lista) != len(hechas):
        print(f"  ! {e['rfc']}: timbró {len(hechas)} pero la lista tiene {len(lista)}")
print("Revisión de folios y listas terminada.")
