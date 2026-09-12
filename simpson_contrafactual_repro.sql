/* ============================================================================
   CONTRAFACTUAL SIMPSON — reproducción exacta en T-SQL del experimento de
   f1_diagnose_round1 (los $738.611).
   CELDA  = las 10 dimensiones obligatorias.
   SERIE  = celda + softcancel (el grano de la tasa en tu config actual).
   Walk-forward sobre los últimos 6 meses con verdad; historia = TODO lo < t.
   AJUSTA: [tabla_raw]. Mandos al final del script.
   ============================================================================ */

WITH truth AS (            -- 1 · meses con verdad, al grano de SERIE
    SELECT
        celda = CONCAT_WS('|', tr_regional_level_1, tr_regional_level_2,
                 tr_regional_level_3, tr_product_level_1, tr_product_level_2,
                 tr_origin_type_SKU_based, tr_term_level_1, tr_term_level_2,
                 tr_band_level_1, tr_band_level_2),
        fs_id = CONCAT_WS('|', tr_regional_level_1, tr_regional_level_2,
                 tr_regional_level_3, tr_product_level_1, tr_product_level_2,
                 tr_origin_type_SKU_based, tr_term_level_1, tr_term_level_2,
                 tr_band_level_1, tr_band_level_2, softcancel),
        period,
        units   = SUM(total_tr_units),
        renewed = SUM(total_renewed_units),
        usd     = SUM(total_tr_usd)
    FROM [Kamelot].[dbo].[tabla_raw]
    WHERE dataset_role IN ('train','test') AND is_current_month = 0
    GROUP BY tr_regional_level_1, tr_regional_level_2, tr_regional_level_3,
             tr_product_level_1, tr_product_level_2, tr_origin_type_SKU_based,
             tr_term_level_1, tr_term_level_2, tr_band_level_1, tr_band_level_2,
             softcancel, period
),
fs_cum AS (                -- 2 · historia acumulada de cada SERIE hasta t−1
    SELECT *,
        ser_ren_prev  = SUM(renewed) OVER (PARTITION BY fs_id ORDER BY period
                          ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
        ser_units_prev = SUM(units)  OVER (PARTITION BY fs_id ORDER BY period
                          ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
    FROM truth
),
cell_month AS (            -- 3 · la CELDA por mes (sumando sus series)
    SELECT celda, period,
        c_units = SUM(units), c_renewed = SUM(renewed), c_usd = SUM(usd)
    FROM truth GROUP BY celda, period
),
cell_cum AS (              -- 4 · historia acumulada de la celda + nº de meses previos
    SELECT *,
        cel_ren_prev   = SUM(c_renewed) OVER (PARTITION BY celda ORDER BY period
                           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
        cel_units_prev = SUM(c_units)   OVER (PARTITION BY celda ORDER BY period
                           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
        meses_previos  = ROW_NUMBER()   OVER (PARTITION BY celda ORDER BY period) - 1,
        rn_ultimo      = ROW_NUMBER()   OVER (PARTITION BY celda ORDER BY period DESC)
    FROM cell_month
),
seg AS (                   -- 5 · método SEGMENTADO: tasa de cada serie ≤t−1,
                           --     ponderada por los vencimientos REALES de t
    SELECT f.celda, f.period,
        seg_num = SUM( f.units *
                  COALESCE(1.0 * f.ser_ren_prev / NULLIF(f.ser_units_prev, 0),
                           1.0 * c.cel_ren_prev / NULLIF(c.cel_units_prev, 0)) ),
        seg_den = SUM(f.units)
    FROM fs_cum f
    JOIN cell_cum c ON c.celda = f.celda AND c.period = f.period
    GROUP BY f.celda, f.period
),
examen AS (                -- 6 · los tres números por celda × mes-examen
    SELECT c.celda, c.period,
        tasa_real  = 1.0 * c.c_renewed    / NULLIF(c.c_units, 0),
        tasa_plano = 1.0 * c.cel_ren_prev / NULLIF(c.cel_units_prev, 0),
        tasa_seg   = s.seg_num / NULLIF(s.seg_den, 0),
        c_usd = c.c_usd
    FROM cell_cum c
    JOIN seg s ON s.celda = c.celda AND s.period = c.period
    WHERE c.rn_ultimo <= 6            -- ← MANDO: los últimos 6 meses con verdad
      AND c.meses_previos >= 6        -- ← MANDO: historia mínima para examinar
)
SELECT celda, mes = period,
    err_plano_pp = ROUND(100 * (tasa_plano - tasa_real), 2),
    err_seg_pp   = ROUND(100 * (tasa_seg   - tasa_real), 2),
    ahorro_usd   = ROUND((ABS(tasa_plano - tasa_real)
                        - ABS(tasa_seg   - tasa_real)) * c_usd, 2)
INTO #contrafactual_repro
FROM examen;

SELECT ahorro_total = SUM(ahorro_usd),
       celdas_mes   = COUNT(*),
       pct_meses_donde_gana_seg = AVG(CASE WHEN ahorro_usd > 0 THEN 100.0 ELSE 0 END)
FROM #contrafactual_repro;

/* ── VERIFICACIÓN contra la tabla del framework (deben clavar, salvo redondeo
      y el mando del mes en curso — ver nota) ─────────────────────────────── */
SELECT r.celda, r.mes, r.ahorro_usd AS repro, k.ahorro_usd AS framework,
       diff = ROUND(r.ahorro_usd - k.ahorro_usd, 2)
FROM #contrafactual_repro r
FULL JOIN [Kamelot].[dbo].[sff_simpson_contrafactual] k
       ON k.celda = r.celda AND k.mes = CONVERT(varchar(7), r.mes)
WHERE ABS(COALESCE(r.ahorro_usd,0) - COALESCE(k.ahorro_usd,0)) > 1
ORDER BY ABS(COALESCE(r.ahorro_usd,0) - COALESCE(k.ahorro_usd,0)) DESC;

/* NOTAS DE CALIBRACIÓN
   · Tu ejecución del día 12 se hizo con la doctrina ANTIGUA (mes en curso dentro
     de test): si tu raw tiene mes en curso y quieres clavar aquel número, quita
     el filtro is_current_month=0 de truth. Con la doctrina nueva, déjalo.
   · La historia mínima del framework cuenta FILAS de la vista (len>=6), aquí
     meses>=6 — puede examinar algún (celda,mes) de diferencia en celdas raras.
   · period: si es varchar 'yyyy-MM' el ORDER BY es correcto; si es date, ídem. */
