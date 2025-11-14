# ahp_final_ui_refactored.py
import streamlit as st
import numpy as np
import pandas as pd
from io import BytesIO
import plotly.express as px
import re

# ----------------------------
# Page config
# ----------------------------
st.set_page_config(page_title="AHP Pro - Refactored", layout="wide")

# ----------------------------
# Constants & helpers (AHP)
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

def sanitize_key(s):
    """Sanitize strings to be safe as Streamlit keys."""
    if s is None:
        return ""
    s = str(s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^0-9a-zA-Z_\-\.]", "", s)
    return s

def pairwise_to_matrix(pairs, n):
    M = np.ones((n, n), dtype=float)
    for (i, j), v in pairs.items():
        M[i, j] = v
        M[j, i] = 1.0 / v
    return M

def priority_from_matrix(M):
    col_sum = M.sum(axis=0)
    # guard against divide by zero
    col_sum[col_sum == 0] = 1e-12
    norm = M / col_sum
    pr = norm.mean(axis=1)
    return pr, norm

def consistency_ratio(M, pr):
    ws = M.dot(pr)
    # avoid division by zero in ws/pr
    with np.errstate(divide='ignore', invalid='ignore'):
        lam = np.mean(np.where(pr != 0, ws / pr, 0.0))
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
            # safe sheet name
            sheet = str(name)[:30]
            df.to_excel(writer, sheet_name=sheet, index=False)
    return out.getvalue()

def make_label_formatter(A, B):
    # return a function that formats slider option labels using A and B (captures current A/B safely)
    return lambda x: LABELS[x].replace("A", A).replace("B", B)

# ----------------------------
# Session-state defaults
# ----------------------------
if 'structure_done' not in st.session_state:
    st.session_state.structure_done = False
if 'k_names' not in st.session_state:
    st.session_state.k_names = []
if 'sub_counts' not in st.session_state:
    st.session_state.sub_counts = []
if 'alt_names' not in st.session_state:
    st.session_state.alt_names = []
# store results; leave None / empty until computed
if 'M_k' not in st.session_state:
    st.session_state.M_k = None
if 'pr_k' not in st.session_state:
    st.session_state.pr_k = None
if 'global_sub' not in st.session_state:
    st.session_state.global_sub = {}
if 'alt_prior' not in st.session_state:
    st.session_state.alt_prior = {}
if 'alt_under' not in st.session_state:
    st.session_state.alt_under = []

# ----------------------------
# Sidebar
# ----------------------------
st.sidebar.title("Pengaturan Umum")
disabled_sidebar = st.session_state.structure_done

max_k = st.sidebar.number_input("Jumlah Kriteria (max)", min_value=2, max_value=20, value=8, step=1, disabled=disabled_sidebar, key="sb_max_k")
max_sub = st.sidebar.number_input("Max Subkriteria per Kriteria", min_value=0, max_value=15, value=5, step=1, disabled=disabled_sidebar, key="sb_max_sub")
max_alt = st.sidebar.number_input("Jumlah Alternatif (max)", min_value=1, max_value=50, value=5, step=1, disabled=disabled_sidebar, key="sb_max_alt")

if st.sidebar.button("Reset Struktur & Data"):
    # clear all session state
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.success("Semua data di-reset.")
    st.rerun()

