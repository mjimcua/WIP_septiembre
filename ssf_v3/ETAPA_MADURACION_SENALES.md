# ETAPA 5.9 · LA MADURACIÓN DE LAS SEÑALES — formalización (implementada en `analysis_signal_maturation.py`; la fase B, medida desde las fotos, queda para cuando haya ≥ 6 meses de `signal_snapshot`)

## 1 · El problema

El forecast es una foto tomada hoy. En esa foto, un contrato que vence en febrero de 2027
lleva sus señales timevarying **tal como están hoy**: `softcancel = 0`, `dormant = 0`. Pero
esas señales se activan con el tiempo: la cancelación se anuncia cuando se acerca el
vencimiento, el uso se abandona a mitad de ciclo. Cuando llegue febrero, una parte de
los contratos que hoy están en la serie neutra estará en la serie `softcancel = 1`, que
renueva al 40 % en vez de al 78 %.

Consecuencia: para los meses lejanos, el forecast de hoy **sobreestima**, porque asigna a
demasiados contratos la tasa de los neutros. Y el sesgo negativo que vimos en el hold-out
a horizontes largos (−2 a −3 puntos) tiene aquí una explicación candidata: en el
backtest, la serie de un mes pasado ya lleva sus señales *finales* (las del vencimiento),
así que el backtest no ve este efecto; el forecast real sí lo sufre.

Dicho con las variables: para un mes futuro m a distancia h,

    forecast(m) = Σ_series  pipeline(m, s) × tasa(s) × uplift(s)

y lo que va a pasar es que una fracción de `pipeline(m, neutra)` se moverá a
`pipeline(m, softcancel)` y a `pipeline(m, dormant)` antes de m. Cuánta, depende de h:
a 1 mes casi todo está ya dicho; a 6 meses, casi nada.

## 2 · Lo que hace falta saber: la curva de maduración

Para cada celda (región × producto, como mínimo) y cada señal f, la **curva de
maduración** es la proporción de unidades (o de dólares) con la señal activa según la
distancia al vencimiento:

    share_f(celda, h) = unidades con f = 1 a h meses del vencimiento / unidades totales

con `share_f(celda, 0)` la proporción **final** (la del mes ya vencido). Y lo que se
necesita para ajustar es la **maduración pendiente**:

    pendiente_f(celda, h) = share_f(celda, 0) − share_f(celda, h)

es decir, cuánta señal falta por aparecer entre hoy y el vencimiento.

## 3 · Qué datos tenemos y qué datos no

**Tenemos** la proporción final: en los meses cerrados, las señales del raw son las del
vencimiento (o las del extracto, que para un mes cerrado es lo mismo si el extracto se
hace después). Es `share_f(celda, 0)` por mes, con su historia: se puede ver su nivel, su
mismo mes del año anterior y su tendencia.

**Tenemos** la proporción actual para cada mes futuro: `share_f(celda, h)` para el h de
hoy, una sola observación por mes futuro.

**No tenemos** cómo estaba la proporción de un mes ya vencido cuando faltaban h meses:
eso solo lo tiene un extracto antiguo. Sin ese dato no hay curva de maduración medida,
solo el punto final y el punto de hoy.

De ahí las dos fases de la etapa: una que funciona **desde el primer mes** con lo que hay,
y otra que se va construyendo sola guardando cada mes la foto.

## 4 · La etapa, formalizada

### 4.1 · Foto mensual de las señales (desde el primer run)

Cada run persiste `signal_snapshot`: por celda × mes objetivo × señal, la distancia h
(mes objetivo − mes en curso), unidades y dólares totales, unidades y dólares con la
señal activa, y la fecha de la foto. Es una tabla que crece cada mes y que dentro de 6-12
meses contiene, para cada mes ya vencido, cómo estaban sus señales a 1, 2, … h meses:
**la curva de maduración medida**, por celda y por señal.

### 4.2 · La curva (fase A: aproximada; fase B: medida)

**Fase A (hoy, sin histórico de fotos).** Se aproxima la maduración pendiente con lo que
sí tenemos:

    share_final_esperado_f(celda, m) = proporción final de los últimos 12 meses cerrados
                                        de la celda (o la del mismo mes del año anterior,
                                        si la señal es estacional: lo dice el benchmark
                                        de flags, `bench_flags`)
    pendiente_f(celda, m, h) = max(0, share_final_esperado − share_actual_f(celda, m))

Supone que todo lo que falta aparecerá antes de m. A h grande es lo correcto (casi nada
ha aparecido aún); a h = 1 sobreestima la maduración (lo que iba a aparecer ya ha
aparecido), y por eso se limita: a h ≤ 1 la pendiente se toma como 0.

**Fase B (cuando `signal_snapshot` tenga ≥ 6 meses vencidos con fotos a la misma h).**
La curva se mide: `share_f(celda, h)` promedio de los meses vencidos, y la maduración
pendiente es la diferencia medida entre h y 0. La fase A se sustituye sola cuando hay
datos; el código lo decide por el número de fotos disponibles.

### 4.3 · El ajuste al forecast

Por celda × mes futuro × señal, las unidades que se moverán de la serie neutra a la
serie con señal:

    unidades_migran_f = pendiente_f(celda, m, h) × unidades_neutras(celda, m)

y el efecto en dólares:

    ajuste_f(celda, m) = − unidades_migran_f × AUV_neutro × uplift_neutro
                          × (tasa_neutra(celda) − tasa_con_señal_f(celda))

