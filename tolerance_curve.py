"""Business dial: for each tolerance (pp), what share of projection money is
predictable within it at 90% — computed from sff_fu_summary (raw, worst case)."""
import sqlite3
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB_PATH = "salida/sff_v2_golden.db"          # point this at Kamelot's export
TOLERANCE_MARKS = [3, 5, 10, 15]

con = sqlite3.connect(DB_PATH)
rows = con.execute("""SELECT moe_pp_max, total_tr_usd FROM sff_fu_summary
                      WHERE dataset_role='projection' AND is_current_month=0""").fetchall()
moe = np.array([r[0] for r in rows]); usd = np.array([r[1] for r in rows])
total_usd = usd.sum()

taus = np.linspace(0.5, 20, 200)
share = [usd[moe <= t].sum() / total_usd * 100 for t in taus]

fig, ax = plt.subplots(figsize=(8.6, 4.8), dpi=150)
ax.plot(taus, share, color="#2E7FA8", lw=2.6)
for t in TOLERANCE_MARKS:
    y = usd[moe <= t].sum() / total_usd * 100
    ax.plot(t, y, "o", color="#E8853D", ms=8)
    ax.annotate(f"±{t}pp → {y:.0f}% del $", xy=(t, y), xytext=(t + 0.5, max(y - 9, 4)),
                fontsize=10.5, color="#B05E1E")
ax.axhline(100, color="#cccccc", lw=0.8)
ax.set_xlabel("tolerancia elegida por negocio (± puntos, con 90% de seguridad)", fontsize=11)
ax.set_ylabel("% del dinero de projection\npredecible dentro de la tolerancia", fontsize=11)
ax.set_title("El dial de negocio (foto RAW, peor caso):\ncada tolerancia compra un % del dinero — el resto es ruido a nivel de celda",
             fontsize=12.5)
ax.set_ylim(0, 106); ax.set_xlim(0, 20)
ax.grid(alpha=0.2)
for spine in ("top", "right"):
    ax.spines[spine].set_visible(False)
plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/tolerance_dial.png", bbox_inches="tight")
for t in TOLERANCE_MARKS:
    inside = usd[moe <= t].sum()
    print(f"τ=±{t:>2}pp: {inside/total_usd*100:5.1f}% del $ dentro · fuera ${total_usd-inside:,.0f}")
