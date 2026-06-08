import re
"""
utils/filters.py
────────────────
Shared filter builder untuk semua halaman dashboard.
Eliminasi duplikasi blok filter yang sama di setiap page.

Cara pakai:
    from utils.filters import build_filters, apply_filters

    filters = build_filters(self.df_all, session_prefix="dash")
    df      = apply_filters(self.df_all, filters)
"""

import streamlit as st
from datetime import date, timedelta, datetime
import pytz
import pandas as pd


# ─────────────────────────────────────────────────────────────────
#  KONSTANTA
# ─────────────────────────────────────────────────────────────────
TIMEZONE   = "Asia/Jakarta"
TARGET_OK  = 98.65

# Batas jam per shift (inklusif bawah, eksklusif atas)
SHIFT_HOURS = {
    "1": (7, 16),
    "2": (16, 23),
    "3": (23, 7),   # shift 3 melewati tengah malam
}


def _get_current_shift() -> str:
    """Kembalikan shift aktif berdasarkan jam WIB saat ini."""
    tz = pytz.timezone(TIMEZONE)
    hour = datetime.now(tz).hour
    if 6 <= hour < 16:
        return "1"
    elif 16 <= hour < 23:
        return "2"
    else:
        return "3"


def build_filters(df_all: pd.DataFrame, session_prefix: str) -> dict:
    """
    Render baris filter (10 kolom) dan kembalikan dict nilai filter aktif.
    """
    p = session_prefix  # alias pendek

    # ── Opsi dropdown statis/mandiri ───────────────────────────────
    cmm_opts   = ["All CMM"]      + sorted(df_all["CMMName"].dropna().unique().tolist())
    cat_opts   = ["All Category"] + sorted(df_all["Category"].dropna().unique().tolist())
    shift_opts = ["All Shift"]    + sorted(df_all["Shift"].dropna().unique().tolist())
    kp_opts    = ["All KP"]       + sorted(df_all["KP"].dropna().astype(str).unique().tolist())

    # ── Handle reset flags dari Back button — HARUS SEBELUM curr_part/model dibaca
    if st.session_state.pop(f"_reset_{p}_model", False):
        st.session_state.pop(f"{p}_model", None)
    if st.session_state.pop(f"_reset_{p}_part", False):
        st.session_state.pop(f"{p}_part", None)
        st.session_state.pop(f"{p}_model", None)

    # Ambil status pilihan Part dan Model (setelah reset) ─────────────
    curr_part  = st.session_state.get(f"{p}_part", "All Part")
    curr_model = st.session_state.get(f"{p}_model", "All Model")

    # Opsi Part & Model saling bergantung (cascade)
    if curr_part != "All Part":
        _tmp_m = df_all[df_all["PartName"] == curr_part]
        model_opts = ["All Model"] + sorted(_tmp_m["ModelName"].dropna().unique().tolist())
    else:
        model_opts = ["All Model"] + sorted(df_all["ModelName"].dropna().unique().tolist())

    if curr_model != "All Model":
        _tmp_p = df_all[df_all["ModelName"] == curr_model]
        part_opts = ["All Part"] + sorted(_tmp_p["PartName"].dropna().unique().tolist())
    else:
        part_opts = ["All Part"] + sorted(df_all["PartName"].dropna().unique().tolist())

    # ── Opsi SampleNo Dinamis (bergantung pada Part & Model) ───────
    _tmp_s = df_all.copy()
    if curr_part != "All Part":
        _tmp_s = _tmp_s[_tmp_s["PartName"] == curr_part]
    if curr_model != "All Model":
        _tmp_s = _tmp_s[_tmp_s["ModelName"] == curr_model]

    sampleno_opts = ["All SampleNo"] + sorted(
        _tmp_s["SampleNo"].dropna().astype(str).unique().tolist(),
        key=lambda s: [int(c) if c.isdigit() else c.lower()
                       for c in re.split(r"(\d+)", s)])

    # --- TAMBAHAN FIX STATE NYANGKUT ---
    # Cek current state. Jika nilainya nyangkut di memori tapi tidak ada di opsi baru, reset paksa.
    current_sampleno_state = st.session_state.get(f"{p}_sampleno", "All SampleNo")
    if current_sampleno_state not in sampleno_opts:
        st.session_state[f"{p}_sampleno"] = "All SampleNo"
        current_sampleno_state = "All SampleNo"
        
    # Ambil index yang benar agar selectbox tidak kebingungan
    idx_sampleno = sampleno_opts.index(current_sampleno_state)
    # -----------------------------------

    # ── Render kolom filter (10 kolom, Cycle disembunyikan dari UI) ─
    # ── Default shift otomatis ───────────────────────────────────────
    current_shift  = _get_current_shift()
    shift_opts_str = [str(x) for x in shift_opts]
    default_shift_idx = shift_opts_str.index(current_shift) if current_shift in shift_opts_str else 0

    # Row 1: Time (paling kiri), lalu filter lainnya
    # 8 kolom equal width — semua filter muat tanpa terpotong
    # Urutan: Time | Shift | CMM | Part | Model | Cat | KP | SampleNo
    cols = st.columns([1.3, 1, 1, 1.3, 1.3, 1.3, 1.4, 1.2], gap="small")
    with cols[0]: f_time = st.selectbox("Time", ["Today", "Last 7 Days", "All Time", "Custom"],
                                        key=f"{p}_time", label_visibility="collapsed", filter_mode=None)
    with cols[1]:
        f_shift = st.selectbox("Shift", shift_opts,
            index=default_shift_idx, key=f"{p}_shift",
            label_visibility="collapsed",
            format_func=lambda x: f"Shift {x}" if str(x) != "All Shift" else x, filter_mode=None)
    with cols[2]: f_cmm   = st.selectbox("CMM",   cmm_opts,   key=f"{p}_cmm",   label_visibility="collapsed", filter_mode=None)
    with cols[3]: f_part  = st.selectbox("Part",  part_opts,  key=f"{p}_part",  label_visibility="collapsed", filter_mode=None)
    with cols[4]: f_model = st.selectbox("Model", model_opts, key=f"{p}_model", label_visibility="collapsed", filter_mode=None)
    with cols[5]: f_cat   = st.selectbox("Cat",   cat_opts,   key=f"{p}_cat",   label_visibility="collapsed", filter_mode=None)
    _kp_opts  = ["All KP", "1"] if f_cat == "Produksi" else ["All KP"]
    _kp_state = st.session_state.get(f"{p}_kp", "All KP")
    if _kp_state not in _kp_opts:
        st.session_state[f"{p}_kp"] = "All KP"; _kp_state = "All KP"
    with cols[6]: f_kp = st.selectbox("KP", _kp_opts, key=f"{p}_kp",
                                       label_visibility="collapsed", filter_mode=None,
                                       format_func=lambda x: "Semua Titik" if x == "All KP" else "KP Only",
                                       index=_kp_opts.index(_kp_state))
    _sno_disabled = (curr_part == "All Part" or curr_model == "All Model")
    if _sno_disabled:
        sampleno_opts = ["All SampleNo"]; idx_sampleno = 0
    with cols[7]:
        f_sampleno = st.selectbox("SampleNo", sampleno_opts, index=idx_sampleno,
            key=f"{p}_sampleno", label_visibility="collapsed",
            filter_mode=None, disabled=_sno_disabled)

    # ── Rentang tanggal — muncul di baris bawah hanya kalau Custom ────
    today = date.today()
    if f_time == "Today":
        d1_val, d2_val = today, today
    elif f_time == "Last 7 Days":
        d1_val, d2_val = today - timedelta(days=7), today
    elif f_time == "All Time":
        d1_val = df_all["Date"].dt.date.min() if not df_all.empty else today
        d2_val = df_all["Date"].dt.date.max() if not df_all.empty else today
    else:
        d1_val, d2_val = today, today

    is_custom = (f_time == "Custom")
    if is_custom:
        dc1, dc2, _ = st.columns([1.5, 1.5, 6], gap="small")
        with dc1: f_d1 = st.date_input("📅 Dari", value=d1_val, key=f"d1_{p}_custom", label_visibility="visible")
        with dc2: f_d2 = st.date_input("📅 Sampai", value=d2_val, key=f"d2_{p}_custom", label_visibility="visible")
    else:
        f_d1, f_d2 = d1_val, d2_val

    # ── Default shift (untuk kalkulasi default_shift_idx di atas) ──────
    return {
        "cmm":      f_cmm,
        "part":     f_part,
        "model":    f_model,
        "cat":      f_cat,
        "kp":       f_kp,
        "time":     f_time,
        "d1":       f_d1,
        "d2":       f_d2,
        "shift":    f_shift,
        "sampleno": f_sampleno,
        "cycle":    st.session_state.get(f"{p}_cycle_hidden", "All Cycle"),
    }


