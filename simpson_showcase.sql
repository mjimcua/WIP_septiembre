/* ============================================================================
   SIMPSON SHOWCASE FINDER — T-SQL puro (traducción de fase_pre.py)
   Busca celdas donde la rotación del mix softcancel mueve el agregado mientras
   los subgrupos están visualmente planos. Sin estadística: ventanas de borde,
   rangos en pp, y la atribución de primaria: caída explicada = giro × brecha.
   AJUSTA: [tabla_raw], el grano de celda (línea marcada ←GRANO) y filtros.
   ============================================================================ */

WITH monthly AS (        -- 1 · unidades y renovaciones por celda × mes × grupo
    SELECT
        cell    = CAST(tr_regional_level_1 AS varchar(100)),      -- ←GRANO: empieza grueso
        period,                                                    --  (añade dims concatenando)
        is_soft = CASE WHEN softcancel = 1 THEN 1 ELSE 0 END,
        units   = SUM(total_tr_units),
        renewed = SUM(total_renewed_units)
    FROM [Kamelot].[dbo].[tabla_raw]                               -- ← tu raw
    WHERE dataset_role IN ('train','test')                         -- solo meses con verdad
      AND is_current_month = 0
    GROUP BY tr_regional_level_1, period,
             CASE WHEN softcancel = 1 THEN 1 ELSE 0 END
),
lines AS (               -- 2 · las cuatro líneas mensuales de cada celda
    SELECT cell, period,
        units_total = SUM(units),
        share_soft  = 1.0 * SUM(CASE WHEN is_soft = 1 THEN units END)
                          / NULLIF(SUM(units), 0),
        rate_soft   = 1.0 * SUM(CASE WHEN is_soft = 1 THEN renewed END)
                          / NULLIF(SUM(CASE WHEN is_soft = 1 THEN units END), 0),
        rate_rest   = 1.0 * SUM(CASE WHEN is_soft = 0 THEN renewed END)
                          / NULLIF(SUM(CASE WHEN is_soft = 0 THEN units END), 0),
        rate_agg    = 1.0 * SUM(renewed) / NULLIF(SUM(units), 0)
    FROM monthly
    GROUP BY cell, period
),
edged AS (               -- 3 · numerar meses desde ambos extremos (ventanas de borde)
    SELECT *,
        rn_first = ROW_NUMBER() OVER (PARTITION BY cell ORDER BY period ASC),
        rn_last  = ROW_NUMBER() OVER (PARTITION BY cell ORDER BY period DESC),
        n_months = COUNT(*)    OVER (PARTITION BY cell)
    FROM lines
),
summar AS (              -- 4 · métricas visuales por celda
    SELECT cell,
        n_months          = MAX(n_months),
        units_mes_medio   = AVG(units_total),
        share_ini         = AVG(CASE WHEN rn_first <= 3 THEN share_soft END),
        share_fin         = AVG(CASE WHEN rn_last  <= 3 THEN share_soft END),
        agg_ini           = AVG(CASE WHEN rn_first <= 3 THEN rate_agg END),
        agg_fin           = AVG(CASE WHEN rn_last  <= 3 THEN rate_agg END),
        gap_pp            = 100.0 * (AVG(rate_rest) - AVG(rate_soft)),
        rango_soft_pp     = 100.0 * (MAX(rate_soft) - MIN(rate_soft)),
        rango_resto_pp    = 100.0 * (MAX(rate_rest) - MIN(rate_rest))
    FROM edged
    GROUP BY cell
)
SELECT TOP 20 *,          -- 5 · atribución, pureza y score de dramatismo visual
    caida_agregado_pp      = ROUND(100.0 * (agg_fin - agg_ini), 1),
    caida_explicada_mix_pp = ROUND(-(share_fin - share_ini) * gap_pp, 1),
    pureza = CASE WHEN ABS(100.0 * (agg_fin - agg_ini)) > 0.5
                  THEN ROUND(GREATEST(0, LEAST(1,
                       -(share_fin - share_ini) * gap_pp
                       / (100.0 * (agg_fin - agg_ini)))), 2)
                  ELSE 0 END,
    score = ROUND(ABS((share_fin - share_ini) * gap_pp)
          * CASE WHEN ABS(100.0*(agg_fin-agg_ini)) > 0.5
                 THEN GREATEST(0, LEAST(1, -(share_fin-share_ini)*gap_pp
                                            /(100.0*(agg_fin-agg_ini)))) ELSE 0 END
          * CASE WHEN rango_soft_pp <= 10 AND rango_resto_pp <= 10
                 THEN 1.0 ELSE 0.4 END, 2)
FROM summar
WHERE n_months >= 8 AND units_mes_medio >= 20
  AND share_ini IS NOT NULL AND share_fin IS NOT NULL
ORDER BY score DESC;

/* ── Para PINTAR la celda ganadora: sus líneas mes a mes ─────────────────── */
-- SELECT cell, period, units_total, share_soft, rate_soft, rate_rest, rate_agg
-- FROM lines WHERE cell = 'PON_AQUI_LA_CELDA' ORDER BY period;
/* Nota SQL Server < 2022: sustituye GREATEST/LEAST por CASE anidados:
   GREATEST(0, LEAST(1, x)) ≡ CASE WHEN x<0 THEN 0 WHEN x>1 THEN 1 ELSE x END */
