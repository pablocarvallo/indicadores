#!/usr/bin/env python3
"""Trae del Banco Central la tasa promedio de créditos de consumo y la deja en datos/consumo.json.

La API de la Base de Datos Estadísticos (BDE) del Banco Central pide usuario y clave, así que no se consulta
desde el iPhone: esta tarea corre en GitHub Actions (.github/workflows/banco-central.yml) cada mañana, con
las credenciales guardadas como secretos del repositorio (BCCH_USER y BCCH_PASS). La app lee el archivo.

Serie: F022.CON.TIP.Z.NO.Z.M, «Tasa promedio de créditos de consumo, total (pesos)», mensual desde 2002.

El archivo solo cambia cuando cambia la serie (un mes nuevo o una revisión), para no llenar el
repositorio de publicaciones iguales.
"""
import datetime, json, os, pathlib, sys, urllib.error, urllib.parse, urllib.request

SERIE = 'F022.CON.TIP.Z.NO.Z.M'
NOMBRE = 'Tasa promedio de créditos de consumo, total (pesos)'
URL = 'https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx'
DESTINO = pathlib.Path(__file__).resolve().parent.parent / 'datos' / 'consumo.json'


def falla(msg):
    # En GitHub Actions, «::error::» deja el mensaje a la vista en el resumen de la tarea
    print(('::error::' if os.environ.get('GITHUB_ACTIONS') else '') + msg)
    sys.exit(1)


usuario = os.environ.get('BCCH_USER', '').strip()
clave = os.environ.get('BCCH_PASS', '').strip()
if not usuario or not clave:
    falla('Faltan los secretos BCCH_USER y BCCH_PASS en Settings → Secrets and variables → Actions.')

hoy = datetime.date.today().isoformat()
consulta = urllib.parse.urlencode({
    'user': usuario, 'pass': clave, 'firstdate': '2002-01-01', 'lastdate': hoy,
    'timeseries': SERIE, 'function': 'GetSeries',
})
pedido = urllib.request.Request(URL + '?' + consulta, headers={'User-Agent': 'indicadores (GitHub Actions)'})
# La dirección lleva la clave: los errores se informan sin ella
try:
    with urllib.request.urlopen(pedido, timeout=90) as r:
        texto = r.read().decode('utf-8-sig')
except urllib.error.HTTPError as e:
    falla('El Banco Central respondió con un error HTTP %s.' % e.code)
except urllib.error.URLError as e:
    falla('No se pudo conectar con el Banco Central (%s).' % getattr(e, 'reason', type(e).__name__))
except Exception as e:  # noqa: BLE001
    falla('No se pudo conectar con el Banco Central (%s).' % type(e).__name__)

try:
    resp = json.loads(texto)
except ValueError:
    falla('El Banco Central no devolvió datos legibles.')
if str(resp.get('Codigo')) != '0':
    # Por ejemplo, -5: usuario o clave incorrectos, o credenciales sin activar
    falla('El Banco Central rechazó la consulta: %s (código %s).' % (resp.get('Descripcion'), resp.get('Codigo')))

serie = resp.get('Series') or {}
obs = []
for o in serie.get('Obs') or []:
    fecha = str(o.get('indexDateString', ''))           # dd-mm-aaaa
    valor = str(o.get('value', '')).strip().replace(',', '.')
    try:
        v = float(valor)
    except ValueError:
        continue                                         # «NaN», «NeuN» u otro texto: sin dato
    partes = fecha.split('-')
    if v != v or len(partes) != 3:
        continue
    obs.append(['%s-%s-%s' % (partes[2], partes[1].zfill(2), partes[0].zfill(2)), round(v, 4)])
obs.sort()
if not obs:
    falla('La serie %s llegó vacía.' % SERIE)

anterior = None
if DESTINO.exists():
    try:
        anterior = json.loads(DESTINO.read_text(encoding='utf-8'))
    except ValueError:
        anterior = None
if anterior and anterior.get('obs') == obs:
    print('Sin cambios: último dato %s, %s%%.' % (obs[-1][0], obs[-1][1]))
    sys.exit(0)

datos = {
    'serie': SERIE,
    'nombre': serie.get('descripEsp') or NOMBRE,
    'fuente': 'Banco Central de Chile, API de la Base de Datos Estadísticos',
    'actualizado': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'obs': obs,
}
DESTINO.parent.mkdir(parents=True, exist_ok=True)
DESTINO.write_text(json.dumps(datos, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
print('Guardado: %d meses, último %s con %s%%.' % (len(obs), obs[-1][0], obs[-1][1]))
