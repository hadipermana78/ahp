import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# ================================================
# CONFIG
# ================================================
MAX_KRITERIA = 30

SLIDER_OPTIONS = [
    "1/9","1/8","1/7","1/6","1/5","1/4","1/3","1/2",
    "1",
    "2","3","4","5","6","7","8","9"
]

LABELS = {
    "1/9": "B jauh lebih penting dari A (1/9)",
    "1/8": "B jauh lebih penting dari A (1/8)",
    "1/7": "B jauh lebih penting dari A (1/7)",
    "1/6": "B jauh lebih penting dari A (1/6)",
    "1/5": "B lebih penting dari A (1/5)",
    "1/4": "B lebih penting dari A (1/4)",
    "1/3": "B cukup lebih penting dari A (1/3)",
    "1/2": "B sedikit lebih penting dari A (1/2)",
    "1": "Sama penting",
    "2": "A sedikit lebih penting dari B (2)",
    "3": "A cukup lebih penting dari B (3)",
    "4": "A lebih penting dari B (4)",
    "5": "A lebih penting dari B (5)",
    "6": "A jauh lebih penting dari B (6)",
    "7": "A jauh lebih penting dari B (7)",
    "8": "A sangat jauh lebih penting dari B (8)",
    "9": "A ekstrim lebih penting dari B (9)"
}

SLMAP = {
    "1/9": 1/9, "1/8": 1/8, "1/7": 1/7, "1/6": 1/6, "1/5": 1/5, "1/4": 1/4, "1/3": 1/3, "1/2": 1/2,
    "1": 1,
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9
}


# ================================================
# FUNCTION AHP
# ================================================
def pairwise_to_matrix(pairs, n):
    M = np.ones((n, n))
    for (i, j), val in pairs.items():
        M[i, j] = val
        M[j, i] = 1 / val
    return M


def priority_from_matrix(M):
    eigvals, eigvecs = np.linalg.eig(M)
    max_index = np.argmax(eigvals.real)
    pr = eigvecs[:, max_index].real
    pr = pr / pr.sum()
    return pr


def consistency_ratio(M):
    n = M.shape[0]
    eigvals, _ = np.linalg.eig(M)
    lam_max = max(eigvals.real)
    CI = (lam_max - n) / (n - 1)

    RI_table = {
        1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12,
        6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49,
        11: 1.51, 12: 1.48, 13: 1.56, 14: 1.57, 15: 1.59
    }
    RI = RI_table.get(n, 1.59)  # untuk n > 15 gunakan 1.59

    CR = CI / RI if RI != 0 else 0
    return lam_max, CI, CR


def export_to_excel(df_matrix, df_weights):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_matrix.to_excel(writer, index=False, sheet_name="Matrix")
        df_weights.to_excel(writer, index=False, sheet_name="Bobot")
    return output.getvalue()


# ================================================
# STREAMLIT UI
# ================================================
st.title("AHP Sistem Pakar")

# -----------------------------------------
# Input jumlah & nama kriteria
# -----------------------------------------
st.subheader("1. Masukkan Jumlah Kriteria")

jml = st.number_input("Jumlah kriteria (1–30)", 1, MAX_KRITERIA, 5)

kriteria = []
for i in range(jml):
    k = st.text_input(f"Nama kriteria {i+1}", f"K{i+1}")
    kriteria.append(k)

st.divider()

# -----------------------------------------
# Pairwise Comparison
# -----------------------------------------
st.subheader("2. Perbandingan Berpasangan")

pairs = {}
for i in range(jml):
    for j in range(i+1, jml):
        key = f"{kriteria[i]} vs {kriteria[j]}"
        val = st.select_slider(
            key,
            options=SLIDER_OPTIONS,
            value="1",
            format_func=lambda x, A=kriteria[i], B=kriteria[j]: LABELS[x].replace("A", A).replace("B", B)
        )
        pairs[(i, j)] = SLMAP[val]

# -----------------------------------------
# Perhitungan AHP
# -----------------------------------------
st.subheader("3. Hasil Perhitungan")

M = pairwise_to_matrix(pairs, jml)
prio = priority_from_matrix(M)
lam, CI, CR = consistency_ratio(M)

df_matrix = pd.DataFrame(M, columns=kriteria, index=kriteria)
df_weights = pd.DataFrame({
    "Kriteria": kriteria,
    "Bobot": prio,
    "Bobot %": prio * 100
})

st.write("### Matriks Perbandingan")
st.dataframe(df_matrix)

st.write("### Bobot Kriteria")
st.dataframe(df_weights)

# Konsistensi
if CR < 0.1:
    st.success(f"Konsisten ✔ (CR = {CR:.4f})")
else:
    st.error(f"TIDAK Konsisten ❌ (CR = {CR:.4f})")


# -----------------------------------------
# Download Excel
# -----------------------------------------
st.subheader("4. Unduh Hasil")

excel_data = export_to_excel(df_matrix, df_weights)

st.download_button(
    "📥 Unduh Excel Hasil AHP",
    data=excel_data,
    file_name="AHP_30Kriteria.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
