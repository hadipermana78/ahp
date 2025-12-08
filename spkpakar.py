# app_ahp_multiuser_final.py
"""
Streamlit AHP Multi-User — Final (Part 1/3)

Fitur:
- Multi-user (register/login) dengan SQLite + PBKDF2 hashing
- Penyimpanan hasil AHP per pakar
- Export Excel via openpyxl (tanpa pd.ExcelWriter)
- PDF generation via reportlab
- Fungsi AHP: build matrix, geometric mean weights, CI/CR
- Data kriteria & sub-kriteria lengkap

Cara menjalankan:
pip install streamlit pandas numpy openpyxl reportlab
streamlit run app_ahp_multiuser_final.py
"""

import streamlit as st
import sqlite3
import json
import itertools
import numpy as np
import pandas as pd
from io import BytesIO
from datetime import datetime
import hashlib
import os

# PDF & Excel libraries
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
except Exception:
    # If reportlab unavailable, PDF features will raise at runtime; user can install later
    canvas = None
    A4 = None
    mm = None

from openpyxl import Workbook

# ------------------------------
# Utility: Excel writer (openpyxl, no ExcelWriter)
# ------------------------------
def to_excel_bytes(df_dict):
    """
    df_dict = {"SheetName": dataframe, ...}
    Return BytesIO Excel file using openpyxl (no pandas.ExcelWriter)
    """
    wb = Workbook()
    # remove default sheet
    default = wb.active
    wb.remove(default)

    for sheet_name, df in df_dict.items():
        # ensure DataFrame
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)
        ws = wb.create_sheet(sheet_name[:31])
        # write header
        ws.append(list(df.columns))
        # write rows
        for row in df.itertuples(index=False, name=None):
            ws.append(list(row))

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output

# ------------------------------
# Config / Data
# ------------------------------
DB_PATH = "ahp_users.db"

CRITERIA = [
    "A. Penataan Area Drop-off, Pick-up, dan Manajemen Moda",
    "B. Penataan Sirkulasi Kendaraan dan Pengendalian Kemacetan",
    "C. Keamanan dan Keselamatan Ruang Publik",
    "D. Kenyamanan Ruang Publik dan Lingkungan",
    "E. Kebersihan dan Pemeliharaan Fasilitas",
    "F. Aksesibilitas dan Konektivitas",
    "G. Aktivitas dan Fasilitas Pendukung"
]

