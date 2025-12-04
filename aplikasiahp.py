# app_multi_user_pdf.py
"""
Streamlit AHP multi-user + PDF report app.

Dependencies:
pip install streamlit pandas numpy openpyxl reportlab
Run:
streamlit run app_multi_user_pdf.py
"""
import streamlit as st
import sqlite3
import json
import itertools
import numpy as np
import pandas as pd
from io import BytesIO
from datetime import datetime
import hashlib, os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from openpyxl import Workbook

def to_excel_bytes(df_dict):
    """
    df_dict = {
        "Sheet1": df1,
        "Sheet2": df2,
        ...
    }
    Return BytesIO Excel
    """
    wb = Workbook()
    default_sheet = wb.active
    wb.remove(default_sheet)

    for sheet_name, df in df_dict.items():
        ws = wb.create_sheet(sheet_name[:31])
        ws.append(list(df.columns))
        for row in df.to_numpy().tolist():
            ws.append(row)

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

RI_DICT = {1:0.0,2:0.0,3:0.58,4:0.90,5:1.12,6:1.24,7:1.32,8:1.41,9:1.45,10:1.49}

# ------------------------------
# Database helpers
# ------------------------------
def delete_submission(submission_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
    conn.commit()
    conn.close()

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
# AHP functions
# ------------------------------
def build_matrix_from_pairs(items, pair_values):
    n = len(items)
    M = np.ones((n,n))
    idx = {it:i for i,it in enumerate(items)}
    for (a,b), val in pair_values.items():
        i = idx[a]; j = idx[b]
        M[i,j] = float(val)
        M[j,i] = 1.0/float(val)
    return M

def geometric_mean_weights(mat):
    n = mat.shape[0]
    gm = np.prod(mat, axis=1) ** (1.0/n)
    w = gm / np.sum(gm)
    return w

def consistency_metrics(mat, weights):
    n = mat.shape[0]
    Aw = mat.dot(weights)
    lambda_max = np.mean(Aw / weights)
    CI = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    RI = RI_DICT.get(n, 1.49)
    CR = CI / RI if RI != 0 else 0.0
    return {"lambda_max": float(lambda_max), "CI": float(CI), "CR": float(CR)}

# ------------------------------
# PDF generation
# ------------------------------
def generate_pdf_bytes(submission_row):
    bio = BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    x = margin; y = height - margin

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, "Laporan Hasil AHP — Penataan Ruang Publik")
    y -= 10*mm
    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"User: {submission_row.get('username', '')}")
    y -= 5*mm
    c.drawString(x, y, f"Waktu: {submission_row.get('timestamp', '')}")
    y -= 8*mm

    # Main criteria weights table (small)
    res = submission_row['result']
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Bobot Kriteria Utama:")
    y -= 6*mm
    c.setFont("Helvetica", 9)
    main_df = pd.DataFrame(res['main']['weights'], index=res['main']['keys'], columns=["Weight"])
    for k, row in main_df.iterrows():
        if y < margin + 30*mm:
            c.showPage(); y = height - margin
        c.drawString(x+2*mm, y, f"{k} : {row['Weight']:.4f}")
        y -= 5*mm

    y -= 4*mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Bobot Global (top items):")
    y -= 6*mm
    c.setFont("Helvetica", 9)
    gw = pd.DataFrame(res['global']).sort_values('GlobalWeight', ascending=False).head(20)
    for idx, r in gw.iterrows():
        if y < margin + 20*mm:
            c.showPage(); y = height - margin
        text = f"{r['SubKriteria']} ({r.get('Kriteria','')}) — {r['GlobalWeight']:.6f}"
        c.drawString(x+2*mm, y, text if len(text) < 120 else text[:117] + "...")
        y -= 5*mm

    y -= 6*mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Ringkasan Konsistensi (CI / CR):")
    y -= 6*mm
    c.setFont("Helvetica", 9)
    main_cons = res['main']['cons']
    c.drawString(x+2*mm, y, f"Kriteria Utama — CI: {main_cons['CI']:.4f}, CR: {main_cons['CR']:.4f}")
    y -= 5*mm
    for grp, grpinfo in res.get('local', {}).items():
        if grpinfo['cons']['CR'] > 0.1:
            if y < margin + 20*mm:
                c.showPage(); y = height - margin
            c.drawString(x+2*mm, y, f"Perhatian: CR>0.1 pada {grp} (CR={grpinfo['cons']['CR']:.3f})")
            y -= 5*mm

    c.showPage()
    c.save()
    bio.seek(0)
    return bio

