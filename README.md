# Indicadores

Tablero de indicadores de Chile para el iPhone: UF, dólar observado, IPC, tasa de política monetaria (TPM), Imacec, precio del cobre y precio del petróleo, con sus gráficos históricos.

## Qué muestra

- **Indicador destacado arriba**: por defecto la UF de hoy. Se puede elegir cualquier otro en Ajustes o con «Destacar arriba» en el detalle de cada indicador. Los demás van en tarjetas debajo.
- **Una tarjeta por indicador**, con el último dato y la tendencia de 12 meses:
  - **UF**: valor de hoy, variación en 12 meses y el último valor ya publicado.
  - **Dólar observado**: valor del día y cambio respecto del día anterior.
  - **IPC**: variación mensual y en 12 meses.
  - **TPM**: tasa vigente, desde cuándo rige y la tasa anterior.
  - **Imacec**: variación en 12 meses y variación mensual (respecto del mes anterior, con la serie desestacionalizada).
  - **Cobre**: precio del día en dólares por libra y cambio respecto del día anterior.
  - **Petróleo**: WTI diario en dólares por barril, con el Brent mensual como dato secundario (en el detalle se puede ver uno u otro).
- **Detalle**: al tocar una tarjeta se abre el gráfico histórico de 1, 5 o 10 años. Al pasar el dedo sobre el gráfico se ve el valor de cada fecha. Además muestra el mínimo, el máximo, el cambio del periodo y una tabla con los últimos valores. El IPC y el Imacec se pueden ver en 12 meses o mensual.
- **Sin conexión**: los datos quedan guardados en el iPhone.

## Fuentes

- **UF, dólar, TPM, Imacec y cobre**: [findic.cl](https://findic.cl), con datos del Banco Central. Se leen directo desde el iPhone. Si findic.cl no responde, la app usa [mindicador.cl](https://mindicador.cl), que entrega lo mismo con el mismo formato.
- **IPC**: se calcula con la UF. Entre el día 10 de un mes y el 9 del siguiente, la UF se reajusta según el IPC del mes anterior, así que el IPC de un mes es la UF del día 9 de dos meses después dividida por la del día 9 del mes siguiente. El dato mensual coincide con el del INE. El de 12 meses compone las variaciones mensuales y puede diferir en una décima del oficial.
- **Imacec mensual y petróleo**: Banco Central de Chile. La API del Banco Central pide usuario y clave, así que no se consulta desde el iPhone. Una tarea de GitHub (`.github/workflows/banco-central.yml`) corre tres veces al día con `herramientas/banco-central.py` y deja las series en `datos/`:
  - `datos/imacec-desest.json`: Imacec desestacionalizado (`F032.IMC.IND.Z.Z.EP18.Z.Z.1.M`), para la variación mensual.
  - `datos/wti.json`: precio diario del petróleo WTI desde 2014 (`F019.PPB.PRE.41B.D`).
  - `datos/brent.json`: precio del petróleo Brent desde 2014 (`F019.PPB.PRE.41AB.M`). El Banco Central no tiene Brent diario, solo el promedio mensual.
- **Petróleo del día**: el Banco Central publica el WTI con algunos días de atraso. Con el secreto opcional `OILPRICEAPI_KEY` (clave gratuita de [oilpriceapi.com](https://www.oilpriceapi.com), 50 consultas al día), la tarea agrega al WTI el precio de mercado de los días que el Banco Central aún no publica; cuando los publica, manda el del Banco Central. La tarea usa 3 consultas al día.
- Al final de cada corrida, la tarea revisa que findic.cl responda y permita la lectura desde el navegador, y lo deja como nota en el resumen.

## Conectar las fuentes (una vez)

1. **Banco Central**: crea una cuenta gratuita y activa las credenciales en [si3.bcentral.cl/Siete/es/Siete/API](https://si3.bcentral.cl/Siete/es/Siete/API). En este repositorio, abre **Settings → Secrets and variables → Actions** y crea los secretos `BCCH_USER` (el correo de la cuenta) y `BCCH_PASS` (la clave).
2. **Petróleo del día (opcional)**: crea una cuenta gratuita en [oilpriceapi.com](https://www.oilpriceapi.com) y guarda su clave como secreto `OILPRICEAPI_KEY`.
3. En **Actions**, abre «Datos del Banco Central» y toca **Run workflow**. Desde ahí corre sola tres veces al día.

Las credenciales quedan solo en los secretos de GitHub. No están en la app ni en el repositorio.

## Instalar en el iPhone

1. La app se publica con GitHub Pages en `https://pablocarvallo.github.io/indicadores/`.
2. Abre esa dirección en **Safari** en el iPhone.
3. Toca **Compartir → Agregar a inicio**.
