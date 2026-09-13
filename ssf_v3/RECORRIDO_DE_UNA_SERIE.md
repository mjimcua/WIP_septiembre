# EL RECORRIDO DE UNA SERIE PEQUEÑA — explicado desde cero

Este documento sigue a una serie concreta a través de todo el sistema, sin dar por
sabido nada. Es para alguien que no conoce la librería y quiere entender qué hace con
un caso real: una serie con **15 clientes al mes de media**, primero sin ninguna señal
de churn y después con una.

## 0 · Tres palabras antes de empezar

- **Serie (forecast series)**: un grupo de clientes definido por unas dimensiones fijas
  (región, producto, tipo de compra, plazo, banda de dispositivos, señales de churn,
  si es cliente nuevo) seguido mes a mes. Cada mes vencen n contratos de ese grupo y
  renuevan k: la tasa del mes es k/n.
- **Pool**: un grupo mayor formado por varias series parecidas. Cuando una serie es
  pequeña, toma prestada la tasa de un pool.
- **Peldaño**: cada uno de los pools candidatos de una serie, ordenados del más parecido
  (peldaño 0: ella misma) al más grueso. La serie "sube la escalera" hasta el primer
  peldaño con clientes suficientes.

Los peldaños tienen siempre el mismo número para que signifiquen lo mismo en todas las
series:

| Peldaño | Qué es | Quién lo tiene |
|---|---|---|
| 0 | la serie sola | todas |
| 1 | las series con las mismas dimensiones y **el mismo signo de señal** (dormido, cancelación anunciada y no instalado se juntan como "negativo") | solo las series con señal; una serie sin señal no tiene nada que juntar aquí y salta al 2 |
| 2 | además, sin distinguir si el cliente es nuevo (`net_new` anulado) | todas |
| 3 | la celda entera: todas las series con las mismas dimensiones obligatorias | todas; **último peldaño para las series con señal** |
| 4, 5, … | la celda con una dimensión obligatoria menos cada vez (primero las que menos separan: bandas de dispositivos, después producto fino…) | solo las series sin señal |

Por eso en el ejemplo de una serie sin señal aparecen los peldaños 0, 2, 3, 4… y no el 1.

## 1 · Por qué el error de una serie pequeña se mide con Wilson

Con 15 clientes, si renuevan 12 la tasa observada es 80 %. Pero con 15 clientes esa
cifra puede moverse mucho por puro azar: otro mes igual podrían renovar 9 o 14. El
intervalo que dice "entre cuánto y cuánto puede estar la tasa real" se calcula con la
fórmula de Wilson y no con la clásica (tasa ± z·error), por dos razones que importan
justo en muestras pequeñas: la clásica puede dar intervalos que pasan del 100 % o
bajan de 0 % (con 14 de 15 daría "93 % ± 11" → hasta 104 %), y es demasiado estrecha
cuando la tasa está cerca de los extremos. Wilson corrige las dos cosas: para 12 de 15
da aproximadamente [58 %, 92 %]; para 14 de 15, [73 %, 98 %]. Es el intervalo estándar
recomendado para proporciones con n pequeño. En las tablas es `error_binomial_pp` (la
mitad del ancho de ese intervalo, en puntos porcentuales).

## 2 · Caso A: la serie sin señal

Serie: DACH · Front Line · KIS MD · Retention · 2 años · 1 dispositivo · sin señales ·
clientes no nuevos. 15 vencimientos al mes de media.

**Paso 1 · Qué es y qué tiene (fase 0).** Tiene meses con historia (sabemos qué pasó) y
meses futuros con contratos que vencen (hay algo que predecir): se marca como
`trainable`. Si solo tuviera historia se marcaría `no_impact` (nada que predecir); si
solo tuviera futuro, `heuristic` (nada de qué aprender).

**Paso 2 · Su serie mensual (fase 1.1).** 44 meses de historia. En 6 de ellos no venció
nadie: esos meses se rellenan con una fila vacía cuya tasa es "desconocida", no 0 %
(un mes sin vencimientos no dice nada de la tasa). Se calcula su tasa de toda la
historia (por ejemplo 76 %), su error de Wilson (±20 puntos con n = 15) y su signo:
`neutral`, porque ningún cliente lleva señal.

**Paso 3 · Sus peldaños (fase 1.3).** Como es neutra: 0 (ella), 2 (con y sin clientes
nuevos), 3 (su celda), 4 (celda sin distinguir banda de dispositivos), 5…

**Paso 4 · La subida.** Peldaño 0: 15 clientes, no llega a 271 → no puede ir sola.
Peldaño 2: ella más su hermana de clientes nuevos suman 42 al mes → llega a 30, que es
el mínimo para que un pool "diga algo". Se para ahí. Su pool es ese: su `id_estimacion`.

