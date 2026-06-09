import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_option_menu import option_menu
import pandas as pd
import os
import base64
from datetime import datetime, timedelta
from pathlib import Path as _PPath

# ── Logo AHM sebagai base64 (dipakai di login, sidebar, report) ──
def _ahm_logo_b64() -> str:
    p = _PPath("assets/Logo_AHM.svg")
    if p.exists():
        return "data:image/svg+xml;base64," + base64.b64encode(p.read_bytes()).decode()
    return ""

# Import class halaman dari folder pages_app
from pages_app.dashboard import DashboardPage
from pages_app.descriptive import DescriptivePage
from pages_app.diagnostic import DiagnosticPage
from pages_app.predictive import PredictivePage
from pages_app.prescriptive import PrescriptivePage
from pages_app.messages import MessagePage
from pages_app.report import ReportPage
from pages_app.settings import SettingsPage
from local_db import get_unread_count, init_db
from floating_chatbot import render_floating_chatbot



# ─────────────────────────────────────────────────────────────────
#  USER CREDENTIALS & ROLES
# ─────────────────────────────────────────────────────────────────
USERS = {
    "admin":       {"password": "admin",       "role": "Admin"},
    "cmm": {"password": "cmm", "role": "Measurement"},
    "produksi":    {"password": "produksi",    "role": "Produksi"},
}

# Pages accessible per role
ALL_PAGES = [
    "Dashboard", "Descriptive", "Diagnostic", "Predictive",
    "Prescriptive", "Messages", "Report", "Settings",
]

ROLE_PAGES = {
    "Admin":       ALL_PAGES,
    "Measurement": ALL_PAGES,
    "Produksi":    ALL_PAGES,
}

PAGE_ICONS = {
    "Dashboard":    "house",
    "Descriptive":  "bar-chart",
    "Diagnostic":   "activity",
    "Predictive":   "graph-up",
    "Prescriptive": "lightbulb",
    "Messages":     "envelope",
    "Report":       "file-text",
    "Settings":     "gear",
}