def build_filters_dashboard(df_all: pd.DataFrame, session_prefix: str = "shared") -> dict:
    """
    Filter Dashboard — 1 baris.
      Urutan : Periode | Shift | Kategori | Mesin CMM | [From | To jika Custom] | Part·Model
    Date input hanya muncul saat Custom dipilih.
    Return dict kompatibel dengan apply_filters.
    """
    p = session_prefix

    # ── Konstanta pills ───────────────────────────────────────────
    TIME_OPTS = ["Today", "7H", "30H", "All", "Custom"]
    TIME_MAP  = {
        "Today":  "Today",
        "7H":     "Last 7 Days",
        "30H":    "Last 30 Days",
        "All":    "All Time",
        "Custom": "Custom",
    }
    SHIFT_OPTS    = ["All", "S1", "S2", "S3"]
    SHIFT_MAP     = {"All": "All Shift", "S1": "1", "S2": "2", "S3": "3"}
    current_shift = _get_current_shift()
    SHIFT_DEFAULT = f"S{current_shift}" if f"S{current_shift}" in SHIFT_OPTS else "All"

    # ── Opsi Part · Model dari data ──────────────────────────────
    combos     = (
        df_all[["PartName", "ModelName"]]
        .dropna().drop_duplicates()
        .sort_values(["PartName", "ModelName"])
    )
    combo_opts = ["All Part"] + [
        f"{r.PartName} · {r.ModelName}" for _, r in combos.iterrows()
    ]

    # ── Opsi Category dari data ───────────────────────────────────
    cat_vals = sorted(df_all["Category"].dropna().unique().tolist())
    CAT_OPTS = ["All"] + cat_vals
    CAT_MAP  = {"All": "All Category"} | {c: c for c in cat_vals}

    # ── Opsi Mesin CMM dari data ──────────────────────────────────
    cmm_vals = sorted(df_all["CMMName"].dropna().unique().tolist())
    CMM_OPTS = ["All"] + cmm_vals
    CMM_MAP  = {"All": "All CMM"} | {c: c for c in cmm_vals}

    # ── Layout kolom — tetap sama, Custom tidak tambah kolom ────────
    _cur_time = st.session_state.get(f"{p}_dash_time", "Today")
    is_custom  = (_cur_time == "Custom")

    # Periode | Shift | Kategori | Mesin CMM | Part·Model  (5 kolom, tidak berubah)
    cols = st.columns([1.8, 1.6, 1.4, 1.6, 2.2], gap="small")
    col_time, col_shift, col_cat, col_cmm, col_combo = cols

    # ── Render Time pills + date input di bawahnya (kolom Periode) ──
    with col_time:
        _t = st.pills(
            "⏱ Periode", TIME_OPTS,
            default="Today",
            key=f"{p}_dash_time",
            label_visibility="visible",
            selection_mode="single",
        )
        f_time_pill = _t if _t else "Today"

    f_time = TIME_MAP[f_time_pill]

    # ── Render Shift pills ────────────────────────────────────────
    with col_shift:
        _s = st.pills(
            "🕐 Shift", SHIFT_OPTS,
            default=SHIFT_DEFAULT,
            key=f"{p}_dash_shift",
            label_visibility="visible",
            selection_mode="single",
        )
        f_shift_pill = _s if _s else "All"

    f_shift = SHIFT_MAP[f_shift_pill]

    # ── Render Category pills ─────────────────────────────────────
    with col_cat:
        _c = st.pills(
            "🏷 Kategori", CAT_OPTS,
            default="All",
            key=f"{p}_dash_cat",
            label_visibility="visible",
            selection_mode="single",
        )
        f_cat_pill = _c if _c else "All"

    f_cat = CAT_MAP[f_cat_pill]

    # ── Render Mesin CMM pills ────────────────────────────────────
    with col_cmm:
        _m = st.pills(
            "🔬 Mesin CMM", CMM_OPTS,
            default="All",
            key=f"{p}_dash_cmm",
            label_visibility="visible",
            selection_mode="single",
        )
        f_cmm_pill = _m if _m else "All"

    f_cmm = CMM_MAP[f_cmm_pill]

    # ── Rentang tanggal final ─────────────────────────────────────
    today = date.today()
    if f_time == "Today":
        f_d1, f_d2 = today, today
    elif f_time == "Last 7 Days":
        f_d1, f_d2 = today - timedelta(days=6), today
    elif f_time == "Last 30 Days":
        f_d1, f_d2 = today - timedelta(days=29), today
    elif f_time == "All Time":
        f_d1 = df_all["Date"].dt.date.min() if not df_all.empty else today
        f_d2 = df_all["Date"].dt.date.max() if not df_all.empty else today
    else:
        f_d1, f_d2 = today, today

    # Date input muncul di BAWAH semua filter (baris baru) saat Custom
    if is_custom:
        _dc = st.columns([1, 1, 5])  # 2 kolom kecil, sisanya kosong
        with _dc[0]:
            f_d1 = st.date_input(
                "Dari", value=f_d1,
                key=f"d1_{p}_custom",
                label_visibility="visible",
            )
        with _dc[1]:
            f_d2 = st.date_input(
                "Sampai", value=f_d2,
                key=f"d2_{p}_custom",
                label_visibility="visible",
            )

    # ── Render Part · Model selectbox ────────────────────────────
    with col_combo:
        st.markdown(
            '<p style="font-size:14px;font-weight:600;color:#374151;margin-bottom:4px;">Pilih Part :</p>',
            unsafe_allow_html=True,
        )
        f_combo = st.selectbox(
            "Pilih Part", combo_opts,
            key=f"{p}_combo",
            label_visibility="collapsed",
        )

    # ── Pecah combo → part & model (kompatibel apply_filters) ────
    if f_combo == "All Part":
        f_part, f_model = "All Part", "All Model"
    else:
        parts  = f_combo.split(" · ", 1)
        f_part = parts[0]
        f_model = parts[1] if len(parts) > 1 else "All Model"

    return {
        "cmm":      f_cmm,
        "part":     f_part,
        "model":    f_model,
        "cat":      f_cat,
        "kp":       "All KP",
        "time":     f_time,
        "d1":       f_d1,
        "d2":       f_d2,
        "shift":    f_shift,
        "sampleno": "All SampleNo",
        "cycle":    "All Cycle",
    }