SUBCRITERIA = {
    "A. Penataan Area Drop-off, Pick-up, dan Manajemen Moda": [
        "A1. Sediakan zona drop-off/pick-up resmi yang tertata",
        "A2. Bangun zona khusus drop-off untuk ojek online",
        "A3. Sediakan ruang drop-off terpisah untuk taksi dan mobil pribadi",
        "A4. Perbesar kapasitas ruang drop-off sesuai volume kendaraan",
        "A5. Pisahkan zona antarmoda secara tegas",
        "A6. Sediakan tempat mangkal resmi untuk ojek online dan ojek pangkalan",
        "A7. Tata alur sirkulasi kendaraan dengan pola yang terarah",
        "A8. Integrasikan manajemen transit dalam satu sistem zonasi",
        "A9. Kendalikan aktivitas moda pada jam sibuk",
        "A10. Sediakan area parkir resmi yang teratur dan mudah diakses"
    ],
    "B. Penataan Sirkulasi Kendaraan dan Pengendalian Kemacetan": [
        "B1. Susun sirkulasi kendaraan agar tidak bergantung pada satu koridor",
        "B2. Hilangkan titik parkir liar melalui desain fisik dan pengawasan",
        "B3. Tambahkan kapasitas sirkulasi untuk moda kecil dan ojol",
        "B4. Atur perilaku lalu lintas melalui desain preventif",
        "B5. Pisahkan jalur kendaraan dari area pejalan kaki"
    ],
    "C. Keamanan dan Keselamatan Ruang Publik": [
        "C1. Sediakan titik penyeberangan aman dan terlindungi",
        "C2. Kurangi titik konflik kendaraan–pejalan kaki melalui pemisahan fisik",
        "C3. Sediakan penerangan merata di seluruh koridor",
        "C4. Tingkatkan keamanan dengan CCTV, patroli, dan desain yang aktif"
    ],
    "D. Kenyamanan Ruang Publik dan Lingkungan": [
        "D1. Sediakan area teduh dan pelindung cuaca pada jalur pejalan kaki",
        "D2. Tambahkan ruang terbuka hijau dan vegetasi",
        "D3. Lebarkan area pejalan kaki agar terasa lapang",
        "D4. Sediakan tempat duduk di titik beristirahat strategis",
        "D5. Bangun ruang tunggu yang luas, teduh, dan nyaman",
        "D6. Tingkatkan kualitas estetika kawasan",
        "D7. Kendalikan kebisingan melalui buffer fisik atau vegetasi"
    ],
    "E. Kebersihan dan Pemeliharaan Fasilitas": [
        "E1. Tingkatkan standar kebersihan toilet, lantai, dan fasilitas dasar",
        "E2. Sediakan sistem pengelolaan sampah yang memadai",
        "E3. Lakukan pemeliharaan fasilitas secara berkala"
    ],
    "F. Aksesibilitas dan Konektivitas": [
        "F1. Sediakan jalur akses yang dekat dan tidak melelahkan",
        "F2. Bangun ramp dan fasilitas akses ramah difabel",
        "F3. Pastikan eskalator dan lift berfungsi baik setiap saat",
        "F4. Tingkatkan konektivitas antarmoda melalui jalur direct link",
        "F5. Sediakan jalur pejalan kaki yang aman, rata, dan tidak licin",
        "F6. Sediakan parkir sepeda yang aman dan memadai"
    ],
    "G. Aktivitas dan Fasilitas Pendukung": [
        "G1. Sediakan fasilitas komersial dasar yang mudah dijangkau",
        "G2. Sediakan fasilitas makan dan minum yang layak dan terjangkau",
        "G3. Sediakan ruang istirahat dan fasilitas transit yang memadai",
        "G4. Tata zona aktivitas agar tidak mengganggu sirkulasi utama",
        "G5. Sediakan sistem informasi dan signage yang jelas dan konsisten"
    ]
}

# Random Index (Saat n <= 10)
RI_DICT = {1:0.0,2:0.0,3:0.58,4:0.90,5:1.12,6:1.24,7:1.32,8:1.41,9:1.45,10:1.49}

# ------------------------------
# Database helpers
# ------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            pw_salt TEXT,
            pw_hash TEXT,
            is_admin INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT,
            main_pairs TEXT,
            sub_pairs TEXT,
            result_json TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    return conn

def delete_submission(submission_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
    conn.commit()
    conn.close()

# ------------------------------
# Auth helpers (PBKDF2)
# ------------------------------
def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    else:
        salt = bytes.fromhex(salt)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200000)
    return salt.hex(), dk.hex()

def verify_password(password, salt_hex, hash_hex):
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200000)
    return dk.hex() == hash_hex

# ------------------------------
# AHP core functions
# ------------------------------
def build_matrix_from_pairs(items, pair_values):
    """
    pair_values: dict with keys (a,b) -> numeric where a/b = value (if key order is (a,b))
    returns NxN numpy matrix
    """
    n = len(items)
    M = np.ones((n, n), dtype=float)
    idx = {it: i for i, it in enumerate(items)}
    for (a, b), val in pair_values.items():
        if a not in idx or b not in idx:
            continue
        i = idx[a]; j = idx[b]
        M[i, j] = float(val)
        if val != 0:
            M[j, i] = 1.0 / float(val)
    return M

def geometric_mean_weights(mat):
    # geometric mean of rows, then normalize
    n = mat.shape[0]
    gm = np.prod(mat, axis=1) ** (1.0 / n)
    w = gm / gm.sum()
    return w

