# AHP App - Upgraded UI (Dashboard Professional with Tabs)
# File: ahp_final_ui_upgrade.py
# Style: Dashboard professional (sidebar dark + content white)
# Features: Tabs navigation, slider two-direction inputs, session_state stabilization,
# Heatmap of pairwise matrices, bar chart of weights, reset structure, badges for CI/CR,
# Excel export. Designed for Streamlit.

import streamlit as st
import numpy as np
import pandas as pd
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="AHP Pro - UI Upgrade", layout="wide")

# ----------------------------
# Helper functions (AHP math)
# ----------------------------
RI_TABLE = {1:0.0,2:0.0,3:0.58,4:0.90,5:1.12,6:1.24,7:1.32,8:1.41,9:1.45,
            10:1.49,11:1.51,12:1.48,13:1.56,14:1.57,15:1.59}

SLIDER_OPTIONS = ["B9","B7","B5","B3","1","A3","A5","A7","A9"]
LABELS = {
    "A9":"A jauh lebih penting (9)",
    "A7":"A sangat lebih penting (7)",
    "A5":"A lebih penting (5)",
    "A3":"A agak lebih penting (3)",
    "1":"Setara (1)",
    "B3":"B agak lebih penting (1/3)",
    "B5":"B lebih penting (1/5)",
    "B7":"B sangat lebih penting (1/7)",
    "B9":"B jauh lebih penting (1/9)"
}
SLMAP = {"A9":9.0,"A7":7.0,"A5":5.0,"A3":3.0,
         "1":1.0,
         "B3":1/3.0,"B5":1/5.0,"B7":1/7.0,"B9":1/9.0}


def pairwise_to_matrix(pairs, n):
    M = np.ones((n, n), dtype=float)
    for (i, j), v in pairs.items():
        M[i, j] = v
        M[j, i] = 1.0 / v
    return M


def priority_from_matrix(M):
    col_sum = M.sum(axis=0)
    norm = M / col_sum
    pr = norm.mean(axis=1)
    return pr, norm


def consistency_ratio(M, pr):
    ws = M.dot(pr)
    lam = np.mean(ws / pr)
    n = M.shape[0]
    CI = (lam - n) / (n - 1) if n > 1 else 0.0
    RI = RI_TABLE.get(n, 1.49)
    CR = CI / RI if RI > 0 else 0.0
    return lam, CI, CR


def df_from_matrix(M, labels):
    return pd.DataFrame(M, index=labels, columns=labels)


def to_excel_bytes(dfs: dict):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, df in dfs.items():
            df.to_excel(writer, sheet_name=name[:30])
    return out.getvalue()

# ----------------------------
# Session state init
# ----------------------------
if 'structure_done' not in st.session_state:
    st.session_state.structure_done = False

if 'k_names' not in st.session_state:
    st.session_state.k_names = []
if 'sub_counts' not in st.session_state:
    st.session_state.sub_counts = []
if 'alt_names' not in st.session_state:
    st.session_state.alt_names = []