# ─────────────────────────────────────────────────────────────────
#  CSV DATA LOADING
# ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data(csv_path: str) -> pd.DataFrame:
    if not os.path.exists(csv_path):
        st.error(f"File CSV tidak ditemukan: {csv_path}")
        return pd.DataFrame()
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            st.sidebar.info("File CSV kosong.")
            return df
        df["Date"] = pd.to_datetime(df["Date"])
        df["Nominal"]   = pd.to_numeric(df["Nominal"],   errors="coerce")
        df["Uppertol"]  = pd.to_numeric(df["Uppertol"],  errors="coerce")
        df["Lowertol"]  = pd.to_numeric(df["Lowertol"],  errors="coerce")
        df["Actual"]    = pd.to_numeric(df["Actual"],    errors="coerce")
        df["Deviation"] = pd.to_numeric(df["Deviation"], errors="coerce")
        return df
    except Exception as e:
        st.error(f"Terjadi kesalahan saat membaca file CSV: {e}")
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────────
#  APP CLASS
# ─────────────────────────────────────────────────────────────────
class QualityDashboardApp:
    def __init__(self):
        st.set_page_config(page_title="CMM Quality Dashboard", layout="wide", initial_sidebar_state="expanded")
        self.apply_custom_css()

    # ── CSS ──────────────────────────────────────────────────────
    def apply_custom_css(self):
        st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800&display=swap');
        html, body, [class*="css"], p, div, span, h1, h2, h3, h4, h5, h6 { font-family: 'Inter', sans-serif; }
        #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stHeader"] { display: none !important; height: 0 !important; min-height: 0 !important; padding: 0 !important; margin: 0 !important; }
        [data-testid="stSidebarCollapseButton"], [data-testid="collapsedControl"], [data-testid="stSidebarHeader"] { display: none !important; padding: 0 !important; margin: 0 !important; }
        button[title="View fullscreen"] { display: none !important; }
        [data-testid="stAppViewContainer"] { background: #F1F4F9 !important; }
        [data-testid="stSidebar"] { background: #FFFFFF !important; width: 240px !important; min-width: 240px !important; max-width: 240px !important; border-right: 1px solid #E8ECF2 !important; }
        [data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; overflow-x: hidden; }
        iframe[title="streamlit_option_menu.option_menu"] { background-color: #FFFFFF !important; border: none !important; outline: none !important; }
        div.block-container { padding-top: 1.5rem !important; padding-bottom: 0rem !important; padding-left: 2rem !important; padding-right: 2rem !important; max-width: 100% !important; }
        .page-hdr { display: flex; align-items: center; gap: 10px; margin-top: 0 !important; margin-bottom: 8px; }
        .page-title { font-size: 18px; font-weight: 800; color: #0F172A; letter-spacing: -0.5px; }
        .prediksi-badge { background: #DC2626; color: #fff; border-radius: 4px; padding: 2px 8px; font-size: 10.5px; font-weight: 600; letter-spacing: 0.1px; }
        [data-testid="stSelectbox"] label { display: none !important; }
        [data-testid="stSelectbox"] > div > div { background: #fff !important; border: 1px solid #DDE1EA !important; border-radius: 6px !important; font-size: 12px !important; color: #374151 !important; box-shadow: 0 1px 2px rgba(0,0,0,.04) !important; min-height: 32px !important; }
        div[data-baseweb="select"] > div { border: none !important; box-shadow: none !important; }
        .kpi-card { background: #fff; border-radius: 10px; border: 1px solid #E8ECF2; box-shadow: 0 2px 4px rgba(15,23,42,.03); padding: 12px 16px; display: flex; align-items: center; gap: 12px; min-height: 65px; }
        .kpi-icon { width: 38px; height: 38px; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .kpi-icon svg { width: 18px; height: 18px; }
        .kpi-blue  { background: #EFF6FF; }
        .kpi-green { background: #F0FDF4; }
        .kpi-red   { background: #FEF2F2; }
        .kpi-val { font-size: 20px; font-weight: 800; color: #0F172A; line-height: 1; letter-spacing: -0.5px; }
        .kpi-val-green { color: #15803D; }
        .kpi-val-red   { color: #B91C1C; }
        .kpi-lbl { font-size: 11px; font-weight: 500; color: #64748B; margin-top: 2px; }
        iframe[title*="echarts"] { background-color: #ffffff !important; border-radius: 10px !important; border: 1px solid #E8ECF2 !important; box-shadow: 0 2px 4px rgba(15,23,42,.03) !important; overflow: hidden !important; display: block; }
        .row-gap { margin-bottom: 8px; }

        /* ── Login Page ── */
        .login-wrap {
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; background: #F1F4F9;
        }
        .login-card {
            background: #fff; border-radius: 16px; border: 1px solid #E8ECF2;
            box-shadow: 0 8px 32px rgba(15,23,42,.08);
            padding: 40px 36px 36px; width: 100%; max-width: 380px;
        }
        .login-logo {
            display: flex; align-items: center; gap: 12px; margin-bottom: 28px;
        }
        .login-logo-box {
            background: #DC2626; border-radius: 10px;
            width: 42px; height: 42px; display: flex; align-items: center; justify-content: center;
        }
        .login-logo-box span { color: #fff; font-weight: 900; font-size: 11px; letter-spacing: -0.3px; }
        .login-title { font-size: 20px; font-weight: 800; color: #0F172A; margin-bottom: 4px; }
        .login-sub   { font-size: 12px; font-weight: 500; color: #64748B; }

        /* ── Date Input — putih bersih ── */
        div[data-testid="stDateInput"] > div {
            background: #FFFFFF !important;
            border: 1px solid #E2E8F0 !important;
            border-radius: 8px !important;
        }
        div[data-testid="stDateInput"] > div:focus-within {
            border-color: #94A3B8 !important;
            box-shadow: 0 0 0 2px rgba(148,163,184,0.15) !important;
        }
        div[data-testid="stDateInput"] input {
            background: #FFFFFF !important;
            color: #0F172A !important;
        }

        </style>
        """, unsafe_allow_html=True)

    # ── LOGIN PAGE ────────────────────────────────────────────────
# ── LOGIN PAGE ────────────────────────────────────────────────
    def render_login(self):
        # CSS tambahan khusus untuk halaman login
        st.markdown("""
        <style>
        /* 1. Background utama halaman (Abu-abu kebiruan sangat soft) */
        [data-testid="stAppViewContainer"] {
            background: #F1F5F9 !important; 
        }
        
        /* 2. Mengubah kotak st.container menjadi Card Putih bersih dengan bayangan lembut */
        [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #FFFFFF !important;
            border-radius: 16px !important;
            border: 1px solid #E2E8F0 !important;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.04) !important;
        }
        
        /* 3. Memaksa area di dalam kotak ikut menjadi putih */
        [data-testid="stVerticalBlockBorderWrapper"] > div {
            background-color: #FFFFFF !important;
            border-radius: 16px !important;
        }

        /* 4. Membuat kotak input (username/password) sedikit abu-abu terang sebagai kontras */
        [data-testid="stTextInput"] > div > div {
            background-color: #F8FAFC !important;
            border: 1px solid #E2E8F0 !important;
            box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.02) !important;
        }
        [data-testid="stTextInput"] > div > div:focus-within {
            border-color: #FCA5A5 !important; /* Garis tepi merah muda saat diklik */
            box-shadow: 0 0 0 2px #FEE2E2 !important;
        }
        </style>
        """, unsafe_allow_html=True)
        # Center the login card using columns
        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            _logo_url = _ahm_logo_b64()
            st.markdown(f"""
            <div style="margin-top: 80px;">
              <div style="display:flex; align-items:center; gap:12px; margin-bottom:28px;">
                {"<img src='"+_logo_url+"' style='height:42px;width:auto;object-fit:contain;flex-shrink:0;' />" if _logo_url else "<div style='background:#DC2626;border-radius:10px;width:42px;height:42px;display:flex;align-items:center;justify-content:center;'><span style='color:#fff;font-weight:900;font-size:11px;'>AHM</span></div>"}
                <div>
                  <div style="font-size:18px; font-weight:800; color:#0F172A; line-height:1.2;">CMM Quality Dashboard</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            with st.container(border=True):
                st.markdown("<div style='margin-bottom:4px; font-size:15px; font-weight:700; color:#0F172A;'>Sign In</div>", unsafe_allow_html=True)
                st.markdown("<div style='font-size:11.5px; color:#64748B; margin-bottom:20px;'>Masukkan kredensial Anda untuk melanjutkan</div>", unsafe_allow_html=True)

                username = st.text_input("Username", placeholder="Username", label_visibility="collapsed")
                password = st.text_input("Password", placeholder="Password", type="password", label_visibility="collapsed")

                if st.button("Login", use_container_width=True, type="primary"):
                    if username in USERS and USERS[username]["password"] == password:
                        st.session_state["logged_in"] = True
                        st.session_state["username"]  = username
                        st.session_state["role"]      = USERS[username]["role"]
                        st.rerun()
                    else:
                        st.error("Username atau password salah.", icon="🔒")

    # ── SIDEBAR ───────────────────────────────────────────────────
# ── SIDEBAR ───────────────────────────────────────────────────
    def render_sidebar(self):
        role     = st.session_state.get("role", "Operator")
        username = st.session_state.get("username", "user")

        # Badge notifikasi untuk Messages
        unread = get_unread_count(role) if role in ("Produksi", "Admin") else 0

        pages = ROLE_PAGES[role]
        icons = [PAGE_ICONS[p] for p in pages]

        # Tambahkan badge ke label Messages kalau ada unread
        display_pages = []
        for p in pages:
            if p == "Messages" and unread > 0:
                display_pages.append(f"Messages ({unread})")
            else:
                display_pages.append(p)
        display_pages.append("Logout")

        display_icons = icons + ["box-arrow-right"]

        # Map display label → page key sebenarnya
        label_to_page = {}
        for i, p in enumerate(pages):
            label_to_page[display_pages[i]] = p
        label_to_page["Logout"] = "Logout"

        initials = username[:2].upper()

        with st.sidebar:
            # Header AHM — Logo SVG
            _logo_url_sb = _ahm_logo_b64()
            _logo_html = (f"<img src='{_logo_url_sb}' style='height:34px;width:auto;object-fit:contain;flex-shrink:0;' />"
                          if _logo_url_sb else
                          "<div style='background:#DC2626;border-radius:8px;width:34px;height:34px;flex-shrink:0;display:flex;align-items:center;justify-content:center;'><span style='color:#fff;font-weight:900;font-size:10px;'>AHM</span></div>")
            st.markdown(f"""
            <div style="padding:16px 20px 14px; display:flex; align-items:center; gap:12px;">
              {_logo_html}
            </div>
            <div style="height:1px; background:#E8ECF2; margin:0;"></div>
            <div style="height:8px;"></div>
            """, unsafe_allow_html=True)

            selected_label = option_menu(
                menu_title=None,
                options=display_pages,
                icons=display_icons,
                default_index=0,
                styles={
                    "container": {"padding": "0!important", "background-color": "#FFFFFF", "border": "none"},
                    "icon": {"color": "#64748B", "font-size": "15px"},
                    "nav-link": {"font-size": "13px", "text-align": "left", "margin": "2px 14px", "padding": "8px 14px", "color": "#475569", "font-weight": "600", "border-radius": "6px", "--hover-color": "#F1F5F9"},
                    "nav-link-selected": {"background-color": "#DC2626", "color": "#FFFFFF", "font-weight": "700"},
                }
            )

            if selected_label == "Logout":
                st.session_state.clear()
                st.rerun()

            @st.fragment(run_every="1s")
            def _live_clock():
                try:
                    import pytz as _tz
                    _now = datetime.now(_tz.timezone("Asia/Jakarta"))
                except Exception:
                    _now = datetime.now()
                h = _now.hour
                shift = 1 if 7 <= h < 16 else (2 if 16 <= h < 24 else 3)
                st.markdown(
                    f'<div style="padding:8px 16px 4px;font-size:11px;font-weight:600;color:#64748B;">'
                    f'{_now.strftime("%H:%M:%S")} WIB · Shift {shift}</div>',
                    unsafe_allow_html=True
                )
            _live_clock()

            st.markdown(f"""
            <div style="position:fixed;bottom:0;left:0;width:240px;background:#FFFFFF;
                        z-index:99;border-top:1px solid #E8ECF2;padding:10px 16px;height:56px;">
              <div style="display:flex;align-items:center;gap:10px;">
                <div style="width:28px;height:28px;border-radius:50%;background:#DC2626;
                            flex-shrink:0;display:flex;align-items:center;justify-content:center;">
                  <span style="color:#fff;font-size:9px;font-weight:700;">{initials}</span>
                </div>
                <div>
                  <div style="font-size:12px;font-weight:700;color:#0F172A;">{username}</div>
                  <div style="font-size:10px;font-weight:500;color:#64748B;">{role}</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        return label_to_page.get(selected_label, selected_label)

    # ── MAIN RUN ──────────────────────────────────────────────────
    def run(self):
        if "logged_in" not in st.session_state:
            st.session_state["logged_in"] = False

        if not st.session_state["logged_in"]:
            self.render_login()
            return

        # ── Keepalive via JS — tidak trigger rerun ─────────────────
        st.components.v1.html("""
        <script>
        // Kirim ping tiap 30 detik supaya WebSocket tidak putus
        setInterval(function() {
            window.parent.postMessage({type: 'streamlit:setComponentValue', value: null}, '*');
        }, 30000);
        </script>
        """, height=0)

        # Inisialisasi database lokal
        init_db()

        nama_file_csv = "REAL7D.csv"
        df_all = load_data(nama_file_csv)

        # ── Warmup XGBoost inference setelah login ────────────────
        # Jalan sekali, hasilnya di-cache 30 menit.
        # Dashboard dan Predictive langsung pakai cache — tidak loading lagi.
        if not df_all.empty:
            from utils.xgb_inference import run_xgb_inference, get_xgb_cache_key, run_rule_prediction, RULE_CACHE_KEY, RULE_TTL
            import time as _wt
            # Warmup XGBoost
            _ck, _, _, _ = get_xgb_cache_key()
            _ts_k = f"{_ck}_ts"
            if _ck not in st.session_state or _wt.time() - st.session_state.get(_ts_k, 0) > 1800:
                run_xgb_inference(df_all)
            # Warmup Rule prediction
            _rts_k = f"{RULE_CACHE_KEY}_ts"
            if RULE_CACHE_KEY not in st.session_state or _wt.time() - st.session_state.get(_rts_k, 0) > RULE_TTL:
                run_rule_prediction(df_all)

        username = st.session_state.get("username", "")

        selected_page = self.render_sidebar()

        # Override navigasi kalau ada flag dari halaman lain (misal Messages → Report)
        if st.session_state.get("nav_to_page"):
            selected_page = st.session_state.pop("nav_to_page")

        page_map = {
            "Dashboard":    lambda: DashboardPage(df_all),
            "Descriptive":  lambda: DescriptivePage(df_all),
            "Diagnostic":   lambda: DiagnosticPage(df_all),
            "Predictive":   lambda: PredictivePage(df_all),
            "Prescriptive": lambda: PrescriptivePage(df_all),
            "Messages":     lambda: MessagePage(df_all),
            "Report":       lambda: ReportPage(df_all, current_user=username),
            "Settings":     lambda: SettingsPage(df_all),
        }

        if selected_page in page_map:
            page_map[selected_page]().render()
            render_floating_chatbot()
        else:
            st.markdown(f"""
            <div style="display:flex; align-items:center; justify-content:center; height:60vh; flex-direction:column; gap:12px;">
              <div style="font-size:40px; color:#CBD5E1;">—</div>
              <div style="font-size:22px; font-weight:800; color:#0F172A;">{selected_page}</div>
              <div style="font-size:14px; color:#94A3B8;">Halaman ini belum tersedia.</div>
            </div>
            """, unsafe_allow_html=True)


if __name__ == "__main__":
    app = QualityDashboardApp()
    app.run()