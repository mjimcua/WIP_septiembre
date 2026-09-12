"""Two teaching charts: (A) exact Binomial(100, 0.6) — point vs interval probability;
(B) how the 90% band shrinks with sample size (the 1/sqrt(n) law)."""
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TRUE_RATE = 0.60
Z_90 = 1.645

def pmf(n, k):
    return math.comb(n, k) * TRUE_RATE**k * (1 - TRUE_RATE)**(n - k)

# ── Chart A: PMF for n=100, highlighting exactly-60 vs exactly-50 ─────────────
n = 100
ks = np.arange(30, 91)
probs = np.array([pmf(n, k) for k in ks])
p60, p50 = pmf(n, 60), pmf(n, 50)
p55_65 = sum(pmf(n, k) for k in range(55, 66))
lo, hi = 60 - Z_90 * 4.899, 60 + Z_90 * 4.899

fig, ax = plt.subplots(figsize=(8.6, 4.6), dpi=150)
colors = ["#2E7FA8" if k not in (50, 60) else ("#1D9E75" if k == 60 else "#C0392B") for k in ks]
ax.bar(ks, probs, width=0.85, color=colors, alpha=0.85)
band = (ks >= lo) & (ks <= hi)
ax.plot(ks[band], probs[band] + 0.0015, lw=0, marker="", color="none")
ax.axvspan(lo, hi, color="#2E7FA8", alpha=0.08)
ax.annotate(f"exactamente 60: {p60*100:.1f}%\n(el valor MÁS probable)", xy=(60, p60),
            xytext=(70, p60*0.97), fontsize=10, color="#14735A",
            arrowprops=dict(arrowstyle="->", color="#14735A"))
ax.annotate(f"exactamente 50: {p50*100:.1f}%\n({p60/p50:.0f}× menos que 60)", xy=(50, p50),
            xytext=(33, p50 + 0.028), fontsize=10, color="#C0392B",
            arrowprops=dict(arrowstyle="->", color="#C0392B"))
ax.annotate(f"entre 55 y 65: {p55_65*100:.0f}%\n(la banda es lo que pesa)", xy=(64, 0.055),
            fontsize=10, color="#1F5F80", ha="left")
ax.set_xlabel("renovaciones observadas de 100 (tasa verdadera = 60%)", fontsize=11)
ax.set_yticks([])
ax.set_ylabel("probabilidad", fontsize=11)
ax.set_title("n=100, tasa verdadera 60%: ningún valor exacto es probable —\nla probabilidad vive en los intervalos", fontsize=12.5)
for spine in ("top", "right", "left"):
    ax.spines[spine].set_visible(False)
plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/binomial_pmf_100.png", bbox_inches="tight")
plt.close()

# ── Chart B: the 1/sqrt(n) law — band width vs sample size ────────────────────
ns = np.arange(10, 5001)
moe = Z_90 * 100 * np.sqrt(TRUE_RATE * (1 - TRUE_RATE) / ns)
markers = [30, 100, 400, 1600]
fig, ax = plt.subplots(figsize=(8.6, 4.6), dpi=150)
ax.plot(ns, moe, color="#2E7FA8", lw=2.4)
for m in markers:
    y = Z_90 * 100 * math.sqrt(TRUE_RATE * (1 - TRUE_RATE) / m)
    ax.plot(m, y, "o", color="#E8853D", ms=7)
    ax.annotate(f"n={m}\n±{y:.1f} pp", xy=(m, y), xytext=(m*1.18, y*1.12),
                fontsize=10, color="#B05E1E")
ax.set_xscale("log")
ax.set_xlabel("tamaño de muestra n (escala log)", fontsize=11)
ax.set_ylabel("banda 90% (± pp)", fontsize=11)
ax.set_title("La banda encoge con √n: cuadruplicar la muestra la reduce a la mitad\n(rendimientos decrecientes: ×100 muestras → solo ÷10 banda)", fontsize=12.5)
ax.grid(alpha=0.2, which="both")
for spine in ("top", "right"):
    ax.spines[spine].set_visible(False)
plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/band_vs_n.png", bbox_inches="tight")
print(f"P(X=60)={p60*100:.2f}%  P(X=50)={p50*100:.2f}%  ratio={p60/p50:.1f}  P(55-65)={p55_65*100:.1f}%")