# header reset
st.markdown("<h1 style='text-align:center;'>AHP Pro — Refactored</h1>", unsafe_allow_html=True)
col1, col2 = st.columns([3,1])
with col2:
    if st.button("Reset Struktur (Header)"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ----------------------------
# Tabs
# ----------------------------
tabs = st.tabs(["Struktur", "Kriteria", "Subkriteria", "Alternatif", "Hasil & Export"])

# ----------------------------
# Tab: Struktur
# ----------------------------
with tabs[0]:
    st.header("1. Struktur Hierarki")
    if not st.session_state.structure_done:
        with st.form("form_structure", clear_on_submit=False):
            default_n_k = min(4, max_k)
            n_k = st.number_input("Jumlah Kriteria", min_value=2, max_value=max_k, value=default_n_k, step=1, key="form_n_k")
            st.subheader("Nama Kriteria")
            k_names = []
            for i in range(int(n_k)):
                nm_key = f"input_kname_{i}"
                default_k = st.session_state.k_names[i] if i < len(st.session_state.k_names) else f"K{i+1}"
                nm = st.text_input(f"Kriteria {i+1}", value=default_k, key=nm_key)
                nm = nm.strip() if nm.strip() else f"K{i+1}"
                k_names.append(nm)

            st.markdown("---")
            st.subheader("Jumlah Subkriteria per Kriteria")
            sub_counts = []
            for i in range(int(n_k)):
                sc_key = f"input_subcount_{i}"
                default_sc = int(st.session_state.sub_counts[i]) if i < len(st.session_state.sub_counts) else 0
                cnt = st.number_input(f"Subkriteria untuk {k_names[i]}", min_value=0, max_value=max_sub, value=default_sc, step=1, key=sc_key)
                sub_counts.append(int(cnt))

            st.markdown("---")
            default_n_alt = min(3, max_alt)
            n_alt = st.number_input("Jumlah Alternatif", min_value=1, max_value=max_alt, value=default_n_alt, step=1, key="form_n_alt")
            st.subheader("Nama Alternatif")
            alt_names = []
            for j in range(int(n_alt)):
                an_key = f"input_altname_{j}"
                default_an = st.session_state.alt_names[j] if j < len(st.session_state.alt_names) else f"A{j+1}"
                an = st.text_input(f"Alternatif {j+1}", value=default_an, key=an_key)
                an = an.strip() if an.strip() else f"A{j+1}"
                alt_names.append(an)

            submit_struct = st.form_submit_button("Simpan Struktur")
        if submit_struct:
            # Save
            st.session_state.structure_done = True
            # truncate or assign new lists
            st.session_state.k_names = k_names[:max_k]
            st.session_state.sub_counts = [int(x) for x in sub_counts[:max_k]]
            st.session_state.alt_names = alt_names[:max_alt]
            # remove derived keys to avoid stale data
            for key in ['M_k','pr_k','global_sub','alt_under','alt_prior']:
                if key in st.session_state:
                    del st.session_state[key]
            st.success("Struktur tersimpan dan dikunci. Gunakan Reset bila ingin ubah.")
            st.rerun()
    else:
        st.success("Struktur sudah tersimpan dan dikunci.")
        st.write("Kriteria:", st.session_state.k_names)
        st.write("Sub counts:", st.session_state.sub_counts)
        st.write("Alternatif:", st.session_state.alt_names)
        st.info("Tekan Reset jika ingin mengubah struktur.")

# ----------------------------
# Utility: pairwise builder UI (used for Kriteria/Subkriteria/Alternatif)
# ----------------------------
def build_pairwise_for_labels(labels, prefix, caption=None):
    """
    Build UI for pairwise comparisons between items in labels.
    - labels: list of strings (names)
    - prefix: key prefix to produce unique keys
    Returns: dict pairs {(i,j): numeric_value}
    """
    n = len(labels)
    pairs = {}
    if n <= 1:
        return pairs
    if caption:
        st.caption(caption)
    for i in range(n):
        for j in range(i+1, n):
            A = labels[i]
            B = labels[j]
            key = f"{prefix}_{i}_{j}"
            key = sanitize_key(key)
            default = st.session_state.get(key, "1")
            sel = st.select_slider(
                label=f"{A} vs {B}",
                options=SLIDER_OPTIONS,
                value=default,
                key=key,
                format_func=make_label_formatter(A, B)
            )
            # map numeric
            pairs[(i, j)] = SLMAP[sel]
    return pairs

# ----------------------------
# Tab: Kriteria
# ----------------------------
with tabs[1]:
    st.header("2. Perbandingan Kriteria")
    if not st.session_state.structure_done:
        st.warning("Lengkapi struktur di tab Struktur terlebih dahulu.")
    else:
        k = st.session_state.k_names
        n = len(k)
        st.info("Gunakan slider untuk memilih arah dan intensitas kepentingan (A vs B).")
        pairs = build_pairwise_for_labels(k, prefix="crit")
        # compute
        if len(k) >= 2:
            M = pairwise_to_matrix(pairs, n)
            pr, _ = priority_from_matrix(M)
            lam, CI, CR = consistency_ratio(M, pr)

            st.subheader("Matriks Perbandingan Kriteria")
            st.dataframe(df_from_matrix(M, k))

            st.subheader("Bobot Kriteria")
            dfp = pd.DataFrame({"Kriteria": k, "Bobot": pr, "Bobot %": pr * 100})
            st.dataframe(dfp)

            fig = px.imshow(M, x=k, y=k, text_auto=True, color_continuous_scale='RdBu_r', origin='lower')
            fig.update_layout(height=420, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig, use_container_width=True)

            if CR < 0.1:
                st.success(f"Konsistensi OK — λmax={lam:.4f}, CI={CI:.4f}, CR={CR:.4f}")
            else:
                st.warning(f"Konsistensi TIDAK OK — λmax={lam:.4f}, CI={CI:.4f}, CR={CR:.4f}")

            # save
            st.session_state.M_k = M
            st.session_state.pr_k = pr
        else:
            st.info("Tambahkan minimal 2 kriteria di tab Struktur.")

# ----------------------------
# Tab: Subkriteria
# ----------------------------
with tabs[2]:
    st.header("3. Subkriteria per Kriteria")
    if not st.session_state.structure_done:
        st.warning("Lengkapi struktur di tab Struktur terlebih dahulu.")
    else:
        k = st.session_state.k_names
        sub_counts = st.session_state.sub_counts
        pr_k = st.session_state.pr_k if 'pr_k' in st.session_state else None

        global_sub = {}
        alt_list = []

        for idx, cnt in enumerate(sub_counts):
            kname = k[idx]
            st.subheader(f"Kriteria: {kname}")
            if cnt <= 0:
                st.info(f"{kname} tidak memiliki subkriteria — dipakai langsung sebagai item.")
                global_sub[kname] = (pr_k[idx] if pr_k is not None else None)
                alt_list.append(kname)
                continue

            # names for subkriteria
            subs = []
            for s in range(cnt):
                nm_key = sanitize_key(f"subname_{idx}_{s}")
                default_nm = st.session_state.get(nm_key, f"{kname}_sub{s+1}")
                nm = st.text_input(f"Nama subkriteria {s+1} untuk {kname}", value=default_nm, key=nm_key)
                nm = nm.strip() if nm.strip() else f"{kname}_sub{s+1}"
                subs.append(nm)
                # do NOT write st.session_state[nm_key] = nm  (widget already sets it)

            # pairwise for this sub-list
            if len(subs) >= 2:
                pairs_s = build_pairwise_for_labels(subs, prefix=f"sub_{idx}")
                M_s = pairwise_to_matrix(pairs_s, len(subs))
                pr_s, _ = priority_from_matrix(M_s)
                lam_s, CI_s, CR_s = consistency_ratio(M_s, pr_s)

                st.write("Matriks Subkriteria:")
                st.dataframe(df_from_matrix(M_s, subs))
                st.dataframe(pd.DataFrame({"Subkriteria": subs, "Bobot": pr_s, "Bobot %": pr_s * 100}))

                fig_s = px.imshow(M_s, x=subs, y=subs, text_auto=True, color_continuous_scale='RdBu_r', origin='lower')
                fig_s.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_s, use_container_width=True)

                if CR_s < 0.1:
                    st.success(f"Subkriteria konsisten — CR={CR_s:.4f}")
                else:
                    st.warning(f"Subkriteria TIDAK konsisten — CR={CR_s:.4f}")

                for sname, w in zip(subs, pr_s):
                    global_sub[sname] = (pr_k[idx] * w) if pr_k is not None else None
                    alt_list.append(sname)
            else:
                # if only one sub, weight = k weight
                if len(subs) == 1:
                    single = subs[0]
                    global_sub[single] = (pr_k[idx] if pr_k is not None else None)
                    alt_list.append(single)
                else:
                    st.info("Belum ada subkriteria untuk kriteria ini.")

        st.session_state.global_sub = global_sub
        st.session_state.alt_under = alt_list