# ------------------------------
# App: auth and pages
# ------------------------------
conn = init_db()
cur = conn.cursor()

st.sidebar.title("Akses")
auth_mode = st.sidebar.selectbox("Mode", ["Login", "Register", "Logout"])
if 'user' not in st.session_state:
    st.session_state['user'] = None

def register_user(username, password, is_admin=0):
    salt, pw_hash = hash_password(password)
    try:
        cur.execute("INSERT INTO users (username, pw_salt, pw_hash, is_admin) VALUES (?,?,?,?)",
                    (username, salt, pw_hash, is_admin))
        conn.commit()
        return True, "Registrasi berhasil."
    except sqlite3.IntegrityError:
        return False, "Username sudah ada."

def authenticate_user(username, password):
    cur.execute("SELECT id, pw_salt, pw_hash, is_admin FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if not row:
        return False, "User tidak ditemukan."
    uid, salt, phash, is_admin = row
    if verify_password(password, salt, phash):
        return True, {"id":uid, "username":username, "is_admin":bool(is_admin)}
    return False, "Password salah."

if auth_mode == "Register":
    st.sidebar.subheader("Daftar pengguna baru")
    new_user = st.sidebar.text_input("Username reg")
    new_pw = st.sidebar.text_input("Password reg", type="password")
    admin_check = st.sidebar.checkbox("Daftarkan sebagai admin (hati-hati)")
    if st.sidebar.button("Daftar"):
        ok, msg = register_user(new_user, new_pw, 1 if admin_check else 0)
        st.sidebar.info(msg)

elif auth_mode == "Login":
    st.sidebar.subheader("Login")
    user = st.sidebar.text_input("Username")
    pw = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Masuk"):
        ok, info = authenticate_user(user, pw)
        if ok:
            st.session_state['user'] = info
            st.sidebar.success(f"Selamat datang, {info['username']}")
        else:
            st.sidebar.error(info)

else:
    if st.sidebar.button("Logout"):
        st.session_state['user'] = None
        st.sidebar.info("Anda telah logout.")

if not st.session_state['user']:
    st.title("Aplikasi Kuesioner AHP — Multi-user")
    st.write("Silakan login atau daftar melalui panel kiri (sidebar).")
    st.write("Setelah login, pengguna dapat mengisi kuesioner dan menyimpan hasil.")
    st.stop()

user = st.session_state['user']
st.sidebar.markdown(f"**User:** {user['username']}  {'(admin)' if user['is_admin'] else ''}")

# Page selector — <<< PERBAIKAN: tambahkan Laporan Final Gabungan Pakar
if user['is_admin']:
    page = st.sidebar.selectbox("Halaman", 
        ["Isi Kuesioner", "My Submissions", "Hasil Akhir Penilaian", "Admin Panel", "Laporan Final Gabungan Pakar"])
else:
    page = st.sidebar.selectbox("Halaman", 
        ["Isi Kuesioner", "My Submissions", "Hasil Akhir Penilaian"])

# ------------------------------
# NEW: improved pairwise_inputs (replaces older version)
# ------------------------------
def _short_key(prefix, a, b):
    """Buat key singkat unik untuk widget dari pasangan a/b."""
    h = hashlib.sha1((prefix + "::" + a + "|||" + b).encode("utf-8")).hexdigest()
    return h[:12]

def pairwise_inputs(items, key_prefix):
    """
    Versi layout rapi:
    - Tampilkan label panjang di kolom kiri dan kanan (boleh membungkus normal).
    - Tengah: radio singkat 'L' / 'R' (tidak akan di-wrap per huruf).
    - Kanan: selectbox 1..9 untuk skala.
    Mengembalikan dict dengan key (a,b) -> nilai (float).
    """
    pairs = list(itertools.combinations(items, 2))
    out = {}
    for (a, b) in pairs:
        # Proporsi: kiri besar, tengah kecil, kanan besar, paling kanan untuk skala
        col_left, col_choice, col_right, col_scale = st.columns([6, 1, 6, 2])

        # Tampilkan teks lengkap pada kolom kiri/kanan (word-wrap normal)
        col_left.markdown(f"<div style='white-space:normal'>{a}</div>", unsafe_allow_html=True)
        col_right.markdown(f"<div style='white-space:normal'>{b}</div>", unsafe_allow_html=True)

        # Buat key singkat unik
        kshort = _short_key(key_prefix, a, b)

        # Radio singkat untuk arah — 'L' artinya item kiri lebih penting; 'R' item kanan
        direction = col_choice.radio(
            label="",
            options=["L", "R"],
            index=0,
            key=f"{kshort}_dir",
            label_visibility="collapsed",
            horizontal=True
        )

        # Scale 1..9
        val = col_scale.selectbox(
            label="",
            options=list(range(1, 10)),
            index=0,
            key=f"{kshort}_scale",
            label_visibility="collapsed"
        )

        # Map result ke numeric sesuai arah
        if direction == "L":
            out[(a, b)] = float(val)
        else:
            out[(a, b)] = float(1.0 / val)

    return out

# ------------------------------
# Halaman: Isi Kuesioner
# ------------------------------
if page == "Isi Kuesioner":
    st.header("Isi Kuesioner AHP")
    st.write("Isi perbandingan berpasangan untuk kriteria utama lalu tiap sub-kriteria. Setelah selesai simpan ke database.")
    st.write("Skala 1–9 (1 = sama penting, 9 = mutlak lebih penting).")

    st.subheader("1) Perbandingan Kriteria Utama")
    main_pairs = pairwise_inputs(CRITERIA, "MAIN")

    st.markdown("---")
    sub_pairs = {}
    for group in CRITERIA:
        st.subheader(f"Sub-kriteria: {group}")
        sp = pairwise_inputs(SUBCRITERIA[group], key_prefix=group[:10].replace(" ","_"))
        sub_pairs[group] = {f"{a} ||| {b}": v for (a,b),v in sp.items()}

    if st.button("Simpan hasil ke database"):
        # compute results
        main_mat = build_matrix_from_pairs(CRITERIA, main_pairs)
        main_w = geometric_mean_weights(main_mat)
        main_cons = consistency_metrics(main_mat, main_w)
        local = {}
        global_rows = []
        for i, group in enumerate(CRITERIA):
            mat = build_matrix_from_pairs(SUBCRITERIA[group], {tuple(k.split(" ||| ")):v for k,v in sub_pairs[group].items()})
            w = geometric_mean_weights(mat)
            cons = consistency_metrics(mat, w)
            local[group] = {"keys": SUBCRITERIA[group], "weights": list(map(float,w)), "cons": cons}
            for sk, lw in zip(SUBCRITERIA[group], w):
                global_rows.append({"Kriteria": group, "SubKriteria": sk, "LocalWeight": float(lw), "MainWeight": float(main_w[i]), "GlobalWeight": float(main_w[i]*lw)})

        result = {
            "main": {"keys": CRITERIA, "weights": list(map(float,main_w)), "cons": main_cons, "mat": main_mat.tolist()},
            "local": local,
            "global": global_rows
        }
        ts = datetime.now().isoformat()
        main_pairs_store = {f"{a} ||| {b}": v for (a,b),v in main_pairs.items()}
        cur.execute("INSERT INTO submissions (user_id, timestamp, main_pairs, sub_pairs, result_json) VALUES (?,?,?,?,?)",
                    (user['id'], ts, json.dumps(main_pairs_store), json.dumps(sub_pairs), json.dumps(result)))
        conn.commit()
        st.success("Hasil berhasil disimpan.")
        st.rerun()

# ------------------------------
# Halaman: My Submissions
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
            dfg = pd.DataFrame(res['global']).sort_values("GlobalWeight", ascending=False).head(10)
            st.table(dfg)
            col1, col2 = st.columns(2)
            with col1:
                df_main = pd.DataFrame({"Kriteria": res['main']['keys'], "Weight": res['main']['weights']})
                df_global = pd.DataFrame(res['global']).sort_values("GlobalWeight", ascending=False)
                out = BytesIO()
                with pd.ExcelWriter(out, engine="openpyxl") as writer:
                    df_main.to_excel(writer, sheet_name="Kriteria_Utama", index=False)
                    df_global.to_excel(writer, sheet_name="Global_Weights", index=False)
                out.seek(0)
                st.download_button(f"Download Excel #{sid}", data=out, file_name=f"submission_{sid}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"ex_{sid}")
            with col2:
                cur.execute("SELECT s.id, u.username, s.timestamp, s.result_json FROM submissions s JOIN users u ON u.id = s.user_id WHERE s.id = ?", (sid,))
                r = cur.fetchone()
                sid2, username, timestamp, result_json = r
                submission_row = {"id": sid2, "username": username, "timestamp": timestamp, "result": json.loads(result_json)}
                pdf_bio = generate_pdf_bytes(submission_row)
                st.download_button(f"Download PDF #{sid}", data=pdf_bio, file_name=f"submission_{sid}.pdf", mime="application/pdf", key=f"pdf_{sid}")

# ------------------------------
# Halaman: Hasil Akhir Penilaian
# ------------------------------
elif page == "Hasil Akhir Penilaian":
    st.header("Hasil Akhir Penilaian Pakar (AHP)")
    cur.execute("""
        SELECT id, timestamp, result_json 
        FROM submissions 
        WHERE user_id = ? 
        ORDER BY id DESC LIMIT 1
    """, (user['id'],))
    row = cur.fetchone()

    if not row:
        st.info("Anda belum mengisi kuesioner AHP.")
        st.stop()

    sid, ts, rjson = row
    res = json.loads(rjson)

    st.subheader("1. Bobot Kriteria Utama")
    df_main = pd.DataFrame({
        "Kriteria": res['main']['keys'],
        "Bobot": res['main']['weights']
    })
    st.table(df_main)

    st.write("**CI = {:.4f}, CR = {:.4f}**".format(
        res['main']['cons']['CI'], 
        res['main']['cons']['CR']
    ))

    st.markdown("---")
    st.subheader("2. Bobot Sub-Kriteria (Bobot Lokal per Grup)")

    for group_name, info in res["local"].items():
        st.markdown(f"### {group_name}")
        df_local = pd.DataFrame({
            "Sub-Kriteria": info["keys"],
            "Bobot Lokal": info["weights"]
        })
        st.table(df_local)

        st.write("**CI = {:.4f}, CR = {:.4f}**".format(
            info['cons']['CI'], 
            info['cons']['CR']
        ))

    st.markdown("---")
    st.subheader("3. Bobot Global (Ranking Semua Sub-Kriteria)")
    df_global = pd.DataFrame(res["global"]).sort_values(
        "GlobalWeight", ascending=False
    )
    st.table(df_global)

    st.subheader("Grafik Bobot Global")
    try:
        import altair as alt
        chart = alt.Chart(df_global.head(20)).mark_bar().encode(
            x='GlobalWeight:Q',
            y=alt.Y('SubKriteria:N', sort='-x')
        ).properties(height=500)
        st.altair_chart(chart, use_container_width=True)
    except:
        st.info("Altair tidak tersedia, grafik dilewati.")

    st.markdown("---")
    st.subheader("4. Download Laporan")
    submission_row = {
        "id": sid,
        "username": user["username"],
        "timestamp": ts,
        "result": res
    }
    pdf_bytes = generate_pdf_bytes(submission_row)
    st.download_button(
        "📄 Download Laporan PDF",
        data=pdf_bytes,
        file_name=f"hasil_ahp_{sid}.pdf",
        mime="application/pdf"
    )

    excel_bytes = to_excel_bytes({
        "Kriteria_Utama": df_main,
        "Global_Weights": df_global,
    })
    st.download_button(
        "📊 Download Excel",
        data=excel_bytes,
        file_name=f"hasil_ahp_{sid}.xlsx",
        mime="application/vnd.openxmlformats-officedocument-spreadsheetml.sheet"
    )

# ------------------------------
# Halaman: Admin Panel
# ------------------------------
# ===============================
# ADMIN PANEL
# ===============================
if "user_is_admin" not in st.session_state:
    st.session_state.user_is_admin = False

elif page == "Admin Panel" and user_is_admin:

    st.title("📊 Admin Panel – Manajemen Penilaian Pakar")

    # Ambil semua penilaian
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT submissions.id, users.username, submissions.timestamp
        FROM submissions
        JOIN users ON submissions.user_id = users.id
        ORDER BY submissions.timestamp DESC
    """, conn)
    conn.close()

    if df.empty:
        st.info("Belum ada data penilaian.")
        st.stop()

    st.subheader("📄 Daftar Semua Penilaian")
    st.dataframe(df)

    st.subheader("🗑 Hapus Penilaian")

    delete_id = st.selectbox(
        "Pilih ID penilaian yang ingin dihapus",
        df["id"].tolist()
    )

    # Tampilkan informasi penilaian yang dipilih
    row = df[df["id"] == delete_id].iloc[0]
    st.write(f"**User:** {row['username']}  \n**Waktu:** {row['timestamp']}")

    # Konfirmasi delete
    konfirmasi = st.checkbox("Saya yakin ingin menghapus penilaian ini")

    if st.button("⚠ Hapus Penilaian", type="primary"):
        if not konfirmasi:
            st.warning("Centang konfirmasi terlebih dahulu.")
            st.stop()

        delete_submission(delete_id)
        st.success(f"Penilaian dengan ID {delete_id} berhasil dihapus.")

        st.experimental_rerun()

        # -------------------------
        # KONFIRMASI DELETE
        # -------------------------
        confirm = st.checkbox(
            f"Saya yakin ingin menghapus penilaian ID {delete_id}",
            help="Centang untuk mengonfirmasi penghapusan"
        )

        if st.button("Hapus Penilaian Sekarang", type="primary"):
            if confirm:
                delete_submission(delete_id)
                st.success(f"Penilaian dengan ID {delete_id} berhasil dihapus!")
                st.experimental_rerun()
            else:
                st.error("Konfirmasi dulu sebelum menghapus penilaian.")


# ------------------------------
# Halaman: Laporan Final Gabungan Pakar
# ------------------------------
elif page == "Laporan Final Gabungan Pakar":
    st.header("Laporan Final Gabungan Antar Pakar (AIJ & AIP)")

    cur.execute("""
        SELECT s.result_json, u.username, s.main_pairs
        FROM submissions s
        JOIN users u ON u.id = s.user_id
    """)
    rows = cur.fetchall()

    if not rows:
        st.info("Belum ada pakar yang mengisi kuesioner.")
        st.stop()

    all_results = [json.loads(r[0]) for r in rows]
    main_pairs_list = [json.loads(r[2]) if r[2] else {} for r in rows]
    usernames = [r[1] for r in rows]
    n_pakar = len(all_results)

    st.subheader(f"Total Pakar: {n_pakar}")
    st.write(", ".join(usernames))

    # 1. AIJ (agregasi pairwise matrices)
    st.markdown("## 1. Agregasi Individual Judgments (AIJ)")
    # reconstruct each main matrix from stored main_pairs
    all_main_matrices = []
    for mp in main_pairs_list:
        # mp keys like "A ||| B" -> value
        pair_values = {}
        for k,v in mp.items():
            a,b = [s.strip() for s in k.split("|||")]
            pair_values[(a,b)] = float(v)
        mat = build_matrix_from_pairs(CRITERIA, pair_values)
        all_main_matrices.append(mat)

    # geometric mean across matrices (element-wise)
    GM = np.exp(np.mean([np.log(m) for m in all_main_matrices], axis=0))
    weights_aij = geometric_mean_weights(GM)
    cons_aij = consistency_metrics(GM, weights_aij)

    df_aij = pd.DataFrame({
        "Kriteria": CRITERIA,
        "Bobot (AIJ)": list(map(float, weights_aij))
    })
    st.table(df_aij)
    st.write(f"CI = {cons_aij['CI']:.4f}, CR = {cons_aij['CR']:.4f}")

    # 2. AIP (agregasi prioritas)
    st.markdown("## 2. Agregasi Individual Priorities (AIP)")
    matrices = []
    for res in all_results:
        matrices.append(np.array(res["main"]["weights"]))
    AIP_vector = np.prod(matrices, axis=0) ** (1/n_pakar)
    AIP_vector = AIP_vector / np.sum(AIP_vector)
    df_aip = pd.DataFrame({
        "Kriteria": CRITERIA,
        "Bobot (AIP)": list(map(float, AIP_vector))
    })
    st.table(df_aip)

    # 3. Gabungan Ranking Global
    st.markdown("## 3. Ranking Global Sub-Kriteria (AIJ & AIP)")
    all_global = []
    for res in all_results:
        all_global.append(pd.DataFrame(res["global"]))
    merged = pd.concat(all_global)
    merged = merged.groupby("SubKriteria").agg({"GlobalWeight":"mean"})
    merged = merged.sort_values("GlobalWeight", ascending=False)
    st.table(merged)

    # 4. Unduhan laporan final
    st.markdown("## 4. Unduh Laporan Final")
    excel_bytes = to_excel_bytes({
        "AHP_Kriteria_AIJ": df_aij,
        "AHP_Kriteria_AIP": df_aip,
        "Ranking_Global": merged.reset_index()
    })
    st.download_button(
        "📊 Download Excel Final",
        data=excel_bytes,
        file_name="AHP_Final_Gabungan.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    pdf_bytes = generate_pdf_bytes({
        "username": "TIM PAKAR",
        "timestamp": "Gabungan",
        "result": {
            "main": {"keys": CRITERIA, "weights": list(map(float, weights_aij)), "cons": cons_aij},
            "global": merged.reset_index().rename(columns={"index":"SubKriteria"}).to_dict(orient="records")
        }
    })
    st.download_button(
        "📄 Download PDF Final",
        data=pdf_bytes,
        file_name="AHP_Final_Gabungan.pdf",
        mime="application/pdf"
    )
# ------------------------------
# Halaman: Laporan Final Gabungan Pakar
# ------------------------------
elif user['is_admin'] and page == "Laporan Final Gabungan Pakar":
    st.header("Laporan Final Gabungan Pakar (AHP)")

    # Ambil semua submission terbaru per pengguna
    cur.execute("""
        SELECT u.username, s.result_json
        FROM users u
        JOIN (
            SELECT user_id, MAX(id) AS max_id
            FROM submissions
            GROUP BY user_id
        ) AS latest ON latest.user_id = u.id
        JOIN submissions s ON s.id = latest.max_id
        ORDER BY u.username
    """)
    experts = cur.fetchall()

    if not experts:
        st.warning("Belum ada submission dari pakar.")
        st.stop()

    st.success(f"Ditemukan {len(experts)} pakar dengan submission terbaru.")

    # -------------------------------------------
    # 1) Gabungkan bobot kriteria utama (geometric mean)
    # -------------------------------------------
    all_main = []

    for username, rjson in experts:
        res = json.loads(rjson)
        all_main.append(np.array(res["main"]["weights"]))

    main_matrix = np.vstack(all_main)
    gm_main = np.exp(np.mean(np.log(main_matrix), axis=0))

    # Normalisasi
    gm_main = gm_main / gm_main.sum()

    df_main = pd.DataFrame({
        "Kriteria": CRITERIA,
        "Bobot Gabungan": gm_main
    })

    st.subheader("1. Bobot Gabungan Kriteria Utama")
    st.table(df_main)

    # -------------------------------------------
    # 2) Gabungkan bobot sub-kriteria (per grup)
    # -------------------------------------------
    local_combined = {}
    global_rows = []

    for group in CRITERIA:
        collect = []
        for username, rjson in experts:
            res = json.loads(rjson)
            w = np.array(res["local"][group]["weights"])
            collect.append(w)

        collect = np.vstack(collect)
        gm = np.exp(np.mean(np.log(collect), axis=0))
        gm = gm / gm.sum()

        local_combined[group] = gm

        for sk, lw in zip(SUBCRITERIA[group], gm):
            idx = CRITERIA.index(group)
            gw = gm_main[idx] * lw
            global_rows.append({
                "Kriteria": group,
                "SubKriteria": sk,
                "LocalWeight": lw,
                "MainWeight": gm_main[idx],
                "GlobalWeight": gw
            })

    # -------------------------------------------
    # 3) Bobot global gabungan
    # -------------------------------------------
    df_global = pd.DataFrame(global_rows).sort_values(
        "GlobalWeight", ascending=False
    )

    st.subheader("2. Bobot Global Gabungan Semua Pakar")
    st.table(df_global)

    # Grafik
    try:
        import altair as alt
        chart = alt.Chart(df_global.head(20)).mark_bar().encode(
            x='GlobalWeight:Q',
            y=alt.Y('SubKriteria:N', sort='-x')
        ).properties(height=500)
        st.altair_chart(chart, use_container_width=True)
    except:
        st.info("Altair tidak tersedia, grafik dilewati.")

    # -------------------------------------------
    # 4) Download Excel & PDF
    # -------------------------------------------
    excel_bytes = to_excel_bytes({
        "Kriteria_Utama_Gabungan": df_main,
        "Global_Gabungan": df_global
    })

    st.download_button(
        "📊 Download Excel Gabungan Pakar",
        data=excel_bytes,
        file_name="gabungan_pakar.xlsx",
        mime="application/vnd.openxmlformats-officedocument-spreadsheetml.sheet"
    )

    # --- PDF (pakai template PDF sebelumnya) ---
    submission_row = {
        "id": 0,
        "username": "SEMUA PAKAR",
        "timestamp": datetime.now().isoformat(),
        "result": {
            "main": {"keys": CRITERIA, "weights": list(map(float, gm_main)), "cons": {"CI":0, "CR":0}},
            "local": {
                group: {
                    "keys": SUBCRITERIA[group],
                    "weights": list(map(float, local_combined[group])),
                    "cons": {"CI":0, "CR":0}
                }
                for group in CRITERIA
            },
            "global": df_global.to_dict(orient="records")
        }
    }

    pdf_bytes = generate_pdf_bytes(submission_row)

    st.download_button(
        "📄 Download PDF Gabungan Pakar",
        data=pdf_bytes,
        file_name="gabungan_pakar.pdf",
        mime="application/pdf"
    )

