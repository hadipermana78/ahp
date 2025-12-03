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
from io import BytesIO

def to_excel_bytes(df_dict):
    """
    df_dict = {
        "Sheet1": df1,
        "Sheet2": df2,
        ...
    }
    Return bytes Excel tanpa ExcelWriter
    """
    wb = Workbook()
    default_sheet = wb.active
    wb.remove(default_sheet)

    for sheet_name, df in df_dict.items():
        # Excel sheet name <= 31 karakter
        ws = wb.create_sheet(sheet_name[:31])

        # Header
        ws.append(list(df.columns))

        # Rows
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
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    # users table: id, username, pw_salt, pw_hash, is_admin (0/1)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        pw_salt TEXT,
        pw_hash TEXT,
        is_admin INTEGER DEFAULT 0
    )
    """)
    # submissions: id, user_id, timestamp, main_pairs JSON, sub_pairs JSON, result JSON
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
    """
    submission_row: dict with keys: id, user, timestamp, main_pairs (dict), sub_pairs (dict), result (dict)
    returns BytesIO PDF
    """
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
    # draw few rows per page
    for k, row in main_df.iterrows():
        if y < margin + 30*mm:
            c.showPage(); y = height - margin
        c.drawString(x+2*mm, y, f"{k} : {row['Weight']:.4f}")
        y -= 5*mm

    y -= 4*mm
    # Global weights table (top 15)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Bobot Global (top items):")
    y -= 6*mm
    c.setFont("Helvetica", 9)
    gw = pd.DataFrame(res['global']).sort_values('GlobalWeight', ascending=False).head(20)
    for idx, r in gw.iterrows():
        if y < margin + 20*mm:
            c.showPage(); y = height - margin
        text = f"{r['SubKriteria']} ({r['Kriteria']}) — {r['GlobalWeight']:.6f}"
        c.drawString(x+2*mm, y, text if len(text) < 120 else text[:117] + "...")
        y -= 5*mm

    y -= 6*mm
    # Show consistency summary
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Ringkasan Konsistensi (CI / CR):")
    y -= 6*mm
    c.setFont("Helvetica", 9)
    main_cons = res['main']['cons']
    c.drawString(x+2*mm, y, f"Kriteria Utama — CI: {main_cons['CI']:.4f}, CR: {main_cons['CR']:.4f}")
    y -= 5*mm
    # show any groups with high CR
    for grp, grpinfo in res['local'].items():
        if grpinfo['cons']['CR'] > 0.1:
            if y < margin + 20*mm:
                c.showPage(); y = height - margin
            c.drawString(x+2*mm, y, f"Perhatian: CR>0.1 pada {grp} (CR={grpinfo['cons']['CR']:.3f})")
            y -= 5*mm

    # Footer
    c.showPage()
    c.save()
    bio.seek(0)
    return bio

# ------------------------------
# App: auth and pages
# ------------------------------
conn = init_db()
cur = conn.cursor()

# --- Simple auth widgets ---
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
    admin_check = st.sidebar.checkbox("Daftarkan sebagai admin (hati-hati)")  # optional
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

else:  # Logout
    if st.sidebar.button("Logout"):
        st.session_state['user'] = None
        st.sidebar.info("Anda telah logout.")

# Main area
if not st.session_state['user']:
    st.title("Aplikasi Kuesioner AHP — Multi-user")
    st.write("Silakan login atau daftar melalui panel kiri (sidebar).")
    st.write("Setelah login, pengguna dapat mengisi kuesioner dan menyimpan hasil.")
    st.stop()

user = st.session_state['user']
st.sidebar.markdown(f"**User:** {user['username']}  {'(admin)' if user['is_admin'] else ''}")

# Page selector
if user['is_admin']:
    page = st.sidebar.selectbox("Halaman", 
        ["Isi Kuesioner", "My Submissions", "Hasil Akhir Penilaian", "Admin Panel"])
else:
    page = st.sidebar.selectbox("Halaman", 
        ["Isi Kuesioner", "My Submissions", "Hasil Akhir Penilaian"])

# Utility: render pairwise UI for list of items
def pairwise_inputs(items, key_prefix):
    pairs = list(itertools.combinations(items, 2))
    out = {}
    for (a,b) in pairs:
        cols = st.columns([4,0.6,4,2])
        cols[0].write(a)
        cols[1].write("vs")
        cols[2].write(b)
        direction_key = f"{key_prefix}_{a}_{b}_dir"
        scale_key = f"{key_prefix}_{a}_{b}_scale"
        # default direction left
        direction = cols[1].radio("", [a, b], key=direction_key, horizontal=True, label_visibility="collapsed")
        val = cols[3].selectbox("", options=list(range(1,10)), key=scale_key)
        if direction == a:
            out[(a,b)] = float(val)
        else:
            out[(a,b)] = float(1.0/val)
    return out

# Page: Isi Kuesioner
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
        # convert keys to strings for JSON storage
        # store as dict with "a ||| b" keys
        sub_pairs[group] = {f"{a} ||| {b}": v for (a,b),v in sp.items()}

    if st.button("Simpan hasil ke database"):
        # compute results
        main_mat = build_matrix_from_pairs(CRITERIA, main_pairs)
        main_w = geometric_mean_weights(main_mat)
        main_cons = consistency_metrics(main_mat, main_w)
        local = {}
        global_rows = []
        for i, group in enumerate(CRITERIA):
            # reconstruct pair dict for build_matrix
            # But we stored main_pairs keys as tuples (a,b) with float values already
            mat = build_matrix_from_pairs(SUBCRITERIA[group], {tuple(k.split(" ||| ")):v for k,v in sub_pairs[group].items()})
            w = geometric_mean_weights(mat)
            cons = consistency_metrics(mat, w)
            local[group] = {"keys": SUBCRITERIA[group], "weights": list(map(float,w)), "cons": cons}
            for sk, lw in zip(SUBCRITERIA[group], w):
                global_rows.append({"Kriteria": group, "SubKriteria": sk, "LocalWeight": float(lw), "MainWeight": float(main_w[i]), "GlobalWeight": float(main_w[i]*lw)})

        result = {
            "main": {"keys": CRITERIA, "weights": list(map(float,main_w)), "cons": main_cons},
            "local": local,
            "global": global_rows
        }
        # save to db
        ts = datetime.now().isoformat()
        cur.execute("INSERT INTO submissions (user_id, timestamp, main_pairs, sub_pairs, result_json) VALUES (?,?,?,?,?)",
                    (user['id'], ts, json.dumps({f"{a}|||{b}":v for (a,b),v in main_pairs.items()}),
                     json.dumps(sub_pairs), json.dumps(result)))
        conn.commit()
        st.success("Hasil berhasil disimpan.")
        st.experimental_rerun()

# Page: My Submissions
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
            # show short summary
            dfg = pd.DataFrame(res['global']).sort_values("GlobalWeight", ascending=False).head(10)
            st.table(dfg)
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"Download Excel #{sid}", key=f"ex_{sid}"):
                    # build excel
                    df_main = pd.DataFrame({"Kriteria": res['main']['keys'], "Weight": res['main']['weights']})
                    df_global = pd.DataFrame(res['global']).sort_values("GlobalWeight", ascending=False)
                    out = BytesIO()
                    with pd.ExcelWriter(out, engine="openpyxl") as writer:
                        df_main.to_excel(writer, sheet_name="Kriteria_Utama", index=False)
                        df_global.to_excel(writer, sheet_name="Global_Weights", index=False)
                    out.seek(0)
                    st.download_button("Download Excel", data=out, file_name=f"submission_{sid}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            with col2:
                if st.button(f"Download PDF #{sid}", key=f"pdf_{sid}"):
                    # prepare submission row for pdf generator
                    cur.execute("SELECT s.id, u.username, s.timestamp, s.result_json FROM submissions s JOIN users u ON u.id = s.user_id WHERE s.id = ?", (sid,))
                    r = cur.fetchone()
                    sid2, username, timestamp, result_json = r
                    submission_row = {"id": sid2, "username": username, "timestamp": timestamp, "result": json.loads(result_json)}
                    pdf_bio = generate_pdf_bytes(submission_row)
                    st.download_button("Download PDF", data=pdf_bio, file_name=f"submission_{sid}.pdf", mime="application/pdf")
                    # ---------------------------------------------
# PAGE: HASIL AKHIR PENILAIAN PAKAR
# ---------------------------------------------
elif page == "Hasil Akhir Penilaian":
    st.header("Hasil Akhir Penilaian Pakar (AHP)")

    # Ambil submission terbaru milik user
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

    # Optional grafik
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

    # === PDF ===
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

    # === Excel ===
    excel_bytes = to_excel_bytes({
        "Kriteria_Utama": df_main,
        "Global_Weights": df_global,
    })

    st.download_button(
        "📊 Download Excel",
        data=excel_bytes,
        file_name=f"hasil_ahp_{sid}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# Page: Admin Panel
if user['is_admin'] and page == "Admin Panel":
    st.header("Admin Panel — Semua Submission")
    cur.execute("""SELECT s.id, u.username, s.timestamp, s.result_json
                   FROM submissions s JOIN users u ON u.id = s.user_id ORDER BY s.id DESC""")
    allrows = cur.fetchall()
    st.write(f"Total submission: {len(allrows)}")
    # quick export for all as excel
    all_global = []
    for sid, username, ts, js in allrows:
        res = json.loads(js)
        for row in res['global']:
            row2 = dict(row)
            row2.update({"submission_id": sid, "username": username, "timestamp": ts})
            all_global.append(row2)
    if all_global:
        df_all = pd.DataFrame(all_global)
        out = BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            df_all.to_excel(writer, sheet_name="All_Global", index=False)
        out.seek(0)
        st.download_button("Download Semua Global Weights (Excel)", data=out, file_name="all_global_weights.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # list entries with simple preview and per-row PDF
    for sid, username, ts, js in allrows:
        with st.expander(f"#{sid} — {username} — {ts}"):
            res = json.loads(js)
            st.write("Top 10 Global Weights:")
            st.table(pd.DataFrame(res['global']).sort_values("GlobalWeight", ascending=False).head(10))
            if st.button(f"Download PDF for #{sid}", key=f"adm_pdf_{sid}"):
                submission_row = {"id": sid, "username": username, "timestamp": ts, "result": res}
                pdf_bio = generate_pdf_bytes(submission_row)
                st.download_button("Unduh PDF", data=pdf_bio, file_name=f"submission_{sid}.pdf", mime="application/pdf")

# end of file
