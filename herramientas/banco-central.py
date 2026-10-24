#!/usr/bin/env python3
"""Trae series del Banco Central y las deja en la carpeta datos/ para la app.

La API de la Base de Datos Estadísticos (BDE) del Banco Central pide usuario y clave, así que no se consulta
desde el iPhone: esta tarea corre en GitHub Actions (.github/workflows/banco-central.yml) cada mañana, con
las credenciales guardadas como secretos del repositorio (BCCH_USER y BCCH_PASS). La app lee los archivos.

Series:
  datos/consumo.json       F022.CON.TIP.Z.NO.Z.M, tasa promedio de créditos de consumo, total (pesos), mensual.
  datos/imacec-desest.json Imacec desestacionalizado (índice), mensual. Con él la app calcula la variación
                           respecto del mes anterior. Si el código no es el esperado, se busca por su nombre.

Cada archivo solo cambia cuando cambia su serie (un mes nuevo o una revisión), para no llenar el repositorio
de publicaciones iguales. Si una serie falla, las demás se guardan igual y la tarea avisa el problema.
"""
import datetime, json, os, pathlib, re, sys, urllib.error, urllib.parse, urllib.request

URL = 'https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx'
DATOS = pathlib.Path(__file__).resolve().parent.parent / 'datos'
EN_GITHUB = bool(os.environ.get('GITHUB_ACTIONS'))


def aviso(nivel, msg):
    # En GitHub Actions, «::error::» y «::warning::» dejan el mensaje a la vista en el resumen de la tarea
    print(('::%s::' % nivel if EN_GITHUB else '') + msg)


def falla(msg):
    aviso('error', msg)
    sys.exit(1)


usuario = os.environ.get('BCCH_USER', '').strip()
clave = os.environ.get('BCCH_PASS', '').strip()
if not usuario or not clave:
    falla('Faltan los secretos BCCH_USER y BCCH_PASS en Settings → Secrets and variables → Actions.')


class Rechazo(Exception):
    pass


def api(**params):
    """Consulta la API. La dirección lleva la clave: los errores se informan sin ella."""
    consulta = urllib.parse.urlencode(dict(params, user=usuario, **{'pass': clave}))
    pedido = urllib.request.Request(URL + '?' + consulta, headers={'User-Agent': 'indicadores (GitHub Actions)'})
    try:
        with urllib.request.urlopen(pedido, timeout=120) as r:
            crudo = r.read()
            juego = r.headers.get_content_charset() or ''
    except urllib.error.HTTPError as e:
        raise Rechazo('el Banco Central respondió con un error HTTP %s' % e.code)
    except urllib.error.URLError as e:
        raise Rechazo('no se pudo conectar con el Banco Central (%s)' % getattr(e, 'reason', type(e).__name__))
    except Exception as e:  # noqa: BLE001
        raise Rechazo('no se pudo conectar con el Banco Central (%s)' % type(e).__name__)
    # El Banco Central puede responder en UTF-8 o en la codificación de Windows (Latin-1), según el servidor
    texto = None
    for cod in [juego, 'utf-8-sig', 'cp1252', 'latin-1']:
        if not cod:
            continue
        try:
            texto = crudo.decode(cod)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    try:
        resp = json.loads(texto)
    except (TypeError, ValueError):
        raise Rechazo('el Banco Central no devolvió datos legibles')
    codigo = str(resp.get('Codigo'))
    if codigo == '-5':
        # Usuario o clave rechazados. Para revisar los secretos sin mostrarlos: solo su forma, nunca su contenido.
        raras = set('$#"\'\\&+%? ')
        pistas = [
            'usuario de %d caracteres%s' % (len(usuario), '' if '@' in usuario and '.' in usuario.split('@')[-1] else ', no parece un correo'),
            'con mayúsculas' if usuario != usuario.lower() else 'en minúsculas',
            'clave de %d caracteres' % len(clave),
        ]
        if any(c in raras for c in clave):
            pistas.append('la clave tiene símbolos que la API suele rechazar ($ # comillas \\ & + % ? o espacios)')
        if any(ord(c) > 126 for c in usuario + clave):
            pistas.append('hay letras con tilde, ñ u otros caracteres especiales')
        falla('El Banco Central rechazó el usuario o la clave (código -5). Revisión de los secretos: ' + '; '.join(pistas) + '.')
    if codigo != '0':
        raise Rechazo('el Banco Central rechazó la consulta: %s (código %s)' % (resp.get('Descripcion'), codigo))
    return resp