# ----------------------------
# Layout - Sidebar and Header
# ----------------------------
st.markdown("<h1 style='text-align:center;'>AHP Pro — Dashboard</h1>", unsafe_allow_html=True)
col1, col2 = st.columns([3,1])
with col2:
    if st.button("Reset Struktur", help="Reset semua input dan mulai ulang struktur"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

st.sidebar.title("Pengaturan")
max_k = st.sidebar.number_input("Jumlah Kriteria (max)", min_value=2, max_value=15, value=8)
max_sub = st.sidebar.number_input("Max Subkriteria per Kriteria", min_value=0, max_value=10, value=5)
max_alt = st.sidebar.number_input("Jumlah Alternatif (max)", min_value=1, max_value=10, value=5)

# Navigation tabs
tabs = st.tabs(["Struktur", "Kriteria", "Subkriteria", "Alternatif", "Hasil"])

# ----------------------------
# Tab 1: Struktur
# ----------------------------
with tabs[0]:
    st.header("1. Struktur Hierarki")
    if not st.session_state.structure_done:
        with st.form("form_structure"):
            n_k = st.number_input("Jumlah Kriteria", min_value=2, max_value=max_k, value=4)
            k_names = []
            st.subheader("Nama Kriteria")
            for i in range(n_k):
                nm = st.text_input(f"Kriteria {i+1}", value=f"K{i+1}")
                k_names.append(nm if nm.strip() else f"K{i+1}")

            st.markdown("---")
            st.subheader("Jumlah Subkriteria per Kriteria")
            sub_counts = []
            for i in range(n_k):
                cnt = st.number_input(f"Subkriteria untuk {k_names[i]}", min_value=0, max_value=max_sub, value=0)
                sub_counts.append(int(cnt))

            st.markdown("---")
            n_alt = st.number_input("Jumlah Alternatif", min_value=1, max_value=max_alt, value=3)
            alt_names = []
            st.subheader("Nama Alternatif")
            for j in range(n_alt):
                an = st.text_input(f"Alternatif {j+1}", value=f"A{j+1}")
                alt_names.append(an if an.strip() else f"A{j+1}")

            ok = st.form_submit_button("Simpan Struktur")
        if ok:
            st.session_state.structure_done = True
            st.session_state.k_names = k_names
            st.session_state.sub_counts = sub_counts
            st.session_state.alt_names = alt_names
            st.success("Struktur tersimpan. Silakan lanjut ke tab Kriteria.")
            st.rerun()
    else:
        st.success("Struktur sudah tersimpan.")
        st.write("Kriteria:", st.session_state.k_names)
        st.write("Sub counts:", st.session_state.sub_counts)
        st.write("Alternatif:", st.session_state.alt_names)

# ----------------------------
# Tab 2: Kriteria
# ----------------------------
with tabs[1]:
    st.header("2. Perbandingan Kriteria")
    if not st.session_state.structure_done:
        st.warning("Lengkapi struktur di tab Struktur terlebih dahulu.")
    else:
        k = st.session_state.k_names
        n = len(k)
        pairs = {}
        st.info("Gunakan slider untuk memilih arah dan intensitas kepentingan (A vs B).")
        for i in range(n):
            for j in range(i+1, n):
                lbl = f"{k[i]}  vs  {k[j]}"
                sel = st.select_slider(lbl, options=SLIDER_OPTIONS, value="1",
                                       format_func=lambda x, A=k[i], B=k[j]: LABELS[x].replace('A', A).replace('B', B),
                                       key=f"crit_{i}_{j}")
                pairs[(i,j)] = SLMAP[sel]

        M = pairwise_to_matrix(pairs, n)
        pr, norm = priority_from_matrix(M)
        lam, CI, CR = consistency_ratio(M, pr)
        st.subheader("Matriks Perbandingan Kriteria")
        st.dataframe(df_from_matrix(M, k))

        st.subheader("Bobot Kriteria")
        dfp = pd.DataFrame({"Kriteria":k, "Bobot":pr, "Bobot %":pr*100})
        st.dataframe(dfp)

        # Heatmap (plotly)
        fig = px.imshow(M, x=k, y=k, text_auto=True, color_continuous_scale='RdBu_r', origin='lower')
        fig.update_layout(height=450, margin=dict(l=20,r=20,t=30,b=20))
        st.plotly_chart(fig, use_container_width=True)

        # badges for consistency
        if CR < 0.1:
            st.success(f"Konsistensi OK — λmax={lam:.4f}, CI={CI:.4f}, CR={CR:.4f}")
        else:
            st.error(f"Konsistensi TIDAK OK — λmax={lam:.4f}, CI={CI:.4f}, CR={CR:.4f}")

        st.session_state.M_k = M
        st.session_state.pr_k = pr

# ----------------------------
# Tab 3: Subkriteria
# ----------------------------
with tabs[2]:
    st.header("3. Subkriteria per Kriteria")
    if not st.session_state.structure_done:
        st.warning("Lengkapi struktur di tab Struktur terlebih dahulu.")
    else:
        k = st.session_state.k_names
        sub_counts = st.session_state.sub_counts
        pr_k = st.session_state.pr_k if 'pr_k' in st.session_state else None
        global_sub = {}  # name -> global weight
        alt_list = []

        for idx, cnt in enumerate(sub_counts):
            st.subheader(f"Kriteria: {k[idx]}")
            if cnt == 0:
                st.info(f"{k[idx]} tidak memiliki subkriteria — akan dipakai langsung sebagai item.")
                global_sub[k[idx]] = pr_k[idx] if pr_k is not None else None
                alt_list.append(k[idx])
                continue

            # input sub names
            subs = []
            for s in range(cnt):
                nm = st.text_input(f"Nama subkriteria {s+1} untuk {k[idx]}", value=f"{k[idx]}_sub{s+1}", key=f"subname_{idx}_{s}")
                subs.append(nm)

            # pairwise
            pairs_s = {}
            for i in range(cnt):
                for j in range(i+1, cnt):
                    lbl = f"{subs[i]} vs {subs[j]}"
                    sel = st.select_slider(lbl, options=SLIDER_OPTIONS, value="1",
                                           format_func=lambda x, A=subs[i], B=subs[j]: LABELS[x].replace('A', A).replace('B', B),
                                           key=f"sub_{idx}_{i}_{j}")
                    pairs_s[(i,j)] = SLMAP[sel]

            M_s = pairwise_to_matrix(pairs_s, cnt)
            pr_s, _ = priority_from_matrix(M_s)
            lam_s, CI_s, CR_s = consistency_ratio(M_s, pr_s)

            st.write("Matriks Subkriteria:")
            st.dataframe(df_from_matrix(M_s, subs))
            st.dataframe(pd.DataFrame({"Subkriteria":subs, "Bobot":pr_s, "Bobot %":pr_s*100}))

            # heatmap per sub
            fig_s = px.imshow(M_s, x=subs, y=subs, text_auto=True, color_continuous_scale='RdBu_r', origin='lower')
            fig_s.update_layout(height=350, margin=dict(l=10,r=10,t=10,b=10))
            st.plotly_chart(fig_s, use_container_width=True)

            if CR_s < 0.1:
                st.success(f"Subkriteria konsisten — CR={CR_s:.4f}")
            else:
                st.error(f"Subkriteria TIDAK konsisten — CR={CR_s:.4f}")

            for sname, w in zip(subs, pr_s):
                global_sub[sname] = (pr_k[idx] * w) if pr_k is not None else None
                alt_list.append(sname)

        st.session_state.global_sub = global_sub
        st.session_state.alt_under = alt_list

# ----------------------------
# Tab 4: Alternatif
# ----------------------------
with tabs[3]:
    st.header("4. Perbandingan Alternatif per Item (subkriteria atau kriteria tanpa sub)")
    if not st.session_state.structure_done:
        st.warning("Lengkapi struktur di tab Struktur terlebih dahulu.")
    else:
        alt = st.session_state.alt_names
        items = st.session_state.alt_under if 'alt_under' in st.session_state else []
        alt_prior = {}
        for item in items:
            st.subheader(f"Item: {item}")
            pairs_a = {}
            m = len(alt)
            for i in range(m):
                for j in range(i+1, m):
                    lbl = f"{alt[i]} vs {alt[j]} (untuk {item})"
                    sel = st.select_slider(lbl, options=SLIDER_OPTIONS, value="1",
                                           format_func=lambda x, A=alt[i], B=alt[j]: LABELS[x].replace('A', A).replace('B', B),
                                           key=f"alt_{item}_{i}_{j}")
                    pairs_a[(i,j)] = SLMAP[sel]

            M_a = pairwise_to_matrix(pairs_a, m)
            pr_a, _ = priority_from_matrix(M_a)
            lam_a, CI_a, CR_a = consistency_ratio(M_a, pr_a)

            st.dataframe(pd.DataFrame({"Alternatif":alt, "Bobot":pr_a, "Bobot %":pr_a*100}))
            if CR_a < 0.1:
                st.success(f"Matrix alternatif konsisten — CR={CR_a:.4f}")
            else:
                st.error(f"Matrix alternatif tidak konsisten — CR={CR_a:.4f}")

            alt_prior[item] = pr_a

        st.session_state.alt_prior = alt_prior

# ----------------------------
# Tab 5: Hasil & Eksport
# ----------------------------
with tabs[4]:
    st.header("5. Hasil Akhir & Export")
    if not st.session_state.structure_done:
        st.warning("Lengkapi struktur di tab Struktur terlebih dahulu.")
    else:
        # Show global sub weights
        global_sub = st.session_state.global_sub if 'global_sub' in st.session_state else {}
        df_gl = pd.DataFrame(list(global_sub.items()), columns=["Item","GlobalWeight"]) if global_sub else pd.DataFrame()
        if not df_gl.empty:
            df_gl = df_gl.sort_values('GlobalWeight', ascending=False).reset_index(drop=True)
            st.subheader("Bobot Global (subkriteria)")
            st.dataframe(df_gl)

            # bar chart
            figb = px.bar(df_gl, x='Item', y='GlobalWeight', title='Bobot Global per Item')
            st.plotly_chart(figb, use_container_width=True)

        # Final scoring
        alt = st.session_state.alt_names
        m = len(alt)
        final_scores = np.zeros(m)
        if 'alt_prior' in st.session_state and global_sub:
            for item, gw in global_sub.items():
                vec = st.session_state.alt_prior.get(item)
                if vec is None:
                    continue
                final_scores += gw * vec

            dff = pd.DataFrame({"Alternatif":alt, "Skor":final_scores})
            dff['Skor %'] = dff['Skor'] / dff['Skor'].sum() * 100
            dff = dff.sort_values('Skor', ascending=False).reset_index(drop=True)
            st.subheader("Ranking Alternatif")
            st.dataframe(dff)

            # pie
            figp = px.pie(dff, names='Alternatif', values='Skor %', title='Distribusi Skor Alternatif')
            st.plotly_chart(figp, use_container_width=True)

            # Export
            to_export = {"GlobalWeights": df_gl, "FinalRanking": dff}
            # include per-item alt priorities
            for item, vec in st.session_state.alt_prior.items():
                to_export[f"AltUnder_{item}"] = pd.DataFrame({"Alternatif":alt, "Priority":vec})

            st.download_button("Unduh Hasil (.xlsx)", data=to_excel_bytes(to_export), file_name='AHP_results_pro.xlsx')
        else:
            st.info("Lengkapi perbandingan untuk subkriteria dan alternatif terlebih dahulu.")

# ----------------------------
# End
# ----------------------------