# ----------------------------
# Tab: Alternatif
# ----------------------------
with tabs[3]:
    st.header("4. Perbandingan Alternatif per Item (subkriteria / kriteria tanpa sub)")
    if not st.session_state.structure_done:
        st.warning("Lengkapi struktur di tab Struktur terlebih dahulu.")
    else:
        alt = st.session_state.alt_names
        items = st.session_state.alt_under if 'alt_under' in st.session_state else []
        alt_prior = {}

        if not items:
            st.info("Belum ada item (subkriteria / kriteria) — periksa tab Subkriteria.")
        else:
            if len(alt) < 2:
                st.warning("Perbandingan alternatif membutuhkan minimal 2 alternatif.")
            else:
                for item in items:
                    st.subheader(f"Item: {item}")
                    # prefix uses sanitized item to avoid weird keys
                    prefix = f"alt_{sanitize_key(item)}"
                    pairs_a = build_pairwise_for_labels(alt, prefix=prefix)
                    if pairs_a:
                        M_a = pairwise_to_matrix(pairs_a, len(alt))
                        pr_a, _ = priority_from_matrix(M_a)
                        lam_a, CI_a, CR_a = consistency_ratio(M_a, pr_a)

                        st.dataframe(pd.DataFrame({"Alternatif": alt, "Bobot": pr_a, "Bobot %": pr_a * 100}))
                        if CR_a < 0.1:
                            st.success(f"Matrix alternatif konsisten — CR={CR_a:.4f}")
                        else:
                            st.warning(f"Matrix alternatif tidak konsisten — CR={CR_a:.4f}")

                        alt_prior[item] = pr_a
                    else:
                        st.info("Belum ada input perbandingan untuk alternatif pada item ini.")

        st.session_state.alt_prior = alt_prior

