"""validation.py — Run validation: does every artifact hold what it promises?

Complements the equivalence gate (which compares against a golden) and the inline
asserts (which stop the run). This module never stops anything: it MEASURES the
health of a finished run and persists the verdict, so a run against real data can
be audited without reading the console.

Three families of check:
  · INTEGRITY   — conservation, uniqueness, coverage of the joins (must PASS)
  · DOCTRINE    — the sealed rules actually hold (projection empty of results,
                  rate under the cap, current month out of the judge, mandatory
                  dims never annulled in L1/L2)
  · QUALITY     — informative numbers with a threshold: how much money was
                  repaired, how many pools have a measured band, band calibration.
"""
import numpy as np
import pandas as pd


def _check(name: str, family: str, value, threshold_text: str, passed, detail: str = ""):
    return dict(check=name, familia=family, valor=value, esperado=threshold_text,
                estado="PASS" if passed else ("WARN" if passed is None else "FAIL"),
                detalle=detail)


def run_validation(artifacts: dict, cfg) -> pd.DataFrame:
    """GOAL: audit a finished run and persist `validation_report`.

    INPUT:  artifacts (dict with the frames produced by the run) · cfg.
    OUTPUT: persisted table `validation_report` (one row per check) + console panel.
    STEPS:
      [1] Integrity: money conserved, keys unique, every raw row reaches the bridge.
      [2] Doctrine: projection clean, cap respected, current month out, mandatory intact.
      [3] Quality: repair effect in $, technique and band coverage, calibration.
      [4] Persist and print the panel, FAILs first.
    """
    fine = artifacts["fine_grain_table"]; view = artifacts["fu_view"]
    bridge = artifacts.get("key_bridge"); forecast = artifacts.get("future_rows")
    chain = artifacts.get("support_chain_rows"); rolling = artifacts.get("rolling_table")
    selection = artifacts.get("technique_selection"); bands = artifacts.get("forecast_bands")
    dynamics = artifacts.get("dynamics_diagnosis"); uplift = artifacts.get("uplift_cells")
    rows = []

    # [1] INTEGRITY
    fine_usd = float(fine[cfg.pipeline_usd_col].sum())
    view_usd = float(view[cfg.pipeline_usd_col].sum())
    rows.append(_check("pipeline conservado fine↔vista", "INTEGRITY", round(view_usd, 2),
                       f"= {fine_usd:,.2f}", abs(fine_usd - view_usd) < 1e-6,
                       "la vista agrega sin perder ni un dólar"))
    rows.append(_check("fu_id único en la vista", "INTEGRITY", int(view["fu_id"].duplicated().sum()),
                       "= 0", not view["fu_id"].duplicated().any(),
                       "un duplicado significaría grano mal declarado"))
    if bridge is not None:
        covered = fine["fu_comb_key"].isin(bridge["fu_comb_key"]).mean()
        rows.append(_check("cobertura raw→key_bridge", "INTEGRITY", f"{covered:.1%}", "= 100%",
                           covered > 0.9999, "toda fila del raw debe alcanzar sus linajes"))
        rows.append(_check("fu_comb_key único en el puente", "INTEGRITY",
                           int(bridge["fu_comb_key"].duplicated().sum()), "= 0",
                           not bridge["fu_comb_key"].duplicated().any()))

    # [2] DOCTRINE
    projection = fine[fine[cfg.dataset_role_col] == "projection"]
    early_results = float(projection[cfg.renewed_units_col].fillna(0).sum())
    rows.append(_check("projection sin resultados", "DOCTRINE", early_results, "= 0",
                       early_results == 0, "el futuro no puede traer renovaciones ya contadas"))
    current_in_projection = fine[(fine[cfg.current_month_col].isin([1, True, "1"]))
                                 & (fine[cfg.dataset_role_col] != "projection")]
    rows.append(_check("mes en curso en projection", "DOCTRINE", len(current_in_projection),
                       "= 0 filas fuera", len(current_in_projection) == 0,
                       "es el primer mes a proyectar, nunca test"))
    if forecast is not None and len(forecast) and "tasa_origen" in forecast.columns:
        global_fallback_rows = int((forecast["tasa_origen"] == "global").sum())
        rows.append(_check("filas sin tasa propia ni de celda", "INTEGRITY", global_fallback_rows,
                           "= 0 filas", global_fallback_rows == 0,
                           "caer al promedio global indica lookup roto o fase 1 sin cobertura"))
        own_rate_money = forecast.loc[forecast["tasa_origen"] == "serie", cfg.pipeline_usd_col].sum()
        total_money = max(forecast[cfg.pipeline_usd_col].sum(), 1)
        rows.append(_check("$ del forecast con tasa de su propia serie", "QUALITY",
                           f"{100 * own_rate_money / total_money:.0f}%", "informativo", None,
                           "el resto hereda de su celda: normal en series nuevas"))
    if forecast is not None and len(forecast):
        over_cap = int((forecast["tasa"] > cfg.rate_cap + 1e-9).sum())
        rows.append(_check("tasa bajo el techo", "DOCTRINE", over_cap, "= 0 filas", over_cap == 0,
                           f"techo declarado {cfg.rate_cap:.0%}"))
        bad_uplift = int((forecast["uplift"] <= 0).sum())
        rows.append(_check("uplift positivo", "DOCTRINE", bad_uplift, "= 0 filas", bad_uplift == 0,
                           "renovar gratis no existe"))
        nan_expected = int(forecast["esperado_usd"].isna().sum())
        rows.append(_check("forecast sin NaN", "DOCTRINE", nan_expected, "= 0 filas", nan_expected == 0))
    if chain is not None and len(chain):
        # only the MANDATORY positions matter: extras may legitimately carry '*' (that is
        # what L2 does), and 3_shrink points at a ladder parent whose '*' are its purpose
        mandatory_count = len(cfg.business_mandatory_dims)
        pool_stage_ids = chain[chain["etapa"].isin(["1_L1", "2_L2"])]["id_efectivo"].astype(str)
        mandatory_annulled = int(sum("*" in identifier.split("|")[:mandatory_count]
                                     for identifier in pool_stage_ids))
        rows.append(_check("mandatory intactas en L1/L2", "DOCTRINE", mandatory_annulled,
                           "= 0 ids", mandatory_annulled == 0,
                           "solo la escalera de padres puede colapsar mandatory"))

    # [3] QUALITY
    if chain is not None and len(chain):
        raw_stage = chain[chain["etapa"] == "0_raw"]
        final_stage = chain[chain["etapa"] == "3_shrink"]
        money_below_raw = float(raw_stage[raw_stage["n_efectivo"] < cfg.support_floor]["usd_proj"].sum())
        money_below_final = float(final_stage[final_stage["n_efectivo"] < cfg.support_floor]["usd_proj"].sum())
        repaired = money_below_raw - money_below_final
        rows.append(_check("dinero reparado por la maquinaria", "QUALITY",
                           f"${repaired:,.0f}", "> 0 si había polvo",
                           repaired >= 0 if money_below_raw > 0 else None,
                           f"de ${money_below_raw:,.0f} bajo el suelo quedan ${money_below_final:,.0f}"))
    if selection is not None and len(selection):
        fallback_share = (selection["tecnica_elegida"] == "T2_promedio").mean()
        rows.append(_check("pools con técnica ganadora (no retador)", "QUALITY",
                           f"{1 - fallback_share:.0%}", "informativo", None,
                           "el resto se queda con el promedio: sin señal explotable"))
    if rolling is not None and len(rolling):
        coverage = float(rolling["dentro_de_cota"].mean())
        rows.append(_check("calibración: predicciones dentro de su cota", "QUALITY",
                           f"{coverage:.0%}", "≈ 90% si la cota fuera perfecta",
                           None if coverage < 0.85 else True,
                           "por debajo de 90% ⇒ el proceso baila más que la moneda (phi>1)"))
    if bands is not None and len(bands):
        measured = 1 - float(bands["banda_fallback"].mean())
        rows.append(_check("filas con banda MEDIDA", "QUALITY", f"{measured:.0%}", "≥ 50% deseable",
                           measured >= 0.5, "el resto usa la cota binomial, declarada"))
    if dynamics is not None and len(dynamics):
        seasonal_short = int(((dynamics["gate"] == "estacional") & (dynamics["meses"] < 13)).sum())
        rows.append(_check("estacionalidad solo con ciclo completo", "QUALITY", seasonal_short,
                           "= 0 pools", seasonal_short == 0, "≥13 meses antes de hablar de estación"))
        if "phi" in dynamics.columns:
            engines = int((dynamics["phi"] > 1.5).sum())
            rows.append(_check("pools con motor real (phi>1.5)", "QUALITY", engines, "informativo",
                               None, "su baile no es solo la moneda"))
    if uplift is not None and len(uplift):
        implausible = int(((uplift["uplift_final"] < 0.3) | (uplift["uplift_final"] > 3.0)).sum())
        rows.append(_check("uplift en rango plausible", "QUALITY", implausible,
                           "= 0 celdas fuera de [0.3, 3.0]", implausible == 0))

    # [4] persist and narrate
    report = pd.DataFrame(rows)
    cfg.write(report, "validation_report")
    failed = report[report["estado"] == "FAIL"]
    warned = report[report["estado"] == "WARN"]
    print("\n" + "═" * 70)
    print(f"VALIDATION REPORT — {len(report)} checks · "
          f"{(report['estado'] == 'PASS').sum()} PASS · {len(warned)} WARN · {len(failed)} FAIL")
    for _, row in pd.concat([failed, warned, report[report["estado"] == "PASS"]]).iterrows():
        mark = {"PASS": "✓", "WARN": "•", "FAIL": "✗"}[row["estado"]]
        print(f"  {mark} [{row['familia']:9s}] {row['check']:42s} {str(row['valor']):>14s}"
              f"   ({row['esperado']})")
    print("═" * 70)
    return report
