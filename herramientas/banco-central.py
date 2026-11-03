#!/usr/bin/env python3
"""Trae series del Banco Central y las deja en la carpeta datos/ para la app.

La API de la Base de Datos Estadísticos (BDE) del Banco Central pide usuario y clave, así que no se consulta
desde el iPhone: esta tarea corre en GitHub Actions (.github/workflows/banco-central.yml) cada mañana, con
las credenciales guardadas como secretos del repositorio (BCCH_USER y BCCH_PASS). La app lee los archivos.

Series:
  datos/imacec-desest.json Imacec desestacionalizado (índice), mensual. Con él la app calcula la variación
                           respecto del mes anterior. Si el código no es el esperado, se busca por su nombre.
  datos/wti.json           Precio del petróleo WTI (dólares por barril), diario desde 2014.
  datos/brent.json         Precio del petróleo Brent (dólares por barril), mensual desde 2014.
                           Las dos de petróleo se buscan por su nombre la primera vez; después se usa el código
                           que quedó guardado en el archivo.
                           El Banco Central tiene el WTI diario y el Brent solo mensual. Publica el WTI con unos
                           días de atraso. Si existe el secreto
                           OILPRICEAPI_KEY (clave gratuita de oilpriceapi.com), se agrega el precio de mercado de los
                           días que el Banco Central aún no publica; cuando los publica, manda el del Banco Central.

UF, dólar, IPC, TPM, Imacec en 12 meses y cobre no pasan por aquí: la app los lee de findic.cl. Al final, la tarea
revisa que findic.cl responda y permita la lectura desde el navegador, y deja el resultado como nota.

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


def leer_serie(codigo, desde='2002-01-01'):
    resp = api(function='GetSeries', timeseries=codigo, firstdate=desde, lastdate=datetime.date.today().isoformat())
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


_catalogo = {}


def catalogo(frecuencia):
    """Todas las series de una frecuencia (DAILY, MONTHLY…), con su código y título. Se pide una sola vez."""
    if frecuencia not in _catalogo:
        resp = api(function='SearchSeries', frequency=frecuencia)
        _catalogo[frecuencia] = [(str(s.get('seriesId') or ''), sin_tildes(str(s.get('spanishTitle') or '')))
                                 for s in resp.get('SeriesInfos') or []]
    return _catalogo[frecuencia]


def buscar(frecuencias, debe, no_debe=r'$^'):
    """El primer código cuyo título tiene todas las palabras de «debe» y ninguna de «no_debe»."""
    for f in frecuencias:
        hallado = [(len(t), c, t) for c, t in catalogo(f) if all(d in t for d in debe) and not re.search(no_debe, t)]
        if hallado:
            hallado.sort()                                   # el título más corto: la serie principal
            return hallado[0][1], f
    raise Rechazo('no se encontró la serie «%s» entre las del Banco Central' % ' '.join(debe))


def codigo_guardado(nombre_archivo):
    try:
        return json.loads((DATOS / nombre_archivo).read_text(encoding='utf-8')).get('serie') or ''
    except (OSError, ValueError):
        return ''


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
    print('%s guardado: %d datos, último %s con %s.' % (nombre_archivo, len(obs), obs[-1][0], obs[-1][1]))


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


# ---------- Petróleo Brent y WTI ----------
# Código de la serie diaria del WTI (confirmado por su nombre). El Banco Central no tiene Brent diario: se usa el mensual.
DIARIOS = {'wti': 'F019.PPB.PRE.41B.D'}


def petroleo(tipo):
    archivo = tipo + '.json'
    guardado = codigo_guardado(archivo)
    # Primero la serie diaria; si no hay, la que quedó guardada. La búsqueda por nombre, solo si nada de eso responde.
    codigos = []
    for c in [guardado if guardado.endswith('.D') else '', DIARIOS.get(tipo, ''), guardado]:
        if c and c not in codigos:
            codigos.append(c)
    nombre, obs, codigo = '', [], ''
    for c in codigos:
        try:
            n, o = leer_serie(c, '2014-01-01')
        except Rechazo:
            continue
        if o and tipo in sin_tildes(n):
            nombre, obs, codigo = n, o, c
            break
    if not obs:
        try:
            codigo, frecuencia = buscar(['DAILY'], [tipo, 'barril'], r'futuro|variaci|indice|spread|diferencial')
        except Rechazo:
            # Para revisar a mano: los títulos diarios que nombran este petróleo
            vistos = [c + ' «' + t + '»' for c, t in catalogo('DAILY') if tipo in t][:6]
            aviso('notice', 'Petróleo %s: no hay serie diaria; series diarias que lo nombran: %s.' % (tipo.upper(), '; '.join(vistos) or 'ninguna'))
            codigo, frecuencia = buscar(['MONTHLY'], ['petroleo', tipo], r'futuro|promedio|variaci|indice|spread|diferencial')
        nombre, obs = leer_serie(codigo, '2014-01-01')
        aviso('notice', 'Petróleo %s: se usa la serie %s (%s, %s).' % (tipo.upper(), codigo, nombre, frecuencia.lower()))
    if not obs:
        raise Rechazo('la serie del petróleo %s llegó vacía' % tipo.upper())
    if codigo != guardado:
        aviso('notice', 'Petróleo %s: serie %s (%s).' % (tipo.upper(), codigo, nombre))
    # Los días que el Banco Central aún no publica, con el precio de mercado (si hay clave de OilPriceAPI).
    # Solo sobre una serie diaria: a una mensual no se le mezclan precios de un día.
    ultimo = obs[-1][0]
    mercado = []
    if codigo.endswith('.D'):
        mercado = [m for m in mercado_guardado(archivo) if m[0] > ultimo]
        hoy = precio_mercado(tipo)
        if hoy and hoy[0] > ultimo:
            mercado = [m for m in mercado if m[0] != hoy[0]] + [hoy]
        mercado.sort()
    guardar(archivo, codigo, nombre or 'Precio del petróleo %s (dólares/barril)' % tipo.upper(), obs + mercado,
            {'mercado': [m[0] for m in mercado]} if mercado else None)


OILPRICE = {'wti': 'WTI_USD', 'brent': 'BRENT_CRUDE_USD'}


def mercado_guardado(nombre_archivo):
    """Los precios de mercado guardados antes: los días marcados en «mercado»."""
    try:
        d = json.loads((DATOS / nombre_archivo).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    dias = set(d.get('mercado') or [])
    return [o for o in d.get('obs') or [] if o[0] in dias]


def precio_mercado(tipo):
    """Último precio de OilPriceAPI, como [fecha en Chile, valor]. Sin clave, o si falla, None."""
    clave_op = os.environ.get('OILPRICEAPI_KEY', '').strip()
    if not clave_op:
        return None
    pedido = urllib.request.Request('https://api.oilpriceapi.com/v1/prices/latest?by_code=' + OILPRICE[tipo], headers={
        'Authorization': 'Token ' + clave_op, 'Accept': 'application/json', 'User-Agent': 'indicadores (GitHub Actions)'})
    try:
        with urllib.request.urlopen(pedido, timeout=60) as r:
            d = (json.loads(r.read().decode('utf-8')) or {}).get('data') or {}
        precio = float(d.get('price'))
        marca = str(d.get('as_of') or d.get('source_timestamp') or d.get('created_at') or '')
        momento = datetime.datetime.fromisoformat(marca.replace('Z', '+00:00'))
    except urllib.error.HTTPError as e:
        aviso('warning', 'OilPriceAPI (%s): error HTTP %s%s.' % (tipo.upper(), e.code, ', revisa la clave OILPRICEAPI_KEY' if e.code in (401, 403) else ''))
        return None
    except Exception as e:  # noqa: BLE001
        aviso('warning', 'OilPriceAPI (%s): no se pudo leer (%s).' % (tipo.upper(), type(e).__name__))
        return None
    if not (precio > 0):
        return None
    try:
        from zoneinfo import ZoneInfo
        momento = momento.astimezone(ZoneInfo('America/Santiago'))
    except Exception:  # noqa: BLE001
        momento = momento - datetime.timedelta(hours=3)
    print('OilPriceAPI %s: %s al %s.' % (tipo.upper(), precio, momento.isoformat()))
    return [momento.date().isoformat(), round(precio, 2)]


# ---------- IPC: variación mensual y en 12 meses ----------
# Las publica el INE el día 8 de cada mes y el Banco Central las tiene el mismo día. La primera vez se buscan por
# su nombre; después se usa el código que quedó guardado, mientras siga vigente.
IPC = {'mensual': 'ipc-mensual.json', '12m': 'ipc-12m.json'}
DOCE = r'12 meses|doce meses|anual'
NO_IPC = (r'sin |subyacente|sae|volatil|bien|servicio|transable|alimento|energia|combustible|vivienda|transporte|'
          r'division|producto|grupo|incidencia|ponderac|expectativ|encuesta|region|sector|acumulad|ipcx|ipp|ipm|ipe\b')


def candidatas_ipc(cual):
    out = []
    for c, t in catalogo('MONTHLY'):
        if not (re.search(r'\bipc\b', t) or 'precios al consumidor' in t) or 'variaci' not in t or re.search(NO_IPC, t):
            continue
        doce = bool(re.search(DOCE, t))
        if (cual == '12m') != doce or (cual == 'mensual' and 'mensual' not in t):
            continue
        out.append((0 if c.startswith('F074') else 1, len(t), c, t))
    out.sort()
    return [(c, t) for _, _, c, t in out]


def ipc(cual):
    archivo = IPC[cual]
    limite = (datetime.date.today() - datetime.timedelta(days=100)).isoformat()   # con datos de los últimos meses

    def vigente(o):
        return bool(o) and o[-1][0] >= limite

    guardado = codigo_guardado(archivo)
    nombre, obs, codigo = '', [], ''
    if guardado:
        try:
            nombre, obs = leer_serie(guardado, '2000-01-01')
            codigo = guardado
        except Rechazo:
            pass
    if not vigente(obs):
        cands = candidatas_ipc(cual)
        aviso('notice', 'IPC %s: candidatas %s.' % (cual, '; '.join(c + ' «' + t + '»' for c, t in cands[:8]) or 'ninguna'))
        nombre, obs, codigo = '', [], ''
        for c, t in cands[:6]:
            try:
                n, o = leer_serie(c, '2000-01-01')
            except Rechazo:
                continue
            if vigente(o) and len(o) >= 60:
                nombre, obs, codigo = n, o, c
                break
        if not obs:
            raise Rechazo('no se encontró una serie vigente del IPC (%s)' % cual)
        aviso('notice', 'IPC %s: se usa la serie %s (%s); últimos datos %s.' % (cual, codigo, nombre, obs[-3:]))
    guardar(archivo, codigo, nombre or 'IPC, variación ' + ('en 12 meses' if cual == '12m' else 'mensual'), obs)


# ---------- Revisión de findic.cl (la fuente de la app para el resto de los indicadores) ----------
def revisar_findic():
    pedido = urllib.request.Request('https://findic.cl/api/uf', headers={
        'User-Agent': 'indicadores (GitHub Actions)', 'Origin': 'https://pablocarvallo.github.io'})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as r:
            permiso = r.headers.get('Access-Control-Allow-Origin') or ''
            datos = json.loads(r.read().decode('utf-8', 'replace'))
        ultimo = (datos.get('serie') or [{}])[0]
        if permiso in ('*', 'https://pablocarvallo.github.io'):
            aviso('notice', 'findic.cl responde y permite leerlo desde la app (UF %s: %s).' % (ultimo.get('fecha'), ultimo.get('valor')))
        else:
            aviso('warning', 'findic.cl responde, pero no permite leerlo desde el navegador (Access-Control-Allow-Origin: %s).' % (permiso or 'ausente'))
    except Exception as e:  # noqa: BLE001
        aviso('warning', 'findic.cl no responde (%s).' % type(e).__name__)


tareas = [('IPC mensual', lambda: ipc('mensual')), ('IPC en 12 meses', lambda: ipc('12m')),
          ('Imacec desestacionalizado', imacec_desest), ('Petróleo Brent', lambda: petroleo('brent')), ('Petróleo WTI', lambda: petroleo('wti'))]
fallas = []
for nombre_tarea, tarea in tareas:
    try:
        tarea()
    except Rechazo as e:
        fallas.append(nombre_tarea)
        aviso('warning', '%s: %s.' % (nombre_tarea, e))
revisar_findic()
if len(fallas) == len(tareas):
    falla('No se pudo traer ninguna serie del Banco Central.')