**Paso 5 · Cuánto creerse a sí misma.** El sistema mide si las series de ese pool
renuevan parecido entre sí. Si sí, se fía más del pool; si no, más de cada una. Sale un
peso: por ejemplo 20 % de su propia tasa y 80 % de la del pool. Su tasa estimada es esa
mezcla. Quedan dos errores: el de la *estimación* (≈ ±4 puntos, porque el pool ayuda) y el
de la *predicción* (≈ ±13 puntos: el mes que viene vendrán 15 clientes y 15 clientes
oscilan). Nivel de riesgo **B · prestado**: predice con un pariente casi idéntico.

**Paso 6 · Cómo se mueve (fase 2).** Lo que se mide no es la serie sino su pool: si su
tasa tiene estación (renueva más en unos meses), tendencia, o si cambió de nivel en
algún momento. Con 42 clientes, casi seguro sale "no se mueve más de lo que el azar
explica": la mejor predicción es la media reciente.

**Paso 7 · Qué método predice (fase 3).** Se prueban varios métodos sobre el pool,
prediciendo los últimos 24 meses como si no se conocieran, y gana el que menos se
equivocó. Con 42 clientes ganará el más simple (la media de los últimos 3 meses).

**Paso 8 · A qué precio renueva (fase 4).** Sus clientes, según descuento y antigüedad,
caen en celdas de revalorización. Con 15 clientes esas celdas son pequeñas y toman el
factor de precio de su celda padre.

**Paso 9 · El forecast de cada mes futuro (fase 5).** Tasa = lo que predice el método
del pool para ese mes, más el 20 % de su diferencia propia respecto al pool. Dinero
esperado = lo que vence × tasa × factor de precio. Banda = la que el pool demostró
tener en el backtest a ese horizonte, ampliada por su propio azar de 15 clientes (que
aquí manda: ±20 puntos).

**Paso 10 · Cómo entra en el total.** Su dinero se suma al de las demás series. Su
banda se suma en línea con las filas de su mismo pool en el mismo mes (se equivocan
juntas) y en cuadratura con todo lo demás (errores independientes se compensan en
parte). Una serie de 15 clientes con ±20 puntos aporta muy poca banda al total.

## 3 · Caso B: la misma serie con una señal (`softcancel = 1`)

Ahora los 15 clientes tienen cancelación anunciada. Todo es igual hasta el signo.

**Paso 2 · Signo.** `softcancel` es una señal negativa activa → signo `neg`. Este cliente
renueva de forma muy distinta (en torno al 40 % frente al 78 % de los que no han
avisado). La regla del sistema: **una serie con señal nunca toma prestada la tasa de
series sin señal ni de series con la señal contraria.**

**Paso 3 · Sus peldaños.** 0 (ella), 1 (las series de su celda con cualquier señal
negativa: dormidos, cancelación anunciada, no instalados), 2 (además sin distinguir
cliente nuevo, mismo signo), 3 (su celda × señal negativa). Y aquí se para. Solo si se
activa el parámetro `signed_ladder_max_loss` sigue subiendo, manteniendo la señal, por
las dimensiones que casi no separan (bandas de dispositivos, producto fino).

**Paso 4 · La subida.** Igual que antes: el primer peldaño ≥ 1 con 30 clientes. Dos salidas:

- *Encuentra pool*: el peldaño 3 (su celda con señal negativa) suma 38 → se para ahí.
  Nivel **C · lejano** (peldaño 3). Credibilidad, dinámica y método se calculan sobre ese
  pool con señal; el forecast será del orden del 40 %, no del 78 %: eso es lo que la
  señal aporta, y es el motivo de no mezclar.
- *No encuentra pool*: ninguno de sus peldaños llega a 30. Nivel **S · señal bajo suelo**.
  Usa la mejor tasa que encontró (la de su celda con señal, aunque sea de 22 clientes),
  sin mezcla, con banda ancha (±25 puntos o más), y no participa en el backtest. Es
  ruidosa, pero honesta: un 40 % ± 25 es más útil para el negocio que un 78 % ± 4 que no
  es suyo. En la cartera real hay 4.287 series así con 8,8 millones; por eso existe el
  parámetro del paso 3.

**Pasos 5 a 10.** Como en el caso A, con dos diferencias: el pool es el de las señales
negativas, y si la serie es S, la banda es la binomial de sus propios 15 clientes.

**Y si tuviera dos señales opuestas** (`softcancel = 1` y `autorenew = 1`): signo `mixed`.
Solo peldaño 0, nivel **M**, se queda sola y se cuenta. No es un problema del forecast:
son dos modelos marcando al mismo cliente en sentidos contrarios.

## 4 · Dónde se ve todo esto

- `sheet("<id de la serie>", configuration)` imprime este recorrido con los números
  reales de la serie y dibuja su figura (tasa mensual, pipeline, estación, hold-out).
- `series_card`: una fila por serie con nivel, pool, peso propio, tasa y errores.
- `parent_ladder`: sus peldaños, con los clientes de cada uno y cuál se eligió.
- `forecast_detail`: cada mes futuro con la tasa del pool, la desviación propia
  aplicada, la tasa final y el dinero.
- `risk_levels`: cuánto dinero de la cartera está en cada nivel (A, B, C, S, …) y con qué
  error medio: la foto de cuánto se puede prometer y dónde no.