# ----------------------------
# Tab: Hasil & Export
# ----------------------------
with tabs[4]:
    st.header("5. Hasil Akhir & Export")
    if not st.session_state.structure_done:
        st.warning("Lengkapi struktur di tab Struktur terlebih dahulu.")
    else:
        global_sub = st.session_state.global_sub if 'global_sub' in st.session_state else {}
        df_gl = pd.DataFrame(list(global_sub.items()), columns=["Item", "GlobalWeight"]) if global_sub else pd.DataFrame()
        if not df_gl.empty:
            df_gl = df_gl.sort_values('GlobalWeight', ascending=False).reset_index(drop=True)
            st.subheader("Bobot Global (subkriteria / item)")
            st.dataframe(df_gl)

            figb = px.bar(df_gl, x='Item', y='GlobalWeight', title='Bobot Global per Item')
            st.plotly_chart(figb, use_container_width=True)

        alt = st.session_state.alt_names
        m = len(alt)
        final_scores = np.zeros(m)
        if 'alt_prior' in st.session_state and global_sub:
            for item, gw in global_sub.items():
                vec = st.session_state.alt_prior.get(item)
                if vec is None:
                    continue
                final_scores += gw * vec

            if final_scores.sum() > 0:
                dff = pd.DataFrame({"Alternatif": alt, "Skor": final_scores})
                dff['Skor %'] = dff['Skor'] / dff['Skor'].sum() * 100
                dff = dff.sort_values('Skor', ascending=False).reset_index(drop=True)
                st.subheader("Ranking Alternatif")
                st.dataframe(dff)

                figp = px.pie(dff, names='Alternatif', values='Skor %', title='Distribusi Skor Alternatif')
                st.plotly_chart(figp, use_container_width=True)

                # prepare export (include per-item alt priorities)
                to_export = {"GlobalWeights": df_gl, "FinalRanking": dff}
                for item, vec in st.session_state.alt_prior.items():
                    to_export[f"AltUnder_{sanitize_key(item)}"] = pd.DataFrame({"Alternatif": alt, "Priority": vec})

                st.download_button("Unduh Hasil (.xlsx)", data=to_excel_bytes(to_export), file_name='AHP_results_refactored.xlsx')
            else:
                st.info("Skor akhir belum bisa dihitung — pastikan semua perbandingan alternatif diisi.")
        else:
            st.info("Lengkapi perbandingan untuk subkriteria dan alternatif terlebih dahulu.")

# ----------------------------
# End of File
# ----------------------------