def consistency_metrics(mat, weights):
    n = mat.shape[0]
    Aw = mat.dot(weights)
    # lambda_max approximation:
    lambda_max = float(np.mean(Aw / weights))
    CI = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    RI = RI_DICT.get(n, 1.49)
    CR = CI / RI if RI != 0 else 0.0
    return {"lambda_max": lambda_max, "CI": CI, "CR": CR}

# ------------------------------
# PDF generation (reportlab)
# ------------------------------
def generate_pdf_bytes(submission_row):
    """
    submission_row: dict with keys:
      - username
      - timestamp
      - result: { main: {keys, weights, cons}, local: {...}, global: [...] }
    returns BytesIO PDF
    """
    if canvas is None:
        raise RuntimeError("reportlab not installed. Install with `pip install reportlab` to enable PDF export.")

    bio = BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    width, height = A4
    margin = 18 * mm
    x = margin
    y = height - margin

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, "Laporan Hasil AHP — Penataan Ruang Publik")
    y -= 8 * mm
    c.setFont("Helvetica", 9)
    c.drawString(x, y, f"User / Group: {submission_row.get('username','')}")
    y -= 5 * mm
    c.drawString(x, y, f"Waktu: {submission_row.get('timestamp','')}")
    y -= 8 * mm

    res = submission_row.get("result", {})

    # Main weights
    main = res.get("main", {})
    keys = main.get("keys", [])
    weights = main.get("weights", [])
    cons = main.get("cons", {})

    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Bobot Kriteria Utama:")
    y -= 6 * mm
    c.setFont("Helvetica", 9)

    for k, w in zip(keys, weights):
        if y < margin + 30 * mm:
            c.showPage()
            y = height - margin
        c.drawString(x + 2 * mm, y, f"{k} — {w:.4f}")
        y -= 5 * mm

    # Global weights top items
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Bobot Global (Top):")
    y -= 6 * mm
    c.setFont("Helvetica", 9)

    gw = pd.DataFrame(res.get("global", []))
    if not gw.empty:
        gw_sorted = gw.sort_values("GlobalWeight", ascending=False).head(20)
        for _, row in gw_sorted.iterrows():
            if y < margin + 20 * mm:
                c.showPage()
                y = height - margin
            text = f"{row.get('SubKriteria','')} ({row.get('Kriteria','')}) — {row.get('GlobalWeight',0):.6f}"
            c.drawString(x + 2 * mm, y, text if len(text) < 120 else text[:117] + "...")
            y -= 5 * mm

    # Consistency summary
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Ringkasan Konsistensi (CI / CR):")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawString(x + 2 * mm, y, f"Kriteria Utama — CI: {cons.get('CI',0):.4f} , CR: {cons.get('CR',0):.4f}")
    y -= 6 * mm

    # highlight groups with CR > 0.1
    local = res.get("local", {})
    for grp, info in local.items():
        grp_cons = info.get("cons", {})
        if grp_cons.get("CR", 0) > 0.1:
            if y < margin + 15 * mm:
                c.showPage()
                y = height - margin
            c.drawString(x + 2 * mm, y, f"Perhatian: CR>0.1 pada {grp} (CR={grp_cons.get('CR'):.3f})")
            y -= 5 * mm

    c.showPage()
    c.save()
    bio.seek(0)
    return bio

# ------------------------------
# Initialize DB connection
# ------------------------------
conn = init_db()
cur = conn.cursor()

# End of Part 1 (imports, utils, AHP core, DB init)
# --- Lanjutkan ke Part 2: authentication, routing, pages (minta "lanjutkan bagian 2")
# ------------------------------
# Part 2/3 — Authentication, Routing, Kuesioner & My Submissions
# ------------------------------

st.set_page_config(page_title="AHP Multi-User", layout="wide")

# ------------------------------
# Authentication UI & helpers
# ------------------------------
st.sidebar.title("Akses Aplikasi")
auth_mode = st.sidebar.selectbox("Mode", ["Login", "Register", "Logout"])

# Ensure session state
if 'user' not in st.session_state:
    st.session_state['user'] = None

