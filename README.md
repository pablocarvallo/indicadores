# Indicadores

Tablero de indicadores de Chile para el iPhone: UF, dólar observado, IPC, tasa de política monetaria (TPM), Imacec y tasa promedio de créditos de consumo, con sus gráficos históricos.

## Qué muestra

- **Indicador destacado arriba**: por defecto la UF de hoy. Se puede elegir cualquier otro en Ajustes o con «Destacar arriba» en el detalle de cada indicador. Los demás van en tarjetas debajo.
- **Una tarjeta por indicador**, con el último dato y la tendencia de 12 meses:
  - **Dólar observado**: valor diario y cambio respecto del día anterior.
  - **IPC**: variación mensual y en 12 meses.
  - **TPM**: tasa vigente, desde cuándo rige y la tasa anterior.
  - **Imacec**: variación en 12 meses y variación mensual (respecto del mes anterior, con la serie desestacionalizada).
  - **Créditos de consumo**: tasa promedio del sistema financiero, en pesos (% anual), y su cambio respecto del mes anterior.
- **Detalle**: al tocar una tarjeta se abre el gráfico histórico de 1, 5 o 10 años. Al pasar el dedo sobre el gráfico se ve el valor de cada fecha. Además muestra el mínimo, el máximo, el cambio del periodo y una tabla con los últimos valores. El IPC y el Imacec se pueden ver en 12 meses o mensual.
- **Sin conexión**: los datos quedan guardados en el iPhone.

## Fuentes

- **UF, dólar, TPM e Imacec**: [mindicador.cl](https://mindicador.cl), con datos del Banco Central. Se leen directo desde el iPhone.
- **IPC**: se calcula con la UF. Entre el día 10 de un mes y el 9 del siguiente, la UF se reajusta según el IPC del mes anterior, así que el IPC de un mes es la UF del día 9 de dos meses después dividida por la del día 9 del mes siguiente. El dato mensual coincide con el del INE. El de 12 meses compone las variaciones mensuales y puede diferir en una décima del oficial. Se calcula así porque mindicador.cl dejó de publicar el IPC en diciembre de 2025.
- **Créditos de consumo e Imacec mensual**: Banco Central de Chile. La tasa es la serie `F022.CON.TIP.Z.NO.Z.M` («Tasa promedio de créditos de consumo, total (pesos)», mensual desde 2002). La variación mensual del Imacec se calcula con el índice desestacionalizado: la tarea usa `F032.IMC.IND.Z.Z.EP18.Z.Z.1.M` y, si no corresponde, busca la serie por su nombre. La API del Banco Central pide usuario y clave, así que no se consulta desde el iPhone. Una tarea de GitHub (`.github/workflows/banco-central.yml`) corre cada mañana con `herramientas/banco-central.py` y deja las series en `datos/consumo.json` y `datos/imacec-desest.json`. Los archivos solo cambian cuando hay un mes nuevo o una revisión. La app los lee directo del repositorio.

## Conectar la API del Banco Central (una vez)

1. Crea una cuenta gratuita y activa las credenciales en [si3.bcentral.cl/Siete/es/Siete/API](https://si3.bcentral.cl/Siete/es/Siete/API).
2. En este repositorio, abre **Settings → Secrets and variables → Actions** y crea dos secretos:
   - `BCCH_USER`: el correo de la cuenta.
   - `BCCH_PASS`: la clave de la API.
3. En **Actions**, abre «Datos del Banco Central» y toca **Run workflow**. Desde ahí corre sola cada mañana.

Las credenciales quedan solo en los secretos de GitHub. No están en la app ni en el repositorio.

## Instalar en el iPhone

1. La app se publica con GitHub Pages en `https://pablocarvallo.github.io/indicadores/`.
2. Abre esa dirección en **Safari** en el iPhone.
3. Toca **Compartir → Agregar a inicio**.