def build_filters_quick(df_all: pd.DataFrame, session_prefix: str = "shared") -> dict:
    """
    Filter ringkas untuk Descriptive Quick mode — Time + Shift + Category.
    Part·Model tidak ada karena Quick mode drill-down via klik bar pareto.
    Return dict kompatibel dengan apply_filters.
    """
    p = session_prefix

    # ── Konstanta pills ───────────────────────────────────────────
    TIME_OPTS = ["Today", "7H", "30H", "All", "Custom"]
    TIME_MAP  = {
        "Today":  "Today",
        "7H":     "Last 7 Days",
        "30H":    "Last 30 Days",
        "All":    "All Time",
        "Custom": "Custom",
    }
    SHIFT_OPTS    = ["All", "1", "2", "3"]
    SHIFT_MAP     = {"All": "All Shift", "1": "1", "2": "2", "3": "3"}
    current_shift = _get_current_shift()
    SHIFT_DEFAULT = f"S{current_shift}" if f"S{current_shift}" in SHIFT_OPTS else "All"

    cat_vals  = sorted(df_all["Category"].dropna().unique().tolist())
    CAT_OPTS  = ["All"] + cat_vals
    CAT_MAP   = {"All": "All Category"} | {c: c for c in cat_vals}

    # ── Baca state Time untuk keputusan layout (Custom?) ─────────
    _cur_time = st.session_state.get(f"{p}_dash_time", "Today")
    is_custom = (_cur_time == "Custom")

    # ── Layout: Time | Shift | Cat (+ Date From | To kalau Custom) ────
    if is_custom:
        cols = st.columns([1.6, 1.4, 1.4, 0.8, 1.0, 1.0], gap="small")
        col_time, col_shift, col_cat, col_kp, col_d1, col_d2 = cols
    else:
        cols = st.columns([1.6, 1.4, 1.4, 0.8], gap="small")
        col_time, col_shift, col_cat, col_kp = cols
        col_d1 = col_d2 = None

    # ── Time selectbox ───────────────────────────────────────────
    with col_time:
        f_time_pill = st.selectbox(
            "Periode", TIME_OPTS,
            index=TIME_OPTS.index(st.session_state.get(f"{p}_dash_time", "Today"))
                  if st.session_state.get(f"{p}_dash_time", "Today") in TIME_OPTS else 0,
            key=f"{p}_dash_time",
            label_visibility="collapsed",
        ) or "Today"
    f_time = TIME_MAP[f_time_pill]

    # ── Shift selectbox ───────────────────────────────────────────
    with col_shift:
        f_shift_pill = st.selectbox(
            "Shift", SHIFT_OPTS,
            index=SHIFT_OPTS.index(st.session_state.get(f"{p}_dash_shift", SHIFT_DEFAULT))
                  if st.session_state.get(f"{p}_dash_shift", SHIFT_DEFAULT) in SHIFT_OPTS else 0,
            key=f"{p}_dash_shift",
            label_visibility="collapsed",
            format_func=lambda x: "Semua Shift" if x == "All" else f"Shift {x}",
        ) or SHIFT_DEFAULT
    f_shift = SHIFT_MAP[f_shift_pill]

    # ── Category selectbox (default Produksi) ─────────────────────
    default_cat = "Produksi" if "Produksi" in CAT_OPTS else "All"
    with col_cat:
        f_cat_pill = st.selectbox(
            "Category", CAT_OPTS,
            index=CAT_OPTS.index(st.session_state.get(f"{p}_dash_cat", default_cat))
                  if st.session_state.get(f"{p}_dash_cat", default_cat) in CAT_OPTS else
                  (CAT_OPTS.index(default_cat) if default_cat in CAT_OPTS else 0),
            key=f"{p}_dash_cat",
            label_visibility="collapsed",
        ) or default_cat
    f_cat = CAT_MAP.get(f_cat_pill, f_cat_pill)

    # ── KP selectbox ──────────────────────────────────────────────
    _kp_q_opts = ["Semua Titik", "KP Only"] if f_cat_pill == "Produksi" else ["Semua Titik"]
    _kp_q_st   = st.session_state.get(f"{p}_dash_kp", "Semua Titik")
    if _kp_q_st not in _kp_q_opts: _kp_q_st = "Semua Titik"
    f_kp = "All KP"
    with col_kp:
        kp_val = st.selectbox(
            "KP", _kp_q_opts,
            key=f"{p}_dash_kp",
            label_visibility="collapsed",
            index=_kp_q_opts.index(_kp_q_st),
        ) or "Semua Titik"
    f_kp = "1" if kp_val == "KP Only" else "All KP"

    # ── Rentang tanggal sesuai preset ────────────────────────────
    today = date.today()
    if f_time == "Today":
        d1_val, d2_val = today, today
    elif f_time == "Last 7 Days":
        d1_val, d2_val = today - timedelta(days=6), today
    elif f_time == "Last 30 Days":
        d1_val, d2_val = today - timedelta(days=29), today
    elif f_time == "All Time":
        d1_val = df_all["Date"].dt.date.min() if not df_all.empty else today
        d2_val = df_all["Date"].dt.date.max() if not df_all.empty else today
    else:
        d1_val, d2_val = today, today

    # ── Date input (hanya saat Custom) ───────────────────────────
    if is_custom and col_d1 is not None:
        with col_d1:
            f_d1 = st.date_input(
                "From", value=d1_val,
                key=f"d1_{p}_custom",
                label_visibility="collapsed",
            )
        with col_d2:
            f_d2 = st.date_input(
                "To", value=d2_val,
                key=f"d2_{p}_custom",
                label_visibility="collapsed",
            )
    else:
        f_d1, f_d2 = d1_val, d2_val

    return {
        "cmm":      "All CMM",
        "part":     "All Part",
        "model":    "All Model",
        "cat":      f_cat,
        "kp":       f_kp,
        "time":     f_time,
        "d1":       f_d1,
        "d2":       f_d2,
        "shift":    f_shift,
        "sampleno": "All SampleNo",
        "cycle":    "All Cycle",
    }