def leer_serie(codigo):
    resp = api(function='GetSeries', timeseries=codigo, firstdate='2002-01-01', lastdate=datetime.date.today().isoformat())
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
    return str(serie.get('descripEsp') or ''), obs


def sin_tildes(s):
    return s.lower().translate(str.maketrans('áéíóúü', 'aeiouu'))


def buscar_imacec_desest():
    """Busca, entre las series mensuales, el Imacec total desestacionalizado (índice)."""
    resp = api(function='SearchSeries', frequency='MONTHLY')
    candidatas = []
    for s in resp.get('SeriesInfos') or []:
        titulo = sin_tildes(str(s.get('spanishTitle') or ''))
        codigo = str(s.get('seriesId') or '')
        if 'imacec' not in titulo or 'desestacionaliz' not in titulo:
            continue
        if re.search(r'minero|no minero|mineria|resto|industria|comercio|servicio|produccion|impuesto|variaci|incidencia|tendencia', titulo):
            continue
        ref = re.search(r'EP(\d{2})', codigo)                 # año de referencia (EP18 = 2018): el más nuevo primero
        candidatas.append((0 if codigo.startswith('F032.IMC.IND') else 1, -int(ref.group(1)) if ref else 0, codigo))
    if not candidatas:
        raise Rechazo('no se encontró el Imacec desestacionalizado entre las series del Banco Central')
    candidatas.sort()
    return candidatas[0][2]


def guardar(nombre_archivo, codigo, nombre, obs, extra=None):
    destino = DATOS / nombre_archivo
    anterior = None
    if destino.exists():
        try:
            anterior = json.loads(destino.read_text(encoding='utf-8'))
        except ValueError:
            anterior = None
    if anterior and anterior.get('obs') == obs and anterior.get('serie') == codigo:
        print('%s sin cambios: último dato %s, %s.' % (nombre_archivo, obs[-1][0], obs[-1][1]))
        return
    datos = {
        'serie': codigo,
        'nombre': nombre,
        'fuente': 'Banco Central de Chile, API de la Base de Datos Estadísticos',
        'actualizado': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    datos.update(extra or {})
    datos['obs'] = obs
    DATOS.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('%s guardado: %d meses, último %s con %s.' % (nombre_archivo, len(obs), obs[-1][0], obs[-1][1]))


# ---------- Tasa promedio de créditos de consumo ----------
def consumo():
    codigo = 'F022.CON.TIP.Z.NO.Z.M'
    nombre, obs = leer_serie(codigo)
    if not obs:
        raise Rechazo('la serie %s llegó vacía' % codigo)
    guardar('consumo.json', codigo, nombre or 'Tasa promedio de créditos de consumo, total (pesos)', obs)


# ---------- Imacec desestacionalizado ----------
def imacec_desest():
    codigo = 'F032.IMC.IND.Z.Z.EP18.Z.Z.1.M'     # el código habitual; se confirma por su nombre
    nombre, obs = '', []
    try:
        nombre, obs = leer_serie(codigo)
    except Rechazo:
        pass
    titulo = sin_tildes(nombre)
    if not obs or 'desestacionaliz' not in titulo or re.search(r'minero|no minero|resto', titulo):
        codigo = buscar_imacec_desest()
        nombre, obs = leer_serie(codigo)
        aviso('notice', 'Imacec desestacionalizado: se usa la serie %s (%s).' % (codigo, nombre))
    if not obs:
        raise Rechazo('la serie del Imacec desestacionalizado llegó vacía')
    guardar('imacec-desest.json', codigo, nombre or 'Imacec desestacionalizado', obs)


fallas = []
for nombre_tarea, tarea in [('Créditos de consumo', consumo), ('Imacec desestacionalizado', imacec_desest)]:
    try:
        tarea()
    except Rechazo as e:
        fallas.append(nombre_tarea)
        aviso('warning', '%s: %s.' % (nombre_tarea, e))
if len(fallas) == 2:
    falla('No se pudo traer ninguna serie del Banco Central.')