donde las tasas son las que ya tiene el framework (la serie neutra y la serie con señal
de la misma celda, o su pool). El ajuste es negativo para las señales negativas y
positivo para `autorenew`, que también madura (se activa con el tiempo).

Se persiste `signal_adjustment` (celda × mes × señal: share actual, share final esperado,
pendiente, unidades que migran, ajuste $) y se lleva al resumen:

    forecast_ajustado(m) = forecast(m) + Σ_f ajuste_f(m)

`business_summary` y `horizon_report_total` llevan las dos columnas, `forecast_usd` (la
foto) y `forecast_ajustado_usd` (la foto más la maduración esperada), y la diferencia por
región en `forecast_by_region` (`ajuste_senales_usd`). **La banda no cambia**: el ajuste es
un desplazamiento del centro, no una incertidumbre nueva; su propia incertidumbre se
mide en 4.5.

### 4.4 · Las alertas

Tres alertas por celda × señal, en unidades del ruido de la propia proporción (una
proporción también es binomial: se = √(share(1−share)/n)):

1. **Nivel anómalo hoy.** La proporción actual a distancia h es mayor que la esperada a
   esa distancia (fase B: la curva; fase A: la final esperada × un factor de h que se
   declara, p. ej. 0 a h ≥ 6, 0,5 a h = 3, 1 a h = 1) en más de 2 errores. "Febrero, a 5
   meses, ya tiene un 5 % de softcancel; a 5 meses lo normal es un 1 %."
2. **Tendencia de la proporción final.** La pendiente de `share_f(celda, 0)` en los
   últimos 12 meses cerrados, en pp/mes, con su error: "la cancelación anunciada crece
   0,4 pp al mes en DACH·KIS". Se mide una vez y no necesita fotos.
3. **Crecimiento mes a mes de la foto.** Con dos o más fotos del mismo mes objetivo
   (a partir del segundo run): cuánto ha crecido la proporción entre fotos comparado con
   lo que crece normalmente en un mes a esa distancia. Es la alerta más fina y la única
   que necesita `signal_snapshot`.

Tabla `signal_alerts`: celda, señal, mes objetivo, h, share actual, share esperado, z,
tipo de alerta, dinero en juego (unidades de la celda × AUV × hueco de tasa). Las alertas
entran en `top_movers` como tipo `senal_madurando`.

### 4.5 · Validación de la etapa (sin trampas)

- **Retrospectiva desde el primer mes**: para los meses cerrados, comparar la proporción
  final con la proporción "que habríamos supuesto" con la fase A (la final media de los 12
  meses anteriores): el error de la aproximación, por celda. Dice cuánto se puede fiar uno
  del ajuste antes de tener fotos.
- **Cuando haya fotos**: la curva medida contra la aproximación; y el forecast ajustado
  contra el no ajustado en el examen (el hold-out de la fase 3 no lo mide, porque el
  backtest ya usa señales finales: hace falta reconstruir el forecast con las señales
  como estaban en la foto de h meses antes, que es exactamente lo que `signal_snapshot`
  permite).

## 5 · Dónde encaja en el flujo

Después del ensamblaje (fase 5) y antes de los resúmenes: 5.9 foto de señales, 5.10
curva y ajuste, 5.11 alertas; los resúmenes leen `forecast_ajustado_usd`. Es RUN (se
ejecuta cada mes, porque la foto es mensual); la curva medida es ANALYSIS.

Tablas nuevas: `signal_snapshot`, `signal_maturation_curve`, `signal_adjustment`,
`signal_alerts`. Parámetros: `signal_maturation_mode` (auto / aproximada / medida),
`signal_maturation_min_snapshots` (6), `signal_maturation_final_window_months` (12), el
perfil de h de la fase A, y el umbral de alerta (2 errores).

## 6 · Ejemplo con números

DACH · KIS MD · 1 año, febrero de 2027, a 5 meses. Hoy: 4.000 unidades, 40 con
`softcancel` (1 %). Proporción final de los últimos 12 meses cerrados: 6 %. Pendiente:
5 % × 3.960 neutras ≈ 198 unidades migrarán. Tasa neutra 78 %, tasa con softcancel 40 %,
AUV × uplift $45. Ajuste: −198 × 45 × 0,38 ≈ **−$3.386** sobre un forecast del mes de
$139.000: un −2,4 %. Alerta 1: si hoy el 1 % ya fuera un 3 % (a 5 meses lo normal es
≈ 1 %), z = (0,03 − 0,01) / √(0,01 × 0,99 / 4.000) ≈ 12: alerta, y el dinero en juego
sería el hueco de ese 2 % adicional: ≈ $1.350.

## 7 · Lo que hay que confirmar antes de implementar

1. Que en un mes **cerrado** las señales del raw son las del vencimiento (o del cierre),
   no las de hoy. Si el raw reescribe las señales de meses pasados con el estado actual
   del cliente, la proporción final está contaminada y hay que tomarla del extracto de
   cierre.
2. Qué señales maduran y cuáles no: `softcancel` y `dormant` sí; `no_instalado` es un
   estado desde la compra (madura poco); `autorenew` se activa (madura al alza).
3. Si se quiere el forecast ajustado como cifra principal o como cifra acompañante. Mi
   propuesta: acompañante el primer trimestre, principal cuando la retrospectiva (4.5)
   muestre que la aproximación acierta.