def apply_filters(df_all: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """
    Terapkan filters (hasil build_filters) ke df_all.
    Tidak melakukan .copy() yang tidak perlu — langsung chain boolean mask.
    """
    mask = pd.Series(True, index=df_all.index)

    if filters.get("cmm")      != "All CMM":      mask &= df_all["CMMName"]  == filters["cmm"]
    if filters.get("part")     != "All Part":     mask &= df_all["PartName"]  == filters["part"]
    if filters.get("model")    != "All Model":    mask &= df_all["ModelName"] == filters["model"]
    if filters.get("cat")      != "All Category": mask &= df_all["Category"]  == filters["cat"]
    if filters.get("kp")       != "All KP":       mask &= df_all["KP"].astype(str) == filters["kp"]
    if filters.get("shift")    != "All Shift":    mask &= df_all["Shift"].astype(str) == str(filters["shift"])
    if filters.get("sampleno") != "All SampleNo": mask &= df_all["SampleNo"].astype(str) == filters["sampleno"]
    
    # Logika cycle tetap dipertahankan
    if filters.get("cycle", "All Cycle") != "All Cycle": 
        mask &= df_all["Cycle"].astype(str) == filters["cycle"]

    mask &= (df_all["Date"].dt.date >= filters["d1"]) & (df_all["Date"].dt.date <= filters["d2"])

    return df_all[mask]