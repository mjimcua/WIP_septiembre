"""Same 60% rate, different meaning: binomial sampling distribution for n=30 vs n=100."""
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TRUE_RATE = 0.60
Z_90 = 1.645

def binomial_density(n):
    ks = np.arange(0, n + 1)
    pmf = np.array([math.comb(n, k) * TRUE_RATE**k * (1 - TRUE_RATE)**(n - k) for k in ks])
    rates = ks / n * 100
    density = pmf / (100 / n)          # per percentage point, so curves are comparable
    return rates, density

fig, ax = plt.subplots(figsize=(8.6, 4.8), dpi=150)
for n, color, label_y in [(30, "#E8853D", 0.050), (100, "#2E7FA8", 0.085)]:
    rates, density = binomial_density(n)
    se_pp = 100 * math.sqrt(TRUE_RATE * (1 - TRUE_RATE) / n)
    lo, hi = 60 - Z_90 * se_pp, 60 + Z_90 * se_pp
    ax.plot(rates, density, color=color, lw=2.2, label=f"n = {n}  (banda 90%: ±{Z_90*se_pp:.0f} pp)")
    band = (rates >= lo) & (rates <= hi)
    ax.fill_between(rates[band], 0, density[band], color=color, alpha=0.22)
    ax.annotate(f"[{lo:.0f}%, {hi:.0f}%]", xy=(hi, 0.002), xytext=(hi + 1.5, label_y * 0.45),
                fontsize=10, color=color,
                arrowprops=dict(arrowstyle="-", color=color, lw=1))

ax.axvline(60, color="#444444", lw=1.2, ls="--")
ax.text(60, ax.get_ylim()[1]*0.02 + 0.096, "tasa verdadera 60%", ha="center", fontsize=10, color="#444444")

ax.annotate("de 30 licencias:\nrenuevan entre 14 y 22", xy=(47, 0.021), fontsize=10,
            color="#B05E1E", ha="center")
ax.annotate("de 100 licencias:\nrenuevan entre 52 y 68", xy=(74.5, 0.055), fontsize=10,
            color="#1F5F80", ha="center")

ax.set_xlim(28, 92)
ax.set_ylim(0, 0.105)
ax.set_xlabel("tasa de renovación observada en un mes (%)", fontsize=11)
ax.set_ylabel("qué tan a menudo ocurre", fontsize=11)
ax.set_yticks([])
ax.set_title("La misma tasa del 60% no informa lo mismo:\nel tamaño de la muestra decide cuánto puede bailar el mes",
             fontsize=12.5)
ax.legend(loc="upper left", frameon=False, fontsize=10)
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)
ax.grid(axis="x", alpha=0.15)
plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/fu_30_vs_100.png", bbox_inches="tight")
print("saved")