def register_user(username, password, is_admin=0):
    if not username or not password:
        return False, "Username dan password wajib diisi."
    salt, pw_hash = hash_password(password)
    try:
        cur.execute("INSERT INTO users (username, pw_salt, pw_hash, is_admin) VALUES (?,?,?,?)",
                    (username, salt, pw_hash, is_admin))
        conn.commit()
        return True, "Registrasi berhasil. Silakan login."
    except sqlite3.IntegrityError:
        return False, "Username sudah terdaftar."

def authenticate_user(username, password):
    cur.execute("SELECT id, pw_salt, pw_hash, is_admin FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if not row:
        return False, "User tidak ditemukan."
    uid, salt, phash, is_admin = row
    if verify_password(password, salt, phash):
        return True, {"id": uid, "username": username, "is_admin": bool(is_admin)}
    return False, "Password salah."

# Auth widgets
if auth_mode == "Register":
    st.sidebar.subheader("Daftar Pengguna Baru")
    new_user = st.sidebar.text_input("Username (daftar)", key="reg_user")
    new_pw = st.sidebar.text_input("Password (daftar)", type="password", key="reg_pw")
    admin_check = st.sidebar.checkbox("Daftarkan sebagai admin", key="reg_admin")
    if st.sidebar.button("Daftar", key="btn_register"):
        ok, msg = register_user(new_user, new_pw, 1 if admin_check else 0)
        if ok:
            st.sidebar.success(msg)
        else:
            st.sidebar.error(msg)

elif auth_mode == "Login":
    st.sidebar.subheader("Masuk")
    login_user = st.sidebar.text_input("Username", key="login_user")
    login_pw = st.sidebar.text_input("Password", type="password", key="login_pw")
    if st.sidebar.button("Masuk", key="btn_login"):
        ok, info = authenticate_user(login_user, login_pw)
        if ok:
            st.session_state['user'] = info
            st.sidebar.success(f"Selamat datang, {info['username']}")
        else:
            st.sidebar.error(info)

else:  # Logout
    if st.sidebar.button("Logout", key="btn_logout"):
        st.session_state['user'] = None
        st.sidebar.info("Anda telah logout.")

# If not logged in, show landing and stop
if not st.session_state['user']:
    st.title("Aplikasi Kuesioner AHP — Multi-user")
    st.write("Silakan login atau daftar melalui panel kiri (sidebar).")
    st.write("Setelah login, Anda dapat mengisi kuesioner AHP atau melihat hasil.")
    st.stop()

# current user
user = st.session_state['user']
st.sidebar.markdown(f"**User:** {user['username']}  {'(admin)' if user['is_admin'] else ''}")

# ------------------------------
# Page selector (routing)
# ------------------------------
if user['is_admin']:
    page = st.sidebar.selectbox("Halaman", [
        "Isi Kuesioner",
        "My Submissions",
        "Hasil Akhir Penilaian",
        "Admin Panel",
        "Laporan Final Gabungan Pakar"
    ])
else:
    page = st.sidebar.selectbox("Halaman", [
        "Isi Kuesioner",
        "My Submissions",
        "Hasil Akhir Penilaian"
    ])

# ------------------------------
# Pairwise input helper (clean UI)
# ------------------------------
def _short_key(prefix, a, b):
    """Create a short stable key from pair and prefix"""
    h = hashlib.sha1((prefix + "::" + a + "|||" + b).encode("utf-8")).hexdigest()
    return h[:12]

def pairwise_inputs(items, key_prefix):
    """
    Render pairwise inputs for items.
    Returns dict with keys (a,b) -> float such that matrix[i,j] = value (a over b)
    """
    pairs = list(itertools.combinations(items, 2))
    out = {}
    for (a, b) in pairs:
        # layout columns
        col_l, col_mid, col_r, col_scale = st.columns([6, 1, 6, 2])
        col_l.markdown(f"<div style='white-space:normal'>{a}</div>", unsafe_allow_html=True)
        col_r.markdown(f"<div style='white-space:normal'>{b}</div>", unsafe_allow_html=True)
        kshort = _short_key(key_prefix, a, b)
        direction = col_mid.radio("", ["L", "R"], index=0, key=f"{kshort}_dir", horizontal=True, label_visibility="collapsed")
        val = col_scale.selectbox("", list(range(1, 10)), index=1, key=f"{kshort}_scale", label_visibility="collapsed")
        if direction == "L":
            out[(a, b)] = float(val)
        else:
            out[(a, b)] = float(1.0 / val)
    return out

# ------------------------------
# Page: Isi Kuesioner
# ------------------------------
if page == "Isi Kuesioner":
    st.header("Isi Kuesioner AHP — Penataan Ruang Publik")
    st.write("Isi perbandingan berpasangan menggunakan skala 1–9. (1 = sama penting, 9 = mutlak lebih penting).")
    st.markdown("**1) Perbandingan Kriteria Utama (A–G)**")
    main_pairs = pairwise_inputs(CRITERIA, "MAIN")

    st.markdown("---")
    st.markdown("**2) Sub-Kriteria per Grup**")
    sub_pairs = {}
    for group in CRITERIA:
        st.markdown(f"##### {group}")
        sp = pairwise_inputs(SUBCRITERIA[group], key_prefix=group[:12].replace(" ", "_"))
        # store as strings for JSON (a ||| b)
        sub_pairs[group] = {f"{a} ||| {b}": v for (a, b), v in sp.items()}

    if st.button("Simpan hasil ke database"):
        # compute AHP per user submission
        main_mat = build_matrix_from_pairs(CRITERIA, main_pairs)
        main_w = geometric_mean_weights(main_mat)
        main_cons = consistency_metrics(main_mat, main_w)

        local = {}
        global_rows = []
        for i, group in enumerate(CRITERIA):
            # reconstruct pairs for group
            pairdict = {tuple(k.split(" ||| ")): v for k, v in sub_pairs[group].items()}
            mat = build_matrix_from_pairs(SUBCRITERIA[group], pairdict)
            w = geometric_mean_weights(mat)
            cons = consistency_metrics(mat, w)
            local[group] = {"keys": SUBCRITERIA[group], "weights": list(map(float, w)), "cons": cons}
            for sk, lw in zip(SUBCRITERIA[group], w):
                global_rows.append({
                    "Kriteria": group,
                    "SubKriteria": sk,
                    "LocalWeight": float(lw),
                    "MainWeight": float(main_w[i]),
                    "GlobalWeight": float(main_w[i] * lw)
                })

        result = {
            "main": {"keys": CRITERIA, "weights": list(map(float, main_w)), "cons": main_cons, "mat": main_mat.tolist()},
            "local": local,
            "global": global_rows
        }
        ts = datetime.now().isoformat()
        main_pairs_store = {f"{a} ||| {b}": v for (a, b), v in main_pairs.items()}
        cur.execute("INSERT INTO submissions (user_id, timestamp, main_pairs, sub_pairs, result_json) VALUES (?,?,?,?,?)",
                    (user['id'], ts, json.dumps(main_pairs_store), json.dumps(sub_pairs), json.dumps(result)))
        conn.commit()
        st.success("Hasil berhasil disimpan ke database.")
        st.experimental_rerun()

# ------------------------------
# Page: My Submissions
# ------------------------------
elif page == "My Submissions":
    st.header("Submission Saya")
    cur.execute("SELECT id, timestamp, result_json FROM submissions WHERE user_id = ? ORDER BY id DESC", (user['id'],))
    rows = cur.fetchall()
    if not rows:
        st.info("Belum ada submission.")
    else:
        for sid, ts, rjson in rows:
            st.subheader(f"Submission #{sid} — {ts}")
            res = json.loads(rjson)

            # show top 10 global
            dfg = pd.DataFrame(res['global']).sort_values("GlobalWeight", ascending=False).head(10)
            st.table(dfg)

            col1, col2 = st.columns(2)
            with col1:
                df_main = pd.DataFrame({"Kriteria": res['main']['keys'], "Weight": res['main']['weights']})
                df_global = pd.DataFrame(res['global']).sort_values("GlobalWeight", ascending=False)
                # prepare excel using our to_excel_bytes
                excel_out = to_excel_bytes({
                    "Kriteria_Utama": df_main,
                    "Global_Weights": df_global
                })
                st.download_button(f"Download Excel #{sid}", data=excel_out,
                                   file_name=f"submission_{sid}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key=f"ex_{sid}")

            with col2:
                # prepare PDF
                submission_row = {"id": sid, "username": user['username'], "timestamp": ts, "result": json.loads(rjson)}
                try:
                    pdf_bio = generate_pdf_bytes(submission_row)
                    st.download_button(f"Download PDF #{sid}", data=pdf_bio,
                                       file_name=f"submission_{sid}.pdf", mime="application/pdf", key=f"pdf_{sid}")
                except RuntimeError as e:
                    st.warning(str(e))

# End of Part 2
# Next: Part 3 includes Hasil Akhir Per Pakar, Admin Panel, Laporan Gabungan (minta "lanjutkan bagian 3")
# ------------------------------
# Part 3/3 — Hasil Per Pakar, Admin Panel, Laporan Gabungan
# ------------------------------

# ------------------------------
# Page: Hasil Akhir Per Pakar (individual)
# ------------------------------
elif page == "Hasil Akhir Penilaian":
    st.header("Hasil Akhir Penilaian Pakar (AHP)")

    # get latest submission of this user
    cur.execute("""
        SELECT id, timestamp, result_json
        FROM submissions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (user['id'],))
    row = cur.fetchone()
    if not row:
        st.info("Anda belum mengisi kuesioner AHP.")
        st.stop()

    sid, ts, rjson = row
    res = json.loads(rjson)

    st.subheader("1. Bobot Kriteria Utama")
    df_main = pd.DataFrame({"Kriteria": res['main']['keys'], "Bobot": res['main']['weights']})
    st.table(df_main)
    st.write("**CI = {:.4f}, CR = {:.4f}**".format(res['main']['cons'].get('CI', 0), res['main']['cons'].get('CR', 0)))

    st.markdown("---")
    st.subheader("2. Bobot Sub-Kriteria (Bobot Lokal per Grup)")
    for group_name, info in res.get("local", {}).items():
        st.markdown(f"#### {group_name}")
        df_local = pd.DataFrame({"Sub-Kriteria": info.get("keys", []), "Bobot Lokal": info.get("weights", [])})
        st.table(df_local)
        st.write("**CI = {:.4f}, CR = {:.4f}**".format(info.get("cons", {}).get("CI", 0), info.get("cons", {}).get("CR", 0)))

    st.markdown("---")
    st.subheader("3. Bobot Global (Ranking Semua Sub-Kriteria)")
    df_global = pd.DataFrame(res.get("global", [])).sort_values("GlobalWeight", ascending=False)
    st.table(df_global)

    st.subheader("Grafik Bobot Global (Top 20)")
    try:
        import altair as alt
        chart = alt.Chart(df_global.head(20)).mark_bar().encode(
            x='GlobalWeight:Q',
            y=alt.Y('SubKriteria:N', sort='-x')
        ).properties(height=500)
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.info("Altair tidak tersedia, grafik dilewati.")

    st.markdown("---")
    st.subheader("4. Download Laporan")

    submission_row = {"id": sid, "username": user['username'], "timestamp": ts, "result": res}
    # PDF (reportlab required)
    try:
        pdf_bio = generate_pdf_bytes(submission_row)
        st.download_button("📄 Download Laporan PDF", data=pdf_bio,
                           file_name=f"hasil_ahp_{sid}.pdf", mime="application/pdf")
    except RuntimeError as e:
        st.warning(str(e))

    # Excel using to_excel_bytes
    excel_bio = to_excel_bytes({
        "Kriteria_Utama": df_main,
        "Global_Weights": df_global
    })
    st.download_button("📊 Download Excel Hasil", data=excel_bio,
                       file_name=f"hasil_ahp_{sid}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ------------------------------
# Page: Admin Panel (admin-only)
# ------------------------------
elif page == "Admin Panel" and user["is_admin"]:
    st.header("📊 Admin Panel – Manajemen Submission Pakar")

    # fetch all submissions joined with user
    cur.execute("""
        SELECT s.id, u.username, s.timestamp, s.result_json
        FROM submissions s
        JOIN users u ON u.id = s.user_id
        ORDER BY s.id DESC
    """)
    all_rows = cur.fetchall()

    if not all_rows:
        st.info("Belum ada submission dari pakar.")
        st.stop()

    # Prepare summary table
    summary_rows = []
    for sid, username, ts, rjson in all_rows:
        res = json.loads(rjson)
        main_weights = res.get("main", {}).get("weights", [])
        cr_main = res.get("main", {}).get("cons", {}).get("CR", 0)
        summary_rows.append({
            "ID": sid,
            "User": username,
            "Timestamp": ts,
            "CR Utama": cr_main,
            "Bobot Kriteria (truncated)": ", ".join(f"{w:.3f}" for w in (main_weights[:7] if len(main_weights) >= 7 else main_weights))
        })

    df_summary = pd.DataFrame(summary_rows)
    st.dataframe(df_summary, use_container_width=True)

    st.markdown("---")

    # Delete submission
    st.subheader("🗑 Hapus Submission")
    del_id = st.number_input("Masukkan ID submission yang ingin dihapus", min_value=1, step=1)
    if st.button("Hapus Submission"):
        try:
            delete_submission(int(del_id))
            st.success(f"Submission #{del_id} telah dihapus.")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Gagal menghapus: {e}")

    st.markdown("---")
    # Export all data: create Excel with summary + per-submission sheets
    st.subheader("📥 Download Semua Data (Excel)")

    # Build excel dict for to_excel_bytes
    excel_sheets = {"Ringkasan_Admin": df_summary}
    for sid, username, ts, rjson in all_rows:
        res = json.loads(rjson)
        df_main = pd.DataFrame({"Kriteria": res.get("main", {}).get("keys", []),
                                "Bobot": res.get("main", {}).get("weights", [])})
        df_global = pd.DataFrame(res.get("global", [])).sort_values("GlobalWeight", ascending=False)
        excel_sheets[f"Main_{sid}"] = df_main
        excel_sheets[f"Global_{sid}"] = df_global

    excel_all = to_excel_bytes(excel_sheets)
    st.download_button("📊 Download Semua Data (Excel)", data=excel_all,
                       file_name="all_submissions.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ------------------------------
# Page: Laporan Final Gabungan Pakar (admin-only)
# ------------------------------
elif page == "Laporan Final Gabungan Pakar" and user["is_admin"]:
    st.header("📘 Laporan Final Gabungan Antar Pakar (AHP)")

    # get latest submission per user (so each user contributes once - latest)
    cur.execute("""
        SELECT u.username, s.result_json, s.main_pairs
        FROM users u
        JOIN (
            SELECT user_id, MAX(id) AS max_id
            FROM submissions
            GROUP BY user_id
        ) latest ON latest.user_id = u.id
        JOIN submissions s ON s.id = latest.max_id
        ORDER BY u.username
    """)
    experts = cur.fetchall()

    if not experts:
        st.warning("Belum ada pakar yang mengisi kuesioner.")
        st.stop()

    st.success(f"Ditemukan {len(experts)} pakar (menggunakan submission terbaru tiap pakar).")

    # 1) AIJ — aggregate pairwise matrices (main criteria)
    all_main_matrices = []
    for username, rjson, main_pairs_json in experts:
        res = json.loads(rjson)
        # main_pairs_json stored as {"A ||| B": val, ...}
        mp = {}
        try:
            mp = json.loads(main_pairs_json) if isinstance(main_pairs_json, str) else main_pairs_json
        except Exception:
            mp = {}
        pair_values = {}
        for k, v in (mp.items() if isinstance(mp, dict) else []):
            try:
                a, b = [s.strip() for s in k.split("|||")]
                pair_values[(a, b)] = float(v)
            except Exception:
                continue
        M = build_matrix_from_pairs(CRITERIA, pair_values)
        all_main_matrices.append(M)

    # element-wise geometric mean of matrices
    GM = np.exp(np.mean([np.log(m) for m in all_main_matrices], axis=0))
    weights_aij = geometric_mean_weights(GM)
    cons_aij = consistency_metrics(GM, weights_aij)

    df_aij = pd.DataFrame({"Kriteria": CRITERIA, "Bobot_AI J": weights_aij})
    st.subheader("1) Bobot Gabungan Kriteria Utama (AIJ)")
    st.table(df_aij)
    st.write(f"CI = {cons_aij['CI']:.4f}, CR = {cons_aij['CR']:.4f}")

    # 2) AIP — aggregate individual priorities
    all_w = []
    for username, rjson, _ in experts:
        res = json.loads(rjson)
        all_w.append(np.array(res.get("main", {}).get("weights", [])))
    all_w = np.vstack(all_w)
    w_aip = np.exp(np.mean(np.log(all_w), axis=0))
    w_aip = w_aip / w_aip.sum()
    df_aip = pd.DataFrame({"Kriteria": CRITERIA, "Bobot_AIP": w_aip})
    st.subheader("2) Bobot Gabungan Kriteria Utama (AIP)")
    st.table(df_aip)

    # 3) Combine sub-criteria: geometric mean of local weights per group
    local_combined = {}
    global_rows = []
    for group in CRITERIA:
        collects = []
        for username, rjson, _ in experts:
            res = json.loads(rjson)
            lw = res.get("local", {}).get(group, {}).get("weights", [])
            collects.append(np.array(lw))
        collects = np.vstack(collects)
        gm_loc = np.exp(np.mean(np.log(collects), axis=0))
        gm_loc = gm_loc / gm_loc.sum()
        local_combined[group] = gm_loc
        main_idx = CRITERIA.index(group)
        for sk, lw in zip(SUBCRITERIA[group], gm_loc):
            gw = lw * weights_aij[main_idx]
            global_rows.append({
                "Kriteria": group,
                "SubKriteria": sk,
                "LocalWeight": float(lw),
                "MainWeight": float(weights_aij[main_idx]),
                "GlobalWeight": float(gw)
            })

    df_global = pd.DataFrame(global_rows).sort_values("GlobalWeight", ascending=False)

    st.subheader("3) Bobot Global Gabungan Sub-Kriteria")
    st.table(df_global)

    # Chart
    try:
        import altair as alt
        chart = alt.Chart(df_global.head(20)).mark_bar().encode(
            x='GlobalWeight:Q',
            y=alt.Y('SubKriteria:N', sort='-x')
        ).properties(height=500)
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.info("Altair tidak tersedia, grafik dilewati.")

    # Downloads: Excel & PDF
    excel_bio = to_excel_bytes({
        "AIJ_Kriteria": pd.DataFrame({"Kriteria": CRITERIA, "Bobot_AI J": weights_aij}),
        "AIP_Kriteria": pd.DataFrame({"Kriteria": CRITERIA, "Bobot_AIP": w_aip}),
        "Global_Combined": df_global
    })
    st.download_button("📥 Download Excel Gabungan", data=excel_bio,
                       file_name="AHP_Gabungan_Pakar.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # PDF payload and download
    payload = {
        "username": "GABUNGAN PAKAR",
        "timestamp": datetime.now().isoformat(),
        "result": {
            "main": {"keys": CRITERIA, "weights": list(map(float, weights_aij)), "cons": cons_aij},
            "global": df_global.to_dict(orient="records")
        }
    }
    try:
        pdf_bio = generate_pdf_bytes(payload)
        st.download_button("📄 Download PDF Gabungan", data=pdf_bio,
                           file_name="AHP_Gabungan_Pakar.pdf", mime="application/pdf")
    except RuntimeError as e:
        st.warning(str(e))

# End of Part 3 (file complete)
