"""synthetic.py — synthetic dataset v2. FEATURE-COVERAGE MATRIX feature→scenario:
exhaustive config→optional leftover column | conservation→discount combos per FU | universes/routes→flag_ts, train_only, projection_only
gaps→NA|B missing months | L1 sign→small negative dormant/softcancel/no_instalado (15/12/10: only together do they cross 30) + minority positive autorenew
L2 asterisco→product con η² alto vs channel mudo, hermanas pequeñas | credibilidad→rate_series_by_pool ínfimas con mandatory_cell padre gorda
Simpson→NA: product A (.90, weight falling) vs B (.50, weight rising): the aggregate falls while each part is stable | combinations→region×product interaction
uplift starting point→newcust+d40 landing at 1.5 vs veterans at 1.03 | intervals→discount levels | dynamics→EU|A seasonal, EU|B trend that must saturate
current month→2026-02 labeled test | residue→no_instalado=1 → semantic label"""
import numpy as np, pandas as pd, itertools

MESES = pd.period_range("2024-01", "2026-06", freq="M")
def rol(m):
    s = str(m)
    return "projection" if s >= "2026-03" else ("test" if s >= "2025-11" else "train")

def build_raw(seed=7):
    rng = np.random.default_rng(seed)
    collected_rows = []
    def serie(region, product, channel, dorm, soft, noin, auto, n0, tasa_f, combos, meses=None, ts=0):
        for i, m in enumerate(meses if meses is not None else MESES):
            r = rol(m)
            base = tasa_f(i, m)
            for (disc, newc, peso) in combos:
                n = max(1, int(round(n0 * peso)))
                auv = 30.0 * (0.6 if disc == "d40" else 1.0)
                pu, pd_ = n, n * auv
                if r == "projection":
                    ru = rd = np.nan
                else:
                    p = min(0.99, max(0.01, base + rng.normal(0, 0.015)))
                    ru = rng.binomial(n, p)
                    uplift_lookup = 1.5 if (newc == 1 and disc == "d40") else (1.10 if disc == "d40" else 1.03)
                    rd = ru * auv * (uplift_lookup + rng.normal(0, 0.02))
                collected_rows.append(dict(period=str(m), dataset_role=r, total_tr_units=pu, total_tr_usd=pd_,
                    total_renewed_units=ru, total_renewed_usd=rd, is_current_month=int(str(m) == "2026-02"),
                    flag_time_series=ts, region=region, product=product, channel=channel,
                    dormant=dorm, softcancel=soft, no_instalado=noin, autorenew=auto,
                    discount=disc, newcust=newc))
    mix = [("d0", 0, .7), ("d40", 1, .3)]
    plano = [("d0", 0, 1.0)]
    # EU|A big seasonal (A4): base .80 + yearly sine
    serie("EU","A","web",0,0,0,0, 600, lambda i,m: .80 + .05*np.sin(2*np.pi*(m.month-1)/12), mix)
    # EU|B declining trend .86→.70 (A1, saturates in backtest)
    serie("EU","B","web",0,0,0,0, 300, lambda i,m: .86 - .006*i, mix)
    # mute channel: same rates on 'tele' (η² channel ≈ 0), small → L2 annuls channel
    serie("EU","A","tele",0,0,0,0, 12, lambda i,m: .80 + .05*np.sin(2*np.pi*(m.month-1)/12), plano)
    serie("EU","B","tele",0,0,0,0, 10, lambda i,m: .86 - .006*i, plano)
    # NA Simpson: A .90 peso cae 1.0→0.4; B .50 peso sube
    for i, m in enumerate(MESES):
        wA = max(.4, 1.0 - .022*i)
        serie("NA","A","web",0,0,0,0, int(400*wA), lambda i2,m2: .90, plano, meses=[m])
        serie("NA","B","web",0,0,0,0, int(400*(1.6-wA)), lambda i2,m2: .50, plano, meses=[m])
    # small EU timevarying (L1 by sign: 15+12+10=37 crosses the floor of 30)
    serie("EU","A","web",1,0,0,0, 15, lambda i,m: .45, plano)
    serie("EU","A","web",0,1,0,0, 12, lambda i,m: .35, plano)
    serie("EU","A","web",0,0,1,0, 10, lambda i,m: .40, plano)   # no_instalado → residue label
    serie("EU","A","web",1,1,0,0,  5, lambda i,m: .30, plano)
    serie("EU","A","web",0,0,0,1,  6, lambda i,m: .93, plano)   # minority positive
    # gaps: NA|B tele with months missing inside its history
    conh = [m for j, m in enumerate(MESES) if j % 4 != 2]
    serie("NA","B","tele",0,0,0,0, 40, lambda i,m: .55, plano, meses=conh)
    # routes: train_only (no_impact) and projection_only (heuristic)
    serie("NA","A","tele",0,0,0,0, 25, lambda i,m: .70, plano, meses=[m for m in MESES if rol(m)=="train"])
    serie("EU","B","tienda",0,0,0,0, 30, lambda i,m: .60, plano, meses=[m for m in MESES if rol(m)=="projection"])
    # time_series universe
    serie("EU","A","kiosk",0,0,0,0, 50, lambda i,m: .65, plano, ts=1)
    return pd.DataFrame(collected_rows)
