"""Simpson via softcancel — two lessons, two panels, one tiny controlled dataset.
A: aggregate rate falls while BOTH subgroup rates are flat (mix rotation alone).
B: the snapshot trap — projecting future months with TODAY's (immature) softcancel
   mix overestimates renewal; the gap grows with horizon (as-of doctrine, decision 19)."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RATE_NORMAL, RATE_SOFT = 0.85, 0.20
N_MONTHLY = 1000

# ── Panel A dataset: calendar months, softcancel share grows 5% → 30% ─────────
months = pd.period_range("2025-01", "2026-06", freq="M")
share = np.linspace(0.05, 0.30, len(months))
aggregate = RATE_NORMAL * (1 - share) + RATE_SOFT * share
demo = pd.DataFrame({"month": months.astype(str), "softcancel_share": share.round(3),
                     "rate_normal": RATE_NORMAL, "rate_softcancel": RATE_SOFT,
                     "rate_aggregate": aggregate.round(4),
                     "units_normal": (N_MONTHLY*(1-share)).astype(int),
                     "units_softcancel": (N_MONTHLY*share).astype(int)})
demo.to_csv("/mnt/user-data/outputs/raw_simpson_demo.csv", index=False)

# ── Panel B: maturation curve — softcancel share vs months-to-expiry ──────────
def mature_share(months_to_expiry):
    return max(0.03, 0.30 - 0.045 * months_to_expiry)   # 0m→30% · 3m→16.5% · 6m→3%
horizons = np.arange(1, 7)
share_today = np.array([mature_share(h) for h in horizons])       # snapshot at T0
share_final = 0.30                                                # at expiry
projected = RATE_NORMAL * (1 - share_today) + RATE_SOFT * share_today
realized = RATE_NORMAL * (1 - share_final) + RATE_SOFT * share_final

fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=150)
ax = axes[0]
ax.plot(range(len(months)), [RATE_NORMAL*100]*len(months), color="#1D9E75", lw=2.2, label="normales: 85% (plana)")
ax.plot(range(len(months)), [RATE_SOFT*100]*len(months), color="#C0392B", lw=2.2, label="softcancel: 20% (plana)")
ax.plot(range(len(months)), aggregate*100, color="#2E7FA8", lw=2.8, label="AGREGADO (lo que ves)")
ax2 = ax.twinx()
ax2.fill_between(range(len(months)), share*100, color="#E8853D", alpha=0.18)
ax2.set_ylabel("cuota softcancel (%)", color="#B05E1E", fontsize=9); ax2.set_ylim(0, 60)
ax2.tick_params(axis="y", labelcolor="#B05E1E", labelsize=8)
ax.annotate("cae 16pp sin que\nNADIE cambie", xy=(14, 68), fontsize=10.5, color="#1F5F80", ha="center")
ax.set_title("A · La paradoja: el mix rota, el agregado miente", fontsize=11.5)
ax.set_ylabel("tasa de renovación (%)"); ax.set_ylim(0, 100)
ax.set_xticks([0, 6, 12, 17]); ax.set_xticklabels(["2025-01", "2025-07", "2026-01", "2026-06"], fontsize=8)
ax.legend(loc="lower left", fontsize=8.5, frameon=False)

ax = axes[1]
ax.plot(horizons, projected*100, "o-", color="#2E7FA8", lw=2.2, label="proyección ingenua (mix de HOY)")
ax.plot(horizons, [realized*100]*len(horizons), "s--", color="#C0392B", lw=2.2, label="realidad al vencer (mix maduro: 30%)")
for h, p in zip(horizons, projected):
    ax.annotate(f"+{(p-realized)*100:.0f}pp", xy=(h, p*100 + 1.2), ha="center", fontsize=9, color="#B05E1E")
ax.set_title("B · La trampa del snapshot: el softcancel aún no ha llegado", fontsize=11.5)
ax.set_xlabel("horizonte (meses hasta el vencimiento)"); ax.set_ylabel("tasa proyectada (%)")
ax.set_ylim(55, 90); ax.legend(loc="upper left", fontsize=8.5, frameon=False)
for a in axes:
    for spine in ("top", "right"): a.spines[spine].set_visible(False)
plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/simpson_softcancel.png", bbox_inches="tight")
print("share hoy por horizonte:", dict(zip(horizons.tolist(), (share_today*100).round(1).tolist())))
print(f"sobreestimación a 6 meses: +{(projected[-1]-realized)*100:.1f}pp")
