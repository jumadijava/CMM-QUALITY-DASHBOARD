import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from streamlit_echarts import st_echarts

# ─────────────────────────────────────────────────────────────────
#  Definisi Aturan Deteksi Proses di Luar Kendali
# ─────────────────────────────────────────────────────────────────
RULES = {
    1: {"label": "Rule 1", "color": "#EF4444", "severity": "Critical",
        "desc": "1 titik di luar ±3σ"},
    2: {"label": "Rule 2", "color": "#F59E0B", "severity": "Warning",
        "desc": "Delapan titik data berurutan berada di satu sisi nilai rata-rata."},
    3: {"label": "Rule 3", "color": "#8B5CF6", "severity": "Warning",
        "desc": "Tujuh titik data berturut-turut yang meningkat atau menurun."},
    4: {"label": "Rule 4", "color": "#06B6D4", "severity": "Warning",
        "desc": "Empat belas titik data berurutan yang bergantian naik dan turun."},
    5: {"label": "Rule 5", "color": "#10B981", "severity": "Warning",
        "desc": "Dua titik data, dari tiga titik data berurutan, berada di sisi yang sama dari rata-rata di zona A atau di luarnya."},
    6: {"label": "Rule 6", "color": "#F97316", "severity": "Warning",
        "desc": "Empat titik data, dari lima titik data berurutan, berada di sisi yang sama dari rata-rata di zona B atau lebih jauh."},
    7: {"label": "Rule 7", "color": "#3B82F6", "severity": "Warning",
        "desc": "Lima belas titik data berurutan berada dalam zona C (di atas dan di bawah rata-rata)."},
}


def _detect_kendali(values: list) -> dict[int, set]:
    """Deteksi 7 kondisi proses di luar kendali, return dict rule → set of violated indices."""
    vbr = {r: set() for r in range(1, 8)}
    n = len(values)
    if n < 2:
        return vbr

    mean  = float(np.mean(values))
    sigma = float(np.std(values, ddof=1)) if n > 1 else 0.0
    if sigma == 0:
        return vbr

    for i, v in enumerate(values):
        if abs(v - mean) > 3 * sigma:
            vbr[1].add(i)

    for i in range(n - 7):
        w = values[i:i+8]
        if all(v > mean for v in w) or all(v < mean for v in w):
            for j in range(i, i+8): vbr[2].add(j)

    for i in range(n - 6):
        w = values[i:i+7]
        if all(w[j] < w[j+1] for j in range(6)) or all(w[j] > w[j+1] for j in range(6)):
            for j in range(i, i+7): vbr[3].add(j)

    for i in range(n - 13):
        w = values[i:i+14]
        if all((w[j] < w[j+1]) != (w[j+1] < w[j+2]) for j in range(12)):
            for j in range(i, i+14): vbr[4].add(j)

    for i in range(n - 2):
        w = values[i:i+3]
        if (sum(1 for v in w if v > mean + 2*sigma) >= 2 or
                sum(1 for v in w if v < mean - 2*sigma) >= 2):
            for j in range(i, i+3): vbr[5].add(j)

    for i in range(n - 4):
        w = values[i:i+5]
        if (sum(1 for v in w if v > mean + sigma) >= 4 or
                sum(1 for v in w if v < mean - sigma) >= 4):
            for j in range(i, i+5): vbr[6].add(j)

    for i in range(n - 14):
        w = values[i:i+15]
        if all(abs(v - mean) < sigma for v in w):
            for j in range(i, i+15): vbr[7].add(j)

    return vbr


@st.cache_data(show_spinner=False)
def _build_kendali_history(df_all: pd.DataFrame) -> pd.DataFrame:
    """
    Scan seluruh data CMM, deteksi kondisi proses di luar kendali per titik ukur.
    Return DataFrame: Part, Model, Ref, Parameter, Rule, n_violations,
                      last_date, severity, Category
    """
    param_col = "point" if "point" in df_all.columns else "Parameter"
    records   = []

    has_sno    = "SampleNo" in df_all.columns
    group_keys = ["PartName", "ModelName", "ref", param_col]
    if has_sno:
        group_keys.append("SampleNo")

    for keys, grp in df_all.groupby(group_keys, sort=False):
        if has_sno:
            part, model, ref, param, sno = keys
        else:
            part, model, ref, param = keys
            sno = None

        ref_str = str(ref).strip()
        if ref_str in ("-", "nan", ""):
            ref_str = str(grp["ID"].iloc[0]).strip() if "ID" in grp.columns else "—"

        df_g = grp.sort_values(["Date","Shift","Cycle"]).dropna(subset=["Actual"])
        if len(df_g) < 2:
            continue

        values    = df_g["Actual"].tolist()
        vbr       = _detect_kendali(values)
        last_date = df_g["Date"].max().strftime("%d %b %Y")
        category  = grp["Category"].iloc[0] if "Category" in grp.columns else ""

        for rule_num, idxs in vbr.items():
            if not idxs:
                continue
            rec = {
                "Part":        part,
                "Model":       model,
                "Ref":         ref_str,
                "Parameter":   str(param),
                "Category":    category,
                "Rule":        rule_num,
                "Rule Label":  RULES[rule_num]["label"],
                "Deskripsi":   RULES[rule_num]["desc"],
                "Severity":    RULES[rule_num]["severity"],
                "n Titik":     len(idxs),
                "Terakhir":    last_date,
            }
            if sno is not None:
                rec["SampleNo"] = sno
            records.append(rec)

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).sort_values(
        ["Severity", "Rule", "n Titik"], ascending=[True, True, False]
    ).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────
#  Helper: load ilustrasi rule SPC sebagai base64
# ─────────────────────────────────────────────────────────────────
import base64 as _b64_spc
from pathlib import Path as _SpcPath

_SPC_RULE_IMG_DIR = _SpcPath("assets/ilustrasi")

# Daftar nama file ilustrasi per rule — isi sesuai file yang tersedia
_RULE_IMG_FILES = {
    1: "spc_rule_1.jpg",
    2: "spc_rule_2.jpg",
    3: "spc_rule_3.jpg",
    4: "spc_rule_4.jpg",
    5: "spc_rule_5.jpg",
    6: "spc_rule_6.jpg",
    7: "spc_rule_7.jpg",
}
_RULE_IMG_CACHE: dict = {}

def _get_rule_img_html(r_num: int, border_clr: str) -> str:
    """Return <img> tag base64 atau placeholder teks kalau file tidak ada."""
    if r_num in _RULE_IMG_CACHE:
        return _RULE_IMG_CACHE[r_num]
    fname = _RULE_IMG_FILES.get(r_num, "")
    path  = _SPC_RULE_IMG_DIR / fname if fname else None
    if path and path.exists():
        ext  = path.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        b64  = _b64_spc.b64encode(path.read_bytes()).decode()
        html = (f'<img src="data:{mime};base64,{b64}" '
                f'style="max-width:100%;max-height:78px;object-fit:contain;" '
                f'alt="Rule {r_num}"/>')
    else:
        html = (f'<span style="font-size:10px;color:#CBD5E1;">'
                f'📷 Rule {r_num} — tempatkan file <b>{fname or "spc_rule_"+str(r_num)+".jpg"}</b>'
                f' di folder assets/ilustrasi/</span>')
    _RULE_IMG_CACHE[r_num] = html
    return html


# ─────────────────────────────────────────────────────────────────
#  Page Class
# ─────────────────────────────────────────────────────────────────
class PredictivePage:
    def __init__(self, df_all: pd.DataFrame):
        self.df_all = df_all

    def render(self):
        st.markdown(
            '<div class="page-hdr">'
            '<span class="page-title">Predictive</span></div>',
            unsafe_allow_html=True
        )

        mode = st.segmented_control(
            "Mode", ["🤖 AI Predictive", "⚡ Deteksi Proses di Luar Kendali"],
            default="🤖 AI Predictive",
            key="pred_mode",
            label_visibility="collapsed",
        ) or "🤖 AI Predictive"

        if mode == "🤖 AI Predictive":
            self._render_ai()
        else:
            self._render_spc()

    def _render_ai(self):

        ai_tab = st.segmented_control(
            "AI Tab",
            ["🎯 Klasifikasi", "📈 Forecasting", "📐 Prediksi Rule", "🔍 Anomaly", "💬 AI Insight"],
            default="🎯 Klasifikasi",
            key="pred_ai_tab",
            label_visibility="collapsed",
        ) or "🎯 Klasifikasi"

        if ai_tab == "🎯 Klasifikasi":
            self._render_klasifikasi()
        elif ai_tab == "📈 Forecasting":
            self._render_forecasting()
        elif ai_tab == "📐 Prediksi Rule":
            self._render_prediksi_rule()
        else:
            st.markdown(
                f'<div style="text-align:center;padding:80px 0;">'
                f'<div style="font-size:40px;margin-bottom:12px;">🚧</div>'
                f'<div style="font-size:16px;font-weight:700;color:#0F172A;margin-bottom:6px;">'
                f'{ai_tab} — Sedang dalam pengembangan</div>'
                f'</div>', unsafe_allow_html=True
            )

    def _run_arima(self, y: list, forecast_n: int = 30):
        """Fit auto_arima dan return forecast. Return None kalau gagal."""
        try:
            from pmdarima import auto_arima as _auto_arima
            import warnings
            warnings.filterwarnings("ignore")
            model = _auto_arima(
                y, seasonal=False, stepwise=True,
                suppress_warnings=True, error_action="ignore",
                max_p=5, max_q=5, max_d=2,
                information_criterion="aic",
            )
            fc, ci = model.predict(n_periods=forecast_n, return_conf_int=True)
            return {"model": model, "order": model.order,
                    "aic": round(model.aic(), 2),
                    "fc": fc, "ci": ci}
        except Exception as e:
            return {"error": str(e)}

    def _render_forecasting(self):
        CACHE_CSV = Path("data/batch_arima_summary.csv")

        fc_mode = st.segmented_control(
            "Forecast mode",
            ["🔎 Satu Titik", "📊 Batch Overview"],
            default="🔎 Satu Titik",
            key="pred_fc_mode",
            label_visibility="collapsed",
        ) or "🔎 Satu Titik"

        if fc_mode == "🔎 Satu Titik":
            self._render_forecast_single()
        else:
            self._render_forecast_batch(CACHE_CSV)

    def _render_forecast_single(self):
        df = self.df_all

        # ── Baris 1: Part·Model | SampleNo | Category ────────────
        # Cascade: combo → sampleno → ref → param
        combos_df_fc = (
            df[["PartName","ModelName"]].dropna().drop_duplicates()
            .sort_values(["PartName","ModelName"])
        )
        combo_opts_fc = ["— Pilih Part & Model —"] + [
            f"{r.PartName} · {r.ModelName}" for _, r in combos_df_fc.iterrows()
        ]
        if st.session_state.get("fc_combo") not in combo_opts_fc:
            st.session_state["fc_combo"] = "— Pilih Part & Model —"

        cur_combo_fc = st.session_state.get("fc_combo", "— Pilih Part & Model —")
        df_after_combo_fc = df.copy()
        f_part, f_model = "", ""
        if cur_combo_fc != "— Pilih Part & Model —":
            _sp = cur_combo_fc.split(" · ", 1)
            if len(_sp) == 2:
                f_part, f_model = _sp[0], _sp[1]
                df_after_combo_fc = df[(df["PartName"]==f_part)&(df["ModelName"]==f_model)]

        sno_vals_fc = sorted(
            df_after_combo_fc["SampleNo"].dropna().astype(str).unique().tolist(),
            key=lambda s: (0, int(s)) if s.isdigit() else (1, s)
        )
        sno_opts_fc = ["Semua Sample"] + sno_vals_fc
        if st.session_state.get("fc_sno") not in sno_opts_fc:
            st.session_state["fc_sno"] = "Semua Sample"

        c1, c2, c3 = st.columns([2.5, 1.2, 1.2], gap="small")
        with c1:
            f_combo_fc = st.selectbox("🔩 Part · Model", combo_opts_fc, key="fc_combo")
            if f_combo_fc != "— Pilih Part & Model —":
                _sp = f_combo_fc.split(" · ", 1)
                if len(_sp) == 2:
                    f_part, f_model = _sp[0], _sp[1]
                    df_after_combo_fc = df[(df["PartName"]==f_part)&(df["ModelName"]==f_model)]
        with c2:
            f_sno = st.selectbox("🔢 Sample No", sno_opts_fc, key="fc_sno")
        with c3:
            fc_n = st.number_input("📏 Horizon (shift ke depan)", min_value=5, max_value=90, value=30, step=5, key="fc_n")

        # ── Baris 2: Ref | Parameter (cascade dari combo+sno) ────
        param_col = "point" if "point" in df.columns else "Parameter"
        df_pm = df_after_combo_fc.copy()
        if f_sno != "Semua Sample":
            df_pm = df_pm[df_pm["SampleNo"].astype(str) == f_sno]

        refs_fc = sorted([r for r in df_pm["ref"].dropna().astype(str).unique()
                          if r not in ("-","nan","")])
        ref_opts_fc = ["— Pilih Ref / Point —"] + refs_fc
        if st.session_state.get("fc_ref") not in ref_opts_fc:
            st.session_state["fc_ref"] = "— Pilih Ref / Point —"

        cur_ref_fc = st.session_state.get("fc_ref", "— Pilih Ref / Point —")
        df_pm_ref  = df_pm[df_pm["ref"].astype(str)==cur_ref_fc] if cur_ref_fc != "— Pilih Ref / Point —" else df_pm
        params_fc  = sorted([p for p in df_pm_ref[param_col].dropna().astype(str).unique()
                              if p not in ("","nan","-")])
        param_opts_fc = ["— Pilih Parameter —"] + params_fc
        if st.session_state.get("fc_param") not in param_opts_fc:
            st.session_state["fc_param"] = "— Pilih Parameter —"

        c4, c5 = st.columns([1.5, 2.5], gap="small")
        with c4:
            f_ref   = st.selectbox("📍 Ref / Point", ref_opts_fc, key="fc_ref")
        with c5:
            f_param = st.selectbox("📐 Parameter",   param_opts_fc, key="fc_param")

        if f_combo_fc == "— Pilih Part & Model —" or f_ref == "— Pilih Ref / Point —" or f_param == "— Pilih Parameter —":
            st.info("Pilih Part · Model, Ref, dan Parameter untuk melanjutkan.")
            return

        if not f_ref or not f_param:
            st.info("Pilih Ref dan Parameter untuk melanjutkan.")
            return

        df_sel = df_pm[df_pm["ref"].astype(str)==f_ref]
        df_sel = df_sel[df_sel[param_col].astype(str)==f_param]
        df_sel = df_sel.sort_values(["Date","Shift","Cycle"]).dropna(subset=["Deviation"])

        if len(df_sel) < 10:
            st.warning(f"Data terlalu sedikit ({len(df_sel)} observasi). Minimal 10 diperlukan.")
            return

        nominal  = float(df_sel["Nominal"].iloc[0])
        utol     = float(df_sel["Uppertol"].iloc[0])
        ltol     = float(df_sel["Lowertol"].iloc[0])
        usl      = round(nominal + utol, 5)
        lsl      = round(nominal + ltol, 5)
        y_dev    = df_sel["Deviation"].tolist()

        # KPI historis
        n_ok  = int((df_sel["Judgement"]=="OK").sum())
        n_ng  = int((df_sel["Judgement"]=="NG").sum())
        n_tot = len(df_sel)
        pct_ok= round(n_ok/n_tot*100,1)

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0 16px;">'
            + "".join([
                f'<div style="background:{bg};border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="font-size:16px;font-weight:700;color:{fc};">{val}</div>'
                f'<div style="font-size:10px;color:#64748B;">{lbl}</div></div>'
                for bg, fc, val, lbl in [
                    ("#F8FAFC","#0F172A",n_tot,"n historis"),
                    ("#F0FDF4","#16A34A",f"{pct_ok}%","% OK"),
                    ("#FEF2F2","#DC2626",n_ng,"NG"),
                    ("#F8FAFC","#3B82F6",nominal,"Nominal"),
                    ("#F8FAFC","#334155",f"+{utol} / {ltol}","Toleransi"),
                ]
            ])
            + '</div>', unsafe_allow_html=True
        )

        if st.button("▶ Run Forecast", type="primary", key="fc_run"):
            st.session_state["fc_result"] = None
            with st.spinner(f"Fitting ARIMA untuk {f_ref} · {f_param}..."):
                result = self._run_arima(y_dev, int(fc_n))
            st.session_state["fc_result"]  = result
            st.session_state["fc_meta"]    = {
                "y_dev": y_dev, "nominal": nominal, "usl": usl, "lsl": lsl,
                "utol": utol, "ltol": ltol, "ref": f_ref, "param": f_param
            }

        result = st.session_state.get("fc_result")
        meta   = st.session_state.get("fc_meta", {})
        if not result:
            return

        if "error" in result:
            st.error(f"ARIMA gagal: {result['error']}")
            return

        fc    = result["fc"]
        ci    = result["ci"]
        order = result["order"]
        y_dev_m = meta.get("y_dev", y_dev)
        nom_m   = meta.get("nominal", nominal)
        usl_m   = meta.get("usl", usl)
        lsl_m   = meta.get("lsl", lsl)
        utol_m  = meta.get("utol", utol)
        ltol_m  = meta.get("ltol", ltol)

        # Prediksi NG
        fc_ng  = [i+1 for i,v in enumerate(fc) if v > utol_m or v < ltol_m]
        fc_act = [round(v + nom_m, 5) for v in fc]
        fc_lo  = [round(v + nom_m, 5) for v in ci[:,0]]
        fc_hi  = [round(v + nom_m, 5) for v in ci[:,1]]

        # Status badge
        if fc_ng:
            risk_html = (f'<span style="background:#FEE2E2;color:#DC2626;font-size:11px;'
                         f'font-weight:700;padding:3px 10px;border-radius:99px;">'
                         f'⚠ Diprediksi NG pada shift ke-{fc_ng[0]}</span>')
        else:
            risk_html = (f'<span style="background:#DCFCE7;color:#16A34A;font-size:11px;'
                         f'font-weight:700;padding:3px 10px;border-radius:99px;">'
                         f'✓ Tidak ada prediksi NG dalam {int(fc_n)} shift</span>')

        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'margin-bottom:8px;">'
            f'<span style="font-size:13px;font-weight:700;color:#0F172A;">'
            f'ARIMA{order} — {meta.get("ref","?")} · {meta.get("param","?")}</span>'
            f'{risk_html}</div>',
            unsafe_allow_html=True
        )

        # Chart ECharts
        hist_n  = len(y_dev_m)
        x_hist  = list(range(hist_n))
        x_fc    = list(range(hist_n, hist_n + int(fc_n)))
        act_hist= [round(v + nom_m, 5) for v in y_dev_m]

        # Hitung Y range dari data aktual + forecast + toleransi
        all_vals = act_hist + fc_act + fc_lo + fc_hi + [usl_m, lsl_m]
        all_vals = [v for v in all_vals if v is not None]
        y_min = round(min(all_vals) - abs(utol_m) * 0.5, 4)
        y_max = round(max(all_vals) + abs(utol_m) * 0.5, 4)

        from streamlit_echarts import st_echarts as _ech
        _ech({
            "tooltip": {"trigger": "axis"},
            "legend": {"data": ["Aktual","Forecast","CI 95%"],
                       "bottom": 0, "icon": "circle", "itemWidth": 8},
            "grid": {"top": 16, "bottom": 44, "left": 56, "right": 80},
            "xAxis": {"type": "category",
                      "data": x_hist + x_fc,
                      "axisLabel": {"formatter": "shift {value}", "fontSize": 9}},
            "yAxis": {"type": "value", "min": y_min, "max": y_max,
                      "axisLabel": {"fontSize": 9}},
            "dataZoom": [{"type": "inside"}, {"type": "slider", "bottom": 8, "height": 16}],
            "series": [
                {"name": "Aktual", "type": "line",
                 "data": act_hist + [None]*int(fc_n),
                 "itemStyle": {"color": "#6366F1"}, "lineStyle": {"width": 1.5},
                 "symbol": "none"},
                {"name": "Forecast", "type": "line",
                 "data": [None]*hist_n + fc_act,
                 "itemStyle": {"color": "#F59E0B"},
                 "lineStyle": {"width": 2, "type": "dashed"},
                 "symbol": "none"},
                {"name": "CI 95%", "type": "line",
                 "data": [None]*hist_n + fc_hi,
                 "lineStyle": {"opacity": 0},
                 "areaStyle": {"color": "#F59E0B", "opacity": 0.15},
                 "stack": "ci", "symbol": "none"},
                {"name": "CI Low", "type": "line",
                 "data": [None]*hist_n + fc_lo,
                 "lineStyle": {"opacity": 0},
                 "areaStyle": {"color": "#F59E0B", "opacity": 0},
                 "stack": "ci", "symbol": "none"},
                {"name": "USL", "type": "line",
                 "data": [usl_m] * (hist_n + int(fc_n)),
                 "lineStyle": {"color": "#EF4444", "width": 1, "type": "dashed"},
                 "itemStyle": {"color": "#EF4444"}, "symbol": "none"},
                {"name": "LSL", "type": "line",
                 "data": [lsl_m] * (hist_n + int(fc_n)),
                 "lineStyle": {"color": "#EF4444", "width": 1, "type": "dashed"},
                 "itemStyle": {"color": "#EF4444"}, "symbol": "none"},
            ],
        }, height="360px", key="fc_chart")

        # Tabel forecast
        df_fc = pd.DataFrame({
            "Shift ke":        range(1, int(fc_n)+1),
            "Pred. Actual":    fc_act,
            "Lower 95%":       fc_lo,
            "Upper 95%":       fc_hi,
            "Pred. Deviation": [round(v, 5) for v in fc],
            "Status":          ["NG" if (v > utol_m or v < ltol_m) else "OK" for v in fc],
        })
        st.dataframe(df_fc, use_container_width=True, hide_index=True,
                     height=min(400, 42 + len(df_fc)*36))


    @st.fragment
    def _render_klasifikasi(self):
        import joblib, json
        from pathlib import Path as _Path
        from datetime import date as _date, datetime as _dt

        MODEL_DIR = _Path("models")

        # ── Deteksi shift berikutnya ──────────────────────────────
        try:
            import pytz
            now = _dt.now(pytz.timezone("Asia/Jakarta"))
        except Exception:
            now = _dt.now()
        hour = now.hour
        if 7 <= hour < 16:
            cur_shift, next_shift, next_date = 1, 2, _date.today()
        elif 16 <= hour < 24:
            cur_shift, next_shift, next_date = 2, 3, _date.today()
        else:
            cur_shift, next_shift, next_date = 3, 1, _date.today()

        st.markdown(
            f'<div style="background:#EFF6FF;border-radius:8px;padding:12px 16px;'
            f'margin-bottom:16px;display:flex;justify-content:space-between;align-items:center;">'
            f'<div><div style="font-size:13px;font-weight:700;color:#1D4ED8;">Prediksi Shift Berikutnya</div>'
            f'<div style="font-size:11px;color:#3B82F6;margin-top:2px;">'
            f'Shift {cur_shift} sedang berjalan → memprediksi <b>Shift {next_shift} · '
            f'{next_date.strftime("%d %b %Y")}</b></div></div>'
            f'<div style="font-size:22px;">🔮</div></div>',
            unsafe_allow_html=True
        )

        model_files = sorted(MODEL_DIR.glob("xgb_*.pkl")) if MODEL_DIR.exists() else []
        if not model_files:
            st.warning(f"Tidak ada model di folder `{MODEL_DIR}/`.")
            return

        # ── Session state cache — hindari serialisasi JSON ────────
        import time as _time
        cache_key = f"cls_result_{next_shift}_{next_date.isoformat()}"
        ts_key    = f"{cache_key}_ts"
        TTL       = 300
        if cache_key not in st.session_state or \
           _time.time() - st.session_state.get(ts_key, 0) > TTL:
            all_results = []
            with st.spinner("Memuat prediksi model..."):
                df = self.df_all
                for mp in model_files:
                    stem = mp.stem.replace("xgb_", "")
                    ep   = MODEL_DIR / f"encoders_{stem}.pkl"
                    ip   = MODEL_DIR / f"model_info_{stem}.json"
                    if not ep.exists() or not ip.exists():
                        continue
                    try:
                        xgb_model = joblib.load(mp)
                        encoders  = joblib.load(ep)
                        with open(ip) as fi:
                            minfo = json.load(fi)
                    except Exception:
                        continue

                    threshold = minfo.get("optimal_threshold", 0.5)
                    features  = minfo.get("features", [])
                    f_part    = minfo.get("part", "")
                    f_model   = minfo.get("model_name", "")

                    df_ref = df[
                        (df["PartName"]==f_part) & (df["ModelName"]==f_model)
                    ][["PartName","ModelName","SampleNo","CMMName","Parameter",
                       "Category","ref","point","Nominal","Uppertol","Lowertol","KP"]
                      ].drop_duplicates().copy()
                    if df_ref.empty:
                        continue

                    df_ref["Shift"]       = next_shift
                    df_ref["Cycle"]       = 1
                    df_ref["DayOfWeek"]   = next_date.weekday()
                    df_ref["Hour"]        = 7 if next_shift==1 else (16 if next_shift==2 else 0)
                    df_ref["DayOfMonth"]  = next_date.day
                    df_ref["WeekOfYear"]  = int(next_date.isocalendar()[1])
                    df_ref["TolRange"]    = df_ref["Uppertol"] - df_ref["Lowertol"]
                    df_ref["TolMidpoint"] = (df_ref["Uppertol"] + df_ref["Lowertol"]) / 2

                    for col in ["PartName","ModelName","SampleNo","CMMName",
                                "Parameter","Category","ref","point"]:
                        le = encoders.get(col)
                        if le:
                            known = set(le.classes_)
                            df_ref[col+"_enc"] = df_ref[col].astype(str).apply(
                                lambda x: le.transform([x])[0] if x in known else -1
                            )
                        else:
                            df_ref[col+"_enc"] = 0

                    try:
                        proba = xgb_model.predict_proba(df_ref[features].fillna(0))[:,1]
                    except Exception:
                        continue

                    df_ref["Prob_NG"] = (proba * 100).round(1)
                    df_ref["Pred"]    = ["NG" if p >= threshold else "OK" for p in proba]
                    df_ref["Risiko"]  = df_ref["Prob_NG"].apply(
                        lambda p: "🔴 Tinggi" if p >= threshold*100 else
                                  ("🟡 Sedang" if p >= 30 else "🟢 Rendah")
                    )
                    all_results.append(df_ref)

            if not all_results:
                st.info("Tidak ada hasil prediksi.")
                return
            st.session_state[cache_key] = pd.concat(all_results, ignore_index=True)
            st.session_state[ts_key]    = _time.time()

        result = st.session_state[cache_key]

        # ── Filter Baris 1: Risiko (pills) tetap di atas ──
        st.markdown('<div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">🎯 Tingkat Risiko</div>', unsafe_allow_html=True)
        f_risk = st.pills(
            "Tingkat Risiko",
            ["Semua Risiko", "Prediksi NG", "🔴 Tinggi", "🟡 Sedang", "🟢 Rendah"],
            default="🔴 Tinggi", key="cls_filter",
            selection_mode="single", label_visibility="collapsed",
        ) or "Semua Risiko"

        # ── Filter Baris 2: Part·Model | Kategori | Sample No (selectbox cascade) ──
        combos_cls = (
            result[["PartName","ModelName"]].drop_duplicates()
            .sort_values(["PartName","ModelName"])
        )
        combo_cls_opts = ["— Semua Part & Model —"] + [
            f"{r.PartName} · {r.ModelName}" for _, r in combos_cls.iterrows()
        ]
        if st.session_state.get("cls_combo") not in combo_cls_opts:
            st.session_state["cls_combo"] = "— Semua Part & Model —"

        cur_cls_combo = st.session_state.get("cls_combo", "— Semua Part & Model —")
        df_cls_combo  = result.copy()
        if cur_cls_combo != "— Semua Part & Model —":
            _sp = cur_cls_combo.split(" · ", 1)
            if len(_sp) == 2:
                df_cls_combo = result[(result["PartName"]==_sp[0])&(result["ModelName"]==_sp[1])]

        cat_cls_vals = sorted(df_cls_combo["Category"].dropna().unique().tolist()) if "Category" in df_cls_combo.columns else []
        cat_cls_opts = ["Semua Kategori"] + cat_cls_vals
        if st.session_state.get("cls_cat") not in cat_cls_opts:
            st.session_state["cls_cat"] = "Produksi" if "Produksi" in cat_cls_opts else "Semua Kategori"

        cur_cls_cat = st.session_state.get("cls_cat", "Semua Kategori")
        df_cls_cat  = df_cls_combo[df_cls_combo["Category"]==cur_cls_cat] if cur_cls_cat != "Semua Kategori" and "Category" in df_cls_combo.columns else df_cls_combo

        sno_cls_vals = sorted(
            df_cls_cat["SampleNo"].dropna().astype(str).unique().tolist(),
            key=lambda s: (0, int(s)) if s.isdigit() else (1, s)
        )
        sno_cls_opts = ["Semua Sample"] + sno_cls_vals
        if st.session_state.get("cls_sno") not in sno_cls_opts:
            st.session_state["cls_sno"] = "Semua Sample"

        # ── KP → ref → param (cascade dari sno) ──────────────
        cur_cls_sno = st.session_state.get("cls_sno", "Semua Sample")
        df_cls_sno  = df_cls_cat[df_cls_cat["SampleNo"].astype(str)==cur_cls_sno] if cur_cls_sno != "Semua Sample" else df_cls_cat

        _ref_col_cls   = "ref"   if "ref"   in df_cls_sno.columns else "PartName"
        _param_col_cls = "point" if "point" in df_cls_sno.columns else "Parameter"

        ref_cls_vals = sorted([r for r in df_cls_sno[_ref_col_cls].dropna().astype(str).unique() if r not in ("","-","nan")])
        ref_cls_opts = ["Semua Ref / Point"] + ref_cls_vals
        if st.session_state.get("cls_ref") not in ref_cls_opts:
            st.session_state["cls_ref"] = "Semua Ref / Point"

        cur_cls_ref  = st.session_state.get("cls_ref", "Semua Ref / Point")
        df_cls_ref   = df_cls_sno[df_cls_sno[_ref_col_cls].astype(str)==cur_cls_ref] if cur_cls_ref != "Semua Ref / Point" else df_cls_sno

        param_cls_vals = sorted([p for p in df_cls_ref[_param_col_cls].dropna().astype(str).unique() if p not in ("","-","nan")])
        param_cls_opts = ["Semua Parameter"] + param_cls_vals
        if st.session_state.get("cls_param") not in param_cls_opts:
            st.session_state["cls_param"] = "Semua Parameter"

        kp_cls_opts = ["Semua Titik", "KP Only"]
        if st.session_state.get("cls_kp") not in kp_cls_opts:
            st.session_state["cls_kp"] = "Semua Titik"

        cls_r2c1, cls_r2c2, cls_r2c3 = st.columns([2.5, 1.4, 1.2], gap="small")
        with cls_r2c1:
            f_combo_cls = st.selectbox("🔩 Part · Model", combo_cls_opts, key="cls_combo")
        with cls_r2c2:
            f_cat = st.selectbox("🏷 Kategori", cat_cls_opts, key="cls_cat")
        with cls_r2c3:
            f_sno_cls = st.selectbox("🔢 Sample No", sno_cls_opts, key="cls_sno")

        cls_r3c1, cls_r3c2, cls_r3c3 = st.columns([1.2, 1.5, 2.5], gap="small")
        with cls_r3c1:
            f_kp_cls = st.selectbox("⚠ Kritikal Point", kp_cls_opts, key="cls_kp")
        with cls_r3c2:
            f_ref_cls = st.selectbox("📍 Ref / Point", ref_cls_opts, key="cls_ref")
        with cls_r3c3:
            f_param_cls = st.selectbox("📐 Parameter", param_cls_opts, key="cls_param")

        # Terapkan semua filter
        df_filtered = result.copy()
        if f_risk == "Prediksi NG":
            df_filtered = df_filtered[df_filtered["Pred"]=="NG"]
        elif f_risk != "Semua Risiko":
            df_filtered = df_filtered[df_filtered["Risiko"]==f_risk]
        if f_combo_cls != "— Semua Part & Model —":
            _sp = f_combo_cls.split(" · ", 1)
            if len(_sp) == 2:
                df_filtered = df_filtered[(df_filtered["PartName"]==_sp[0])&(df_filtered["ModelName"]==_sp[1])]
        if f_cat != "Semua Kategori" and "Category" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["Category"]==f_cat]
        if f_sno_cls != "Semua Sample":
            df_filtered = df_filtered[df_filtered["SampleNo"].astype(str)==f_sno_cls]
        if f_kp_cls == "KP Only" and "KP" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["KP"].astype(str).isin(["1","1.0","True"])]
        if f_ref_cls != "Semua Ref / Point" and _ref_col_cls in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[_ref_col_cls].astype(str)==f_ref_cls]
        if f_param_cls != "Semua Parameter" and _param_col_cls in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[_param_col_cls].astype(str)==f_param_cls]

        df_show = df_filtered.copy()

        # ── KPI responsif filter ──────────────────────────────────
        n_ng   = int((df_show["Pred"]=="NG").sum())
        n_ok   = int((df_show["Pred"]=="OK").sum())
        n_tot  = len(df_show)
        n_high = int(df_show["Risiko"].str.startswith("🔴").sum())

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px;">'
            + "".join([
                f'<div style="background:{bg};border-radius:8px;padding:12px;text-align:center;">'
                f'<div style="font-size:22px;font-weight:700;color:{fc};">{val}</div>'
                f'<div style="font-size:10px;color:#64748B;">{lbl}</div></div>'
                for bg, fc, val, lbl in [
                    ("#F8FAFC","#0F172A",n_tot,"Total Titik"),
                    ("#FEF2F2","#DC2626",n_ng,"Prediksi NG"),
                    ("#F0FDF4","#16A34A",n_ok,"Prediksi OK"),
                    ("#FFFBEB","#D97706",n_high,"Risiko Tinggi"),
                ]
            ])
            + '</div>', unsafe_allow_html=True
        )

        if n_ng > 0:
            st.error(f"⚠️ **{n_ng} titik** diprediksi NG pada "
                     f"Shift {next_shift} · {next_date.strftime('%d %b %Y')}")

        sc = ["PartName","ModelName","ref","point","SampleNo","KP","Prob_NG","Pred","Risiko"]
        sc = [c for c in sc if c in df_show.columns]
        df_tbl = df_show[sc].sort_values("Prob_NG", ascending=False).reset_index(drop=True)
        _col_rename = {"PartName":"Part","ModelName":"Model","ref":"Ref","point":"Parameter",
                       "SampleNo":"Sample No","KP":"KP","Prob_NG":"Prob NG (%)","Pred":"Prediksi","Risiko":"Risiko"}
        df_tbl.columns = [_col_rename.get(c,c) for c in sc]
        st.dataframe(df_tbl, use_container_width=True, hide_index=True,
                     height=min(520, 42 + len(df_tbl)*36))

    def _render_forecast_batch(self, cache_path):

        st.markdown(
            '<div style="font-size:13px;font-weight:600;color:#0F172A;margin-bottom:12px;">'
            'Batch Forecast — Semua Kombinasi</div>',
            unsafe_allow_html=True
        )

        has_cache = Path(cache_path).exists()
        cc1, cc2 = st.columns([3,1], gap="small")
        with cc2:
            if st.button("🔄 Generate / Perbarui Forecast", use_container_width=True,
                         type="primary" if not has_cache else "secondary",
                         key="fc_batch_run"):
                self._run_batch_arima(cache_path)
                st.rerun()

        if not has_cache:
            st.info("Belum ada hasil batch. Klik 'Generate Forecast' untuk memulai (bisa memakan beberapa menit).")
            return

        df_batch = pd.read_csv(cache_path)
        n_total  = len(df_batch)
        n_risk   = int((df_batch["Prediksi_NG_Shift"]>0).sum())
        n_stable = n_total - n_risk

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px;">'
            + "".join([
                f'<div style="background:{bg};border-radius:8px;padding:12px;text-align:center;">'
                f'<div style="font-size:22px;font-weight:700;color:{fc};">{val}</div>'
                f'<div style="font-size:10px;color:#64748B;">{lbl}</div></div>'
                for bg, fc, val, lbl in [
                    ("#F8FAFC","#0F172A",n_total,"Total Kombinasi"),
                    ("#FEF2F2","#DC2626",n_risk,"Berisiko NG"),
                    ("#F0FDF4","#16A34A",n_stable,"Stabil"),
                ]
            ])
            + '</div>', unsafe_allow_html=True
        )

        # Filter
        f_risk = st.pills("Filter", ["Semua","Berisiko NG","Stabil"],
                           default="Berisiko NG", key="batch_filter",
                           selection_mode="single", label_visibility="collapsed") or "Berisiko NG"
        if f_risk == "Berisiko NG":
            df_show = df_batch[df_batch["Prediksi_NG_Shift"]>0].sort_values("Prediksi_NG_Shift")
        elif f_risk == "Stabil":
            df_show = df_batch[df_batch["Prediksi_NG_Shift"]==0]
        else:
            df_show = df_batch

        cols_show = ["Part","Model","SampleNo","Ref","Point",
                     "ARIMA_Order","Tren","Prediksi_NG_Shift","Status"]
        cols_show = [c for c in cols_show if c in df_show.columns]
        st.dataframe(df_show[cols_show].reset_index(drop=True),
                     use_container_width=True, hide_index=True,
                     height=min(500, 42 + len(df_show)*36))

    # ═════════════════════════════════════════════════════════════════
    #  📐 PREDIKSI RULE — Linear Trend + Toleransi
    # ═════════════════════════════════════════════════════════════════
    @st.fragment
    def _render_prediksi_rule(self):
        import numpy as np
        from datetime import date as _date, datetime as _dt

        st.markdown(
            '<div style="background:#F0FDF4;border-radius:8px;padding:12px 16px;'
            'margin-bottom:16px;display:flex;justify-content:space-between;align-items:center;">'
            '<div>'
            '<div style="font-size:13px;font-weight:700;color:#166534;">📐 Prediksi Rule SPC — Linear Trend</div>'
            '<div style="font-size:11px;color:#16A34A;margin-top:2px;">'
            'Proyeksikan tren nilai aktual ke depan, deteksi pelanggaran rule sebelum terjadi</div>'
            '</div>'
            '<div style="font-size:22px;">📐</div></div>',
            unsafe_allow_html=True
        )

        df = self.df_all
        param_col = "point" if "point" in df.columns else "Parameter"
        ref_col   = "ref"   if "ref"   in df.columns else "ID"

        # ── Filter Baris 1: Part·Model | Kategori | KP ───────────
        combos_pr = (
            df[["PartName","ModelName"]].dropna().drop_duplicates()
            .sort_values(["PartName","ModelName"])
        )
        combo_pr_opts = ["— Pilih Part & Model —"] + [
            f"{r.PartName} · {r.ModelName}" for _, r in combos_pr.iterrows()
        ]
        if st.session_state.get("pr_combo") not in combo_pr_opts:
            st.session_state["pr_combo"] = "— Pilih Part & Model —"

        cur_pr_combo = st.session_state.get("pr_combo", "— Pilih Part & Model —")
        df_pr_combo  = df.copy()
        if cur_pr_combo != "— Pilih Part & Model —":
            _sp = cur_pr_combo.split(" · ", 1)
            if len(_sp) == 2:
                df_pr_combo = df[(df["PartName"]==_sp[0])&(df["ModelName"]==_sp[1])]

        cat_pr_vals = sorted(df_pr_combo["Category"].dropna().unique().tolist()) if "Category" in df_pr_combo.columns else []
        cat_pr_opts = ["Semua Kategori"] + cat_pr_vals
        if st.session_state.get("pr_cat") not in cat_pr_opts:
            st.session_state["pr_cat"] = "Produksi" if "Produksi" in cat_pr_opts else "Semua Kategori"

        cur_pr_cat = st.session_state.get("pr_cat", "Semua Kategori")
        df_pr_cat  = df_pr_combo[df_pr_combo["Category"]==cur_pr_cat] if cur_pr_cat != "Semua Kategori" and "Category" in df_pr_combo.columns else df_pr_combo

        kp_pr_opts = ["Semua Titik", "KP Only"]
        if st.session_state.get("pr_kp") not in kp_pr_opts:
            st.session_state["pr_kp"] = "Semua Titik"

        pr_r1c1, pr_r1c2, pr_r1c3 = st.columns([2.5, 1.4, 1.2], gap="small")
        with pr_r1c1:
            f_pr_combo = st.selectbox("🔩 Part · Model", combo_pr_opts, key="pr_combo")
        with pr_r1c2:
            f_pr_cat = st.selectbox("🏷 Kategori", cat_pr_opts, key="pr_cat")
        with pr_r1c3:
            f_pr_kp = st.selectbox("⚠ Kritikal Point", kp_pr_opts, key="pr_kp")

        # ── Filter Baris 2: SampleNo | Ref/Point | Parameter ─────
        # Cascade dari combo+cat
        df_pr_filt = df_pr_cat.copy()
        if f_pr_combo != "— Pilih Part & Model —":
            _sp = f_pr_combo.split(" · ", 1)
            if len(_sp) == 2:
                df_pr_filt = df_pr_cat[(df_pr_cat["PartName"]==_sp[0])&(df_pr_cat["ModelName"]==_sp[1])]
        if f_pr_cat != "Semua Kategori" and "Category" in df_pr_filt.columns:
            df_pr_filt = df_pr_filt[df_pr_filt["Category"]==f_pr_cat]
        if f_pr_kp == "KP Only" and "KP" in df_pr_filt.columns:
            df_pr_filt = df_pr_filt[df_pr_filt["KP"].astype(str).isin(["1","1.0","True"])]

        sno_pr_vals = sorted(
            df_pr_filt["SampleNo"].dropna().astype(str).unique().tolist(),
            key=lambda s: (0, int(s)) if s.isdigit() else (1, s)
        )
        sno_pr_opts = ["Semua Sample"] + sno_pr_vals
        if st.session_state.get("pr_sno") not in sno_pr_opts:
            st.session_state["pr_sno"] = "Semua Sample"

        cur_pr_sno  = st.session_state.get("pr_sno", "Semua Sample")
        df_pr_sno   = df_pr_filt[df_pr_filt["SampleNo"].astype(str)==cur_pr_sno] if cur_pr_sno != "Semua Sample" else df_pr_filt

        ref_pr_vals = sorted([r for r in df_pr_sno[ref_col].dropna().astype(str).unique() if r not in ("","-","nan")])
        ref_pr_opts = ["— Pilih Ref / Point —"] + ref_pr_vals
        if st.session_state.get("pr_ref") not in ref_pr_opts:
            st.session_state["pr_ref"] = "— Pilih Ref / Point —"

        cur_pr_ref   = st.session_state.get("pr_ref", "— Pilih Ref / Point —")
        df_pr_ref    = df_pr_sno[df_pr_sno[ref_col].astype(str)==cur_pr_ref] if cur_pr_ref != "— Pilih Ref / Point —" else df_pr_sno
        param_pr_vals= sorted([p for p in df_pr_ref[param_col].dropna().astype(str).unique() if p not in ("","-","nan")])
        param_pr_opts= ["— Pilih Parameter —"] + param_pr_vals
        if st.session_state.get("pr_param") not in param_pr_opts:
            st.session_state["pr_param"] = "— Pilih Parameter —"

        pr_r2c1, pr_r2c2, pr_r2c3 = st.columns([1.2, 1.5, 2.5], gap="small")
        with pr_r2c1:
            f_pr_sno   = st.selectbox("🔢 Sample No",   sno_pr_opts,   key="pr_sno")
        with pr_r2c2:
            f_pr_ref   = st.selectbox("📍 Ref / Point", ref_pr_opts,   key="pr_ref")
        with pr_r2c3:
            f_pr_param = st.selectbox("📐 Parameter",   param_pr_opts, key="pr_param")

        # ── Setting horizon ───────────────────────────────────────
        pr_r3c1, pr_r3c2, pr_r3c3 = st.columns([1.5, 1.5, 3], gap="small")
        with pr_r3c1:
            n_hist   = st.number_input("📊 Data historis (shift)", min_value=10, max_value=100, value=20, step=5, key="pr_n_hist",
                                        help="Jumlah data terakhir yang dipakai untuk hitung tren")
        with pr_r3c2:
            n_fc     = st.number_input("🔭 Prediksi ke depan (shift)", min_value=1, max_value=50, value=10, step=1, key="pr_n_fc")

        if f_pr_combo == "— Pilih Part & Model —" or f_pr_ref == "— Pilih Ref / Point —" or f_pr_param == "— Pilih Parameter —":
            st.info("Pilih Part · Model, Ref/Point, dan Parameter untuk menjalankan prediksi.")
            return

        # ── Ambil data terfilter ──────────────────────────────────
        df_sel = df_pr_filt.copy()
        if f_pr_sno != "Semua Sample":
            df_sel = df_sel[df_sel["SampleNo"].astype(str)==f_pr_sno]
        df_sel = df_sel[df_sel[ref_col].astype(str)==f_pr_ref]
        df_sel = df_sel[df_sel[param_col].astype(str)==f_pr_param]
        df_sel = df_sel.sort_values(["Date","Shift","Cycle"]).dropna(subset=["Actual"])

        if len(df_sel) < 10:
            st.warning(f"Data terlalu sedikit ({len(df_sel)} poin). Minimal 10 diperlukan.")
            return

        # Ambil n_hist data terakhir untuk hitung tren
        df_hist_sel = df_sel.tail(int(n_hist)).reset_index(drop=True)
        y_hist      = df_hist_sel["Actual"].tolist()
        n           = len(y_hist)

        nominal  = float(df_hist_sel["Nominal"].dropna().iloc[0])  if df_hist_sel["Nominal"].notna().any()  else 0.0
        uppertol = float(df_hist_sel["Uppertol"].dropna().iloc[0]) if df_hist_sel["Uppertol"].notna().any() else 0.0
        lowertol = float(df_hist_sel["Lowertol"].dropna().iloc[0]) if df_hist_sel["Lowertol"].notna().any() else 0.0
        usl      = round(nominal + uppertol, 5)
        lsl      = round(nominal + lowertol, 5)

        # ── Linear Regression tren ────────────────────────────────
        x_hist    = np.arange(n)
        slope, intercept = np.polyfit(x_hist, y_hist, 1)

        # Residual → confidence interval
        y_fit     = slope * x_hist + intercept
        residuals = np.array(y_hist) - y_fit
        std_res   = float(np.std(residuals, ddof=1)) if n > 2 else 0.0

        # Proyeksikan n_fc shift ke depan
        x_fc      = np.arange(n, n + int(n_fc))
        y_fc      = slope * x_fc + intercept
        y_fc_hi   = y_fc + 1.96 * std_res
        y_fc_lo   = y_fc - 1.96 * std_res

        # ── Deteksi rule pada sequence historis + forecast ────────
        y_combined = y_hist + y_fc.tolist()
        vbr_combined = _detect_kendali(y_combined)

        # Pisahkan: violation di zona historis vs zona forecast
        hist_violations: dict[int, set] = {r: set() for r in range(1,8)}
        fc_violations:   dict[int, set] = {r: set() for r in range(1,8)}
        for rule_num, idxs in vbr_combined.items():
            for idx in idxs:
                if idx < n:
                    hist_violations[rule_num].add(idx)
                else:
                    fc_violations[rule_num].add(idx - n)  # index relatif ke forecast

        # ── KPI ───────────────────────────────────────────────────
        n_fc_ng      = sum(1 for v in y_fc if v > usl or v < lsl)
        n_fc_rule    = sum(1 for r in range(1,8) if fc_violations[r])
        slope_str    = f"{slope:+.5f} mm/shift"
        trend_lbl    = "📈 Naik" if slope > 0 else ("📉 Turun" if slope < 0 else "➡ Stabil")
        trend_clr    = "#DC2626" if abs(slope) > std_res * 0.3 else "#16A34A"

        # Estimasi shift sampai lewat batas (kalau ada tren)
        shifts_to_usl = int((usl - y_hist[-1]) / slope) if slope > 1e-9 else None
        shifts_to_lsl = int((lsl - y_hist[-1]) / slope) if slope < -1e-9 else None
        batas_info    = ""
        if shifts_to_usl is not None and 0 < shifts_to_usl <= 50:
            batas_info = f"⚠ Diprediksi lewat USL dalam ~{shifts_to_usl} shift"
        elif shifts_to_lsl is not None and 0 < shifts_to_lsl <= 50:
            batas_info = f"⚠ Diprediksi lewat LSL dalam ~{shifts_to_lsl} shift"

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0 16px;">'
            + "".join([
                f'<div style="background:{bg};border-radius:8px;padding:10px;text-align:center;">'
                f'<div style="font-size:15px;font-weight:700;color:{fc};">{val}</div>'
                f'<div style="font-size:10px;color:#64748B;margin-top:2px;">{lbl}</div></div>'
                for bg, fc, val, lbl in [
                    ("#F8FAFC", "#0F172A",      n,              "Data historis"),
                    ("#F8FAFC", trend_clr,      trend_lbl,      "Tren"),
                    ("#F8FAFC", trend_clr,      slope_str,      "Slope"),
                    ("#FEF2F2", "#DC2626",       n_fc_ng,        "Prediksi NG"),
                    ("#FFFBEB", "#D97706",       n_fc_rule,      "Rule terpicu (forecast)"),
                ]
            ])
            + '</div>',
            unsafe_allow_html=True
        )

        if batas_info:
            st.warning(batas_info)

        # ── Chart ─────────────────────────────────────────────────
        RC_CLR = {1:"#EF4444",2:"#F59E0B",3:"#8B5CF6",
                  4:"#06B6D4",5:"#10B981",6:"#F97316",7:"#3B82F6"}

        x_labels_hist = df_hist_sel.apply(
            lambda r: f"{r['Date'].strftime('%d/%m')} S{r['Shift']}", axis=1
        ).tolist()
        x_labels_fc   = [f"F+{i+1}" for i in range(int(n_fc))]
        x_all         = x_labels_hist + x_labels_fc

        # Warnai titik historis berdasarkan rule violation
        def _pt_style_hist(i):
            for r in [1,2,3,4,5,6,7]:
                if i in hist_violations[r]:
                    return {"value": y_hist[i], "itemStyle": {"color": "#6366F1", "borderColor": RC_CLR[r], "borderWidth": 2.5}}
            return {"value": y_hist[i], "itemStyle": {"color": "#6366F1"}}

        # Warnai titik forecast berdasarkan rule violation
        def _pt_style_fc(i):
            v = float(y_fc[i])
            clr_pt = "#EF4444" if (v > usl or v < lsl) else "#F59E0B"
            for r in [1,2,3,4,5,6,7]:
                if i in fc_violations[r]:
                    return {"value": round(v,5), "itemStyle": {"color": clr_pt, "borderColor": RC_CLR[r], "borderWidth": 2.5}}
            return {"value": round(v,5), "itemStyle": {"color": clr_pt}}

        series_hist = [_pt_style_hist(i) for i in range(n)]
        series_fc   = [_pt_style_fc(i)   for i in range(int(n_fc))]

        # Hitung y range
        all_y_vals = y_hist + y_fc.tolist() + y_fc_hi.tolist() + y_fc_lo.tolist() + [usl, lsl]
        y_pad  = (max(all_y_vals) - min(all_y_vals)) * 0.15 or abs(uppertol) * 0.5 or 0.01
        y_min  = round(min(all_y_vals) - y_pad, 5)
        y_max  = round(max(all_y_vals) + y_pad, 5)

        # Tren line historis
        trend_line_hist = [round(float(slope * i + intercept), 5) for i in range(n)]
        trend_line_fc   = [round(float(v), 5) for v in y_fc]

        mark_lines = [
            {"yAxis": usl, "lineStyle": {"color":"#EF4444","width":2,"type":"solid"},
             "label": {"formatter":f"USL {usl}","fontSize":10,"color":"#EF4444"}},
            {"yAxis": lsl, "lineStyle": {"color":"#EF4444","width":2,"type":"solid"},
             "label": {"formatter":f"LSL {lsl}","fontSize":10,"color":"#EF4444"}},
            {"yAxis": nominal, "lineStyle": {"color":"#22C55E","width":1.5,"type":"dashed"},
             "label": {"formatter":f"Nom {nominal}","fontSize":10,"color":"#22C55E"}},
        ]

        st_echarts({
            "title": {
                "text": f"Linear Trend + Prediksi Rule — {f_pr_ref} · {f_pr_param}",
                "subtext": f"Abu-abu = historis · Kuning/Merah = forecast · Lingkar berwarna = rule violation",
                "left": 12, "top": 8,
                "textStyle": {"fontSize":13,"fontWeight":700,"color":"#0F172A"},
                "subtextStyle": {"color":"#94A3B8","fontSize":10},
            },
            "legend": {
                "data": ["Aktual","Tren Historis","Forecast","CI 95%"],
                "bottom": 0, "icon": "circle", "itemWidth": 8,
                "textStyle": {"fontSize":10},
            },
            "grid": {"top":60,"right":90,"bottom":50,"left":65},
            "tooltip": {"trigger":"axis","formatter":"{b}<br/>Nilai: <b>{c}</b>"},
            "xAxis": {
                "type":"category","data":x_all,
                "axisLabel":{"rotate":25,"fontSize":8,"interval":"auto"},
                "axisLine":{"lineStyle":{"color":"#E2E8F0"}},
                "axisTick":{"show":False},
                # Zona forecast — background beda
                "splitArea":{"show":False},
            },
            "yAxis": {
                "type":"value","min":y_min,"max":y_max,
                "axisLabel":{"fontSize":9},
                "splitLine":{"lineStyle":{"color":"#F1F5F9","type":"dashed"}},
            },
            "dataZoom": [{"type":"inside"},{"type":"slider","bottom":8,"height":16}],
            "visualMap": {
                "show": False,
                "pieces": [
                    {"min": n, "max": n + int(n_fc), "color": "#FFF7ED"},
                ],
                "seriesIndex": 0,
            },
            "series": [
                # Aktual historis
                {
                    "name":"Aktual","type":"line",
                    "data": series_hist + [None]*int(n_fc),
                    "symbol":"circle","symbolSize":7,
                    "lineStyle":{"color":"#6366F1","width":1.5},
                    "itemStyle":{"color":"#6366F1"},
                    "markLine":{"symbol":["none","none"],"silent":True,"data":mark_lines},
                },
                # Forecast titik
                {
                    "name":"Forecast","type":"line",
                    "data": [None]*n + series_fc,
                    "symbol":"circle","symbolSize":8,
                    "lineStyle":{"color":"#F59E0B","width":2,"type":"dashed"},
                    "itemStyle":{"color":"#F59E0B"},
                },
                # Tren line historis
                {
                    "name":"Tren Historis","type":"line",
                    "data": trend_line_hist + [None]*int(n_fc),
                    "symbol":"none",
                    "lineStyle":{"color":"#94A3B8","width":1.5,"type":"dotted"},
                    "itemStyle":{"color":"#94A3B8"},
                },
                # CI 95% upper
                {
                    "name":"CI 95%","type":"line",
                    "data": [None]*n + [round(float(v),5) for v in y_fc_hi],
                    "symbol":"none",
                    "lineStyle":{"opacity":0},
                    "areaStyle":{"color":"#F59E0B","opacity":0.12},
                    "stack":"ci",
                },
                # CI 95% lower
                {
                    "name":"CI Low","type":"line",
                    "data": [None]*n + [round(float(v),5) for v in y_fc_lo],
                    "symbol":"none",
                    "lineStyle":{"opacity":0},
                    "areaStyle":{"color":"#F59E0B","opacity":0},
                    "stack":"ci",
                },
            ],
        }, height="400px", key="pr_chart")

        # ── Legend warna rule ─────────────────────────────────────
        st.markdown("""
        <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:11px;color:#64748B;margin:6px 0 12px;">
          <span>Warna lingkaran titik = rule violation:</span>
          <span style="color:#EF4444;">● Rule 1</span>
          <span style="color:#F59E0B;">● Rule 2</span>
          <span style="color:#8B5CF6;">● Rule 3</span>
          <span style="color:#06B6D4;">● Rule 4</span>
          <span style="color:#10B981;">● Rule 5</span>
          <span style="color:#F97316;">● Rule 6</span>
          <span style="color:#3B82F6;">● Rule 7</span>
          <span style="color:#EF4444;">■ Titik merah = NG (lewat toleransi)</span>
        </div>
        """, unsafe_allow_html=True)

        # ── Tabel hasil prediksi rule ─────────────────────────────
        RULE_DESC = {
            1: "1 titik di luar ±3σ",
            2: "8 titik berurutan di satu sisi mean",
            3: "7 titik naik/turun terus",
            4: "14 titik bergantian naik-turun",
            5: "2 dari 3 titik > 2σ di satu sisi",
            6: "4 dari 5 titik > 1σ di satu sisi",
            7: "15 titik berurutan dalam ±1σ",
        }
        RULE_SEV = {1:"Critical",2:"Warning",3:"Warning",4:"Warning",5:"Warning",6:"Warning",7:"Warning"}
        RULE_CLR_SEV = {"Critical":"#FEF2F2","Warning":"#FFFBEB"}
        RULE_TXT_SEV = {"Critical":"#991B1B","Warning":"#92400E"}

        rows_rule = []
        for r_num in range(1,8):
            n_hist_v = len(hist_violations[r_num])
            n_fc_v   = len(fc_violations[r_num])
            if n_hist_v == 0 and n_fc_v == 0:
                continue
            rows_rule.append({
                "Rule":          f"Rule {r_num}",
                "Deskripsi":     RULE_DESC[r_num],
                "Severity":      RULE_SEV[r_num],
                "Titik Historis":n_hist_v,
                "Titik Forecast":n_fc_v,
                "Status":        "⚠ Prediksi Terpicu" if n_fc_v > 0 else "✓ Hanya Historis",
            })

        if rows_rule:
            st.markdown(
                '<div style="font-size:13px;font-weight:700;color:#0F172A;margin-bottom:8px;">'
                'Ringkasan Rule Violation</div>',
                unsafe_allow_html=True
            )
            df_rule_tbl = pd.DataFrame(rows_rule)

            def _color_rule_row(row):
                styles = [""] * len(row)
                idx = list(row.index)
                if "Severity" in idx:
                    bg = RULE_CLR_SEV.get(row["Severity"],"")
                    fc = RULE_TXT_SEV.get(row["Severity"],"")
                    styles[idx.index("Severity")] = f"background:{bg};color:{fc};font-weight:700;"
                if "Status" in idx:
                    clr = "#DC2626" if "Prediksi" in str(row["Status"]) else "#16A34A"
                    styles[idx.index("Status")] = f"color:{clr};font-weight:700;"
                if "Titik Forecast" in idx and row["Titik Forecast"] > 0:
                    styles[idx.index("Titik Forecast")] = "color:#DC2626;font-weight:700;"
                return styles

            st.dataframe(
                df_rule_tbl.style.apply(_color_rule_row, axis=1),
                use_container_width=True,
                hide_index=True,
                height=min(400, 42 + len(df_rule_tbl)*36),
            )
        else:
            st.success("✅ Tidak ada rule violation terdeteksi pada historis maupun forecast.")

    def _run_batch_arima(self, cache_path):
        import warnings
        warnings.filterwarnings("ignore")

        df = self.df_all
        param_col = "point" if "point" in df.columns else "Parameter"

        combos = (df[df["ref"]!="-"]
                  .groupby(["PartName","ModelName","SampleNo","ref",param_col])
                  .size().reset_index(name="n"))

        results = []
        progress = st.progress(0, text="Memproses batch forecast...")
        total = len(combos)

        for i, row in combos.iterrows():
            part, model, sno, ref, param = (
                row["PartName"], row["ModelName"],
                str(row["SampleNo"]), row["ref"], row[param_col]
            )
            df_sub = df[
                (df["PartName"]==part) & (df["ModelName"]==model) &
                (df["SampleNo"].astype(str)==sno) &
                (df["ref"].astype(str)==ref) &
                (df[param_col].astype(str)==param)
            ].sort_values(["Date","Shift","Cycle"]).dropna(subset=["Deviation"])

            progress.progress(min((i+1)/total, 1.0), text=f"{ref} · {param} ({i+1}/{total})")

            if len(df_sub) < 10:
                continue

            y    = df_sub["Deviation"].tolist()
            utol = float(df_sub["Uppertol"].iloc[0])
            ltol = float(df_sub["Lowertol"].iloc[0])
            res  = self._run_arima(y, 30)
            if "error" in res:
                continue

            fc = res["fc"]
            ng_shifts = [i+1 for i,v in enumerate(fc) if v > utol or v < ltol]
            trend_slope = round(float(np.polyfit(range(len(y)), y, 1)[0]), 6)
            trend_str = "naik" if trend_slope > 0 else "turun" if trend_slope < 0 else "stabil"

            results.append({
                "Part": part, "Model": model, "SampleNo": sno,
                "Ref": ref, "Point": param,
                "ARIMA_Order": str(res["order"]),
                "AIC": res["aic"],
                "Tren": trend_str,
                "Slope": trend_slope,
                "Prediksi_NG_Shift": ng_shifts[0] if ng_shifts else 0,
                "Status": "Berisiko" if ng_shifts else "Stabil",
            })

        progress.empty()
        if results:
            Path(cache_path).parent.mkdir(exist_ok=True)
            pd.DataFrame(results).to_csv(cache_path, index=False)
            st.success(f"✓ Batch selesai — {len(results)} kombinasi diproses")
        else:
            st.warning("Tidak ada kombinasi dengan data cukup.")

    @st.fragment
    def _render_spc(self):

        # ── Filter Baris 1: Part·Model | Kategori  (selectbox cascade) ──
        spc_combos = (
            self.df_all[["PartName","ModelName"]].dropna().drop_duplicates()
            .sort_values(["PartName","ModelName"])
        )
        spc_combo_opts = ["— Semua Part & Model —"] + [
            f"{r.PartName} · {r.ModelName}" for _, r in spc_combos.iterrows()
        ]
        if st.session_state.get("pred_combo") not in spc_combo_opts:
            st.session_state["pred_combo"] = "— Semua Part & Model —"

        cur_spc_combo = st.session_state.get("pred_combo", "— Semua Part & Model —")
        df_spc_combo  = self.df_all.copy()
        if cur_spc_combo != "— Semua Part & Model —":
            _sp = cur_spc_combo.split(" · ", 1)
            if len(_sp) == 2:
                df_spc_combo = self.df_all[(self.df_all["PartName"]==_sp[0])&(self.df_all["ModelName"]==_sp[1])]

        cat_spc_vals = sorted(df_spc_combo["Category"].dropna().unique().tolist()) if "Category" in df_spc_combo.columns else []
        cat_spc_opts = ["Semua Kategori"] + cat_spc_vals
        if st.session_state.get("pred_cat") not in cat_spc_opts:
            st.session_state["pred_cat"] = "Produksi" if "Produksi" in cat_spc_opts else "Semua Kategori"

        spc_r1c1, spc_r1c2 = st.columns([2.5, 1.5], gap="small")
        with spc_r1c1:
            f_spc_combo = st.selectbox("🔩 Part · Model", spc_combo_opts, key="pred_combo")
        with spc_r1c2:
            f_cat = st.selectbox("🏷 Kategori", cat_spc_opts, key="pred_cat")

        # Baris 2: KP | Ref/Point | Parameter (cascade dari combo+cat)
        cur_spc_cat  = st.session_state.get("pred_cat", "Semua Kategori")
        df_spc_cat   = df_spc_combo[df_spc_combo["Category"]==cur_spc_cat] if cur_spc_cat != "Semua Kategori" and "Category" in df_spc_combo.columns else df_spc_combo

        _ref_col_spc   = "ref"   if "ref"   in df_spc_cat.columns else "PartName"
        _param_col_spc = "point" if "point" in df_spc_cat.columns else "Parameter"

        ref_spc_vals = sorted([r for r in df_spc_cat[_ref_col_spc].dropna().astype(str).unique() if r not in ("","-","nan")])
        ref_spc_opts = ["Semua Ref / Point"] + ref_spc_vals
        if st.session_state.get("pred_ref") not in ref_spc_opts:
            st.session_state["pred_ref"] = "Semua Ref / Point"

        cur_spc_ref  = st.session_state.get("pred_ref", "Semua Ref / Point")
        df_spc_ref   = df_spc_cat[df_spc_cat[_ref_col_spc].astype(str)==cur_spc_ref] if cur_spc_ref != "Semua Ref / Point" else df_spc_cat

        param_spc_vals = sorted([p for p in df_spc_ref[_param_col_spc].dropna().astype(str).unique() if p not in ("","-","nan")])
        param_spc_opts = ["Semua Parameter"] + param_spc_vals
        if st.session_state.get("pred_param") not in param_spc_opts:
            st.session_state["pred_param"] = "Semua Parameter"

        kp_spc_opts = ["Semua Titik", "KP Only"]
        if st.session_state.get("pred_kp") not in kp_spc_opts:
            st.session_state["pred_kp"] = "Semua Titik"

        spc_r2c1, spc_r2c2, spc_r2c3 = st.columns([1.2, 1.5, 2.5], gap="small")
        with spc_r2c1:
            f_kp_spc = st.selectbox("⚠ Kritikal Point", kp_spc_opts, key="pred_kp")
        with spc_r2c2:
            f_ref_spc = st.selectbox("📍 Ref / Point", ref_spc_opts, key="pred_ref")
        with spc_r2c3:
            f_param_spc = st.selectbox("📐 Parameter", param_spc_opts, key="pred_param")

        # ── Filter Baris 3: Rule (tetap pills) ──
        st.markdown('<div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">📏 Filter Rule SPC</div>', unsafe_allow_html=True)
        rule_opts = ["Semua Rule"] + [f"Rule {i}" for i in range(1,8)]
        f_rule = st.pills(
            "Rule", rule_opts, default="Semua Rule",
            key="pred_rule", label_visibility="collapsed",
            selection_mode="single",
        ) or "Semua Rule"

        # Pecah combo → part & model
        f_part, f_model = "Semua Part", "Semua Model"
        if f_spc_combo != "— Semua Part & Model —":
            _sp = f_spc_combo.split(" · ", 1)
            if len(_sp) == 2:
                f_part, f_model = _sp[0], _sp[1]

        # ── Session state cache untuk deteksi kendali ─────────────────────
        import time as _time
        nelson_key = f"kendali_{f_part}_{f_model}_{f_cat}"
        ts_key     = f"{nelson_key}_ts"
        TTL        = 300
        if nelson_key not in st.session_state or \
           _time.time() - st.session_state.get(ts_key, 0) > TTL:
            df_src = self.df_all.copy()
            if f_part != "Semua Part":
                df_src = df_src[df_src["PartName"] == f_part]
            if f_model != "Semua Model":
                df_src = df_src[df_src["ModelName"] == f_model]
            if f_cat != "Semua Kategori" and "Category" in df_src.columns:
                df_src = df_src[df_src["Category"] == f_cat]
            if f_kp_spc == "KP Only" and "KP" in df_src.columns:
                df_src = df_src[df_src["KP"].astype(str).isin(["1","1.0","True"])]
            if f_ref_spc != "Semua Ref / Point" and _ref_col_spc in df_src.columns:
                df_src = df_src[df_src[_ref_col_spc].astype(str) == f_ref_spc]
            if f_param_spc != "Semua Parameter" and _param_col_spc in df_src.columns:
                df_src = df_src[df_src[_param_col_spc].astype(str) == f_param_spc]
            with st.spinner("Mendeteksi kondisi proses di luar kendali..."):
                st.session_state[nelson_key] = _build_kendali_history(df_src)
                st.session_state[ts_key]     = _time.time()

        df_hist = st.session_state[nelson_key]

        if df_hist.empty:
            st.success("Tidak ada kondisi proses di luar kendali yang terdeteksi.")
            return

        if f_rule != "Semua Rule":
            r_num = int(f_rule.split(" ")[1])
            df_hist = df_hist[df_hist["Rule"] == r_num]
        if df_hist.empty:
            st.info("Tidak ada violation untuk filter yang dipilih.")
            return

        # ── KPI summary ───────────────────────────────────────────
        n_total    = len(df_hist)
        n_critical = int((df_hist["Severity"] == "Critical").sum())
        n_warning  = int((df_hist["Severity"] == "Warning").sum())
        n_titik    = df_hist[["Part","Model","Ref","Parameter"]].drop_duplicates().shape[0]

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);'
            f'gap:10px;margin:12px 0 16px;">'
            + "".join([
                f'<div style="background:{bg};border-radius:8px;padding:12px 16px;text-align:center;">'
                f'<div style="font-size:22px;font-weight:700;color:{fc};">{val}</div>'
                f'<div style="font-size:10px;color:#64748B;text-transform:uppercase;'
                f'letter-spacing:.5px;margin-top:3px;">{lbl}</div></div>'
                for bg, fc, val, lbl in [
                    ("#F8FAFC", "#0F172A", n_total,    "Total Violations"),
                    ("#FEF2F2", "#DC2626", n_critical, "Critical"),
                    ("#FFFBEB", "#D97706", n_warning,  "Warning"),
                    ("#F0F9FF", "#0369A1", n_titik,    "Titik Ukur Terdampak"),
                ]
            ])
            + '</div>',
            unsafe_allow_html=True
        )

        # ── Chart: violations per rule ────────────────────────────
        c_left, c_right = st.columns([1.5, 2], gap="small")
        with c_left:
            rule_counts = df_hist.groupby(["Rule","Rule Label","Severity"]).size().reset_index(name="count")
            rule_counts = rule_counts.sort_values("Rule")
            st_echarts({
                "title": {"text": "Violations per Rule",
                          "textStyle": {"fontSize": 13, "fontWeight": 700}},
                "tooltip": {"trigger": "axis"},
                "grid": {"top": 36, "bottom": 8, "left": 8, "right": 40,
                         "containLabel": True},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category",
                          "data": rule_counts["Rule Label"].tolist(),
                          "axisLabel": {"fontSize": 10}},
                "series": [{
                    "data": rule_counts["count"].tolist(),
                    "type": "bar",
                    "itemStyle": {
                        "color": {"type": "linear", "x": 0, "y": 0, "x2": 1, "y2": 0,
                                  "colorStops": [{"offset": 0, "color": "#6366F1"},
                                                 {"offset": 1, "color": "#A78BFA"}]},
                        "borderRadius": [0, 4, 4, 0]
                    },
                    "label": {"show": True, "position": "right", "fontSize": 10}
                }],
            }, height="260px", key="pred_rule_bar")

        with c_right:
            # Semua titik dengan violations, per SampleNo
            grp_cols = ["Ref","Parameter","SampleNo"] if "SampleNo" in df_hist.columns else ["Ref","Parameter"]
            top_titik = (df_hist.groupby(grp_cols)["n Titik"]
                         .sum().sort_values(ascending=False))
            if "SampleNo" in df_hist.columns:
                labels = [f"{r} · {p} (No.{s})" for r, p, s in top_titik.index]
            else:
                labels = [f"{r} · {p}" for r, p in top_titik.index]
            n_items  = len(labels)
            st_echarts({
                "title": {"text": "Titik — Total Violations",
                          "textStyle": {"fontSize": 13, "fontWeight": 700}},
                "tooltip": {"trigger": "axis"},
                "grid": {"top": 36, "bottom": 8, "left": 8, "right": 60,
                         "containLabel": True},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category",
                          "data": list(reversed(labels)),
                          "axisLabel": {"fontSize": 9}},
                "dataZoom": [{"type": "slider", "yAxisIndex": 0,
                              "start": max(0, 100 - round(15/max(n_items,1)*100)) if n_items > 15 else 0,
                              "end": 100,
                              "width": 15, "right": 5,
                              "borderColor": "transparent",
                              "fillerColor": "rgba(99,102,241,0.15)",
                              "handleStyle": {"color": "#6366F1"}}],
                "series": [{
                    "data": list(reversed(top_titik.values.tolist())),
                    "type": "bar",
                    "itemStyle": {"color": "#F59E0B", "borderRadius": [0,4,4,0]},
                    "label": {"show": True, "position": "right", "fontSize": 10}
                }],
            }, height="260px", key="pred_top_titik")
        # ── Deskripsi kondisi proses di luar kendali ─────────────
        with st.expander("📋 Keterangan Kondisi Proses di Luar Kendali", expanded=False):
            RULE_META = [
                (1, "#EF4444", "Critical", "Satu atau lebih titik data berada di luar batas kendali."),
                (2, "#F59E0B", "Warning",  "Delapan titik data berurutan berada di satu sisi nilai rata-rata."),
                (3, "#8B5CF6", "Warning",  "Tujuh titik data berturut-turut yang meningkat atau menurun."),
                (4, "#06B6D4", "Warning",  "Empat belas titik data berurutan yang bergantian naik dan turun."),
                (5, "#10B981", "Warning",  "Dua titik data, dari tiga titik data berurutan, berada di sisi yang sama dari rata-rata di zona A atau di luarnya."),
                (6, "#10B981", "Warning",  "Empat titik data, dari lima titik data berurutan, berada di sisi yang sama dari rata-rata di zona B atau lebih jauh."),
                (7, "#3B82F6", "Warning",  "Lima belas titik data berurutan berada dalam zona C (di atas dan di bawah rata-rata)."),
            ]
            cols = st.columns(2)
            for idx, (r_num, clr, sev, desc) in enumerate(RULE_META):
                is_crit = sev == "Critical"
                sev_bg  = "#FEE2E2" if is_crit else "#EFF6FF"
                sev_clr = "#991B1B" if is_crit else "#1D4ED8"
                card_bg = "#FFF0F0" if is_crit else "#F0F4FF"
                with cols[idx % 2]:
                    st.markdown(
                        f'<div style="background:{card_bg};border:1.5px solid {clr}88;'
                        f'border-left:5px solid {clr};border-radius:10px;'
                        f'padding:12px 14px;margin-bottom:10px;'
                        f'box-shadow:0 2px 8px rgba(0,0,0,0.08);">'
                        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
                        f'<span style="background:{clr};color:#fff;border-radius:6px;'
                        f'padding:2px 10px;font-size:11px;font-weight:700;">Rule {r_num}</span>'
                        f'<span style="background:{sev_bg};color:{sev_clr};border-radius:4px;'
                        f'padding:1px 8px;font-size:10px;font-weight:700;">{sev}</span>'
                        f'</div>'
                        f'<div style="font-size:12px;color:#1E293B;line-height:1.5;font-weight:500;">{desc}</div>'
                        f'<div style="margin-top:8px;border-radius:6px;overflow:hidden;'
                        f'border:1px dashed {clr}66;background:#F8FAFC;'
                        f'height:80px;display:flex;align-items:center;justify-content:center;">' +
                        _get_rule_img_html(r_num, clr) +
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

        # ── Tabel history lengkap ─────────────────────────────────
        st.markdown(
            '<div style="font-size:14px;font-weight:700;color:#0F172A;'
            'margin:16px 0 8px;">History Deteksi Proses di Luar Kendali</div>',
            unsafe_allow_html=True
        )

        # Filter severity
        sev_filter = st.pills(
            "Severity", ["Semua","Critical","Warning"],
            default="Semua", key="pred_sev",
            label_visibility="collapsed", selection_mode="single"
        ) or "Semua"
        if sev_filter != "Semua":
            df_show = df_hist[df_hist["Severity"] == sev_filter].copy()
        else:
            df_show = df_hist.copy()

        RULE_CLR = {
            "Critical": "background-color:#FEF2F2;color:#991B1B;font-weight:700;",
            "Warning":  "background-color:#FFFBEB;color:#92400E;font-weight:700;",
        }
        RULE_LABEL_CLR = {
            "Rule 1": "#EF4444", "Rule 2": "#F59E0B", "Rule 3": "#8B5CF6",
            "Rule 4": "#06B6D4", "Rule 5": "#10B981", "Rule 6": "#F97316",
            "Rule 7": "#3B82F6",
        }

        def color_sev(row):
            styles = [""] * len(row)
            idx = list(row.index)
            si  = idx.index("Severity")
            ri  = idx.index("Rule Label")
            styles[si] = RULE_CLR.get(row["Severity"], "")
            styles[ri] = f"color:{RULE_LABEL_CLR.get(row['Rule Label'], '#64748B')};font-weight:700;"
            return styles

        cols_show = [c for c in ["Part","Model","Category","Ref","Parameter","SampleNo",
                     "Rule Label","Deskripsi","Severity","n Titik","Terakhir"]
                     if c in df_show.columns]

        st.markdown(
            '<div style="font-size:11px;color:#64748B;margin-bottom:6px;">'
            '👆 Klik baris untuk melihat grafik tren</div>',
            unsafe_allow_html=True
        )

        sel = st.dataframe(
            df_show[cols_show].style.apply(color_sev, axis=1),
            use_container_width=True,
            hide_index=True,
            height=min(520, 42 + len(df_show) * 36),
            on_select="rerun",
            selection_mode="single-row",
            key="pred_kendali_table",
        )

        # ── Chart tren untuk baris yang dipilih ────────────
        sel_rows = sel.selection.rows if sel and hasattr(sel, "selection") else []
        if sel_rows:
            row     = df_show[cols_show].iloc[sel_rows[0]]
            s_ref   = str(row["Ref"])
            s_param = str(row["Parameter"])
            s_part  = str(row["Part"])
            s_model = str(row["Model"])
            s_sno   = str(row["SampleNo"]) if "SampleNo" in row.index else None

            param_col = "point" if "point" in self.df_all.columns else "Parameter"
            df_t = self.df_all[
                (self.df_all["PartName"]  == s_part) &
                (self.df_all["ModelName"] == s_model) &
                (self.df_all["ref"].astype(str).str.strip().str.upper() == s_ref.upper()) &
                (self.df_all[param_col].astype(str) == s_param)
            ].copy()
            if s_sno and "SampleNo" in df_t.columns:
                df_t = df_t[df_t["SampleNo"].astype(str) == s_sno]

            df_t = df_t.sort_values(["Date","Shift","Cycle"]).dropna(subset=["Actual","Date"])

            if len(df_t) >= 2:
                st.markdown(
                    f'<div style="font-size:13px;font-weight:700;color:#0F172A;margin:16px 0 6px;">'
                    f'Tren Kendali — {s_ref} · {s_param}'
                    + (f' · No.{s_sno}' if s_sno else '') + '</div>',
                    unsafe_allow_html=True
                )
                y_vals   = df_t["Actual"].tolist()
                x_labels = df_t.apply(
                    lambda r: f"{r['Date'].strftime('%d %b')} S{r['Shift']}", axis=1
                ).tolist()
                mean_v  = float(np.mean(y_vals))
                sigma_v = float(np.std(y_vals, ddof=1)) if len(y_vals) > 1 else 0.0
                ucl_v   = round(mean_v + 3*sigma_v, 5)
                lcl_v   = round(mean_v - 3*sigma_v, 5)

                # USL/LSL dari data — coba kolom langsung, fallback ke Nominal+Tol
                nom_v = float(df_t["Nominal"].dropna().iloc[0]) if "Nominal" in df_t.columns and df_t["Nominal"].notna().any() else None
                if "USL" in df_t.columns and df_t["USL"].notna().any():
                    usl_v = float(df_t["USL"].dropna().iloc[0])
                elif nom_v is not None and "Uppertol" in df_t.columns and df_t["Uppertol"].notna().any():
                    usl_v = round(nom_v + float(df_t["Uppertol"].dropna().iloc[0]), 5)
                else:
                    usl_v = None
                if "LSL" in df_t.columns and df_t["LSL"].notna().any():
                    lsl_v = float(df_t["LSL"].dropna().iloc[0])
                elif nom_v is not None and "Lowertol" in df_t.columns and df_t["Lowertol"].notna().any():
                    lsl_v = round(nom_v + float(df_t["Lowertol"].dropna().iloc[0]), 5)
                else:
                    lsl_v = None

                # Deteksi violations — persis seperti descriptive
                vbr = _detect_kendali(y_vals)
                RC  = {1:"#EF4444",2:"#F59E0B",3:"#8B5CF6",
                       4:"#06B6D4",5:"#10B981",6:"#F97316",7:"#3B82F6"}

                def pt_style(i):
                    for r in [1,2,3,4,5,6,7]:
                        if i in vbr[r]:
                            return {"color":"#6366F1","borderColor":RC[r],"borderWidth":2.5}
                    return {"color":"#6366F1"}

                series_data = [{"value": v, "itemStyle": pt_style(i)}
                               for i, v in enumerate(y_vals)]

                # Legend warna
                st.markdown("""
                <div style="display:flex;flex-wrap:wrap;gap:14px;font-size:11px;
                            color:#64748B;margin-bottom:6px;">
                  <span>&#8943; <span style="color:#EF4444;">dashed</span> UCL/LCL (3&sigma;)</span>
                  <span style="color:#EF4444;">&#9711;</span> Rule 1 &nbsp;
                  <span style="color:#F59E0B;">&#9711;</span> Rule 2 &nbsp;
                  <span style="color:#8B5CF6;">&#9711;</span> Rule 3 &nbsp;
                  <span style="color:#06B6D4;">&#9711;</span> Rule 4 &nbsp;
                  <span style="color:#10B981;">&#9711;</span> Rule 5 &nbsp;
                  <span style="color:#F97316;">&#9711;</span> Rule 6 &nbsp;
                  <span style="color:#3B82F6;">&#9711;</span> Rule 7
                </div>
                """, unsafe_allow_html=True)

                mark_lines = [
                    {"yAxis": ucl_v, "lineStyle": {"color":"#EF4444","width":1,"type":"dashed"},
                     "label": {"formatter":f"UCL {ucl_v}","fontSize":9,"color":"#EF4444"}},
                    {"yAxis": lcl_v, "lineStyle": {"color":"#EF4444","width":1,"type":"dashed"},
                     "label": {"formatter":f"LCL {lcl_v}","fontSize":9,"color":"#EF4444"}},
                ]
                if usl_v: mark_lines += [
                    {"yAxis": usl_v, "lineStyle": {"color":"#EF4444","width":2,"type":"solid"},
                     "label": {"formatter":f"USL {usl_v}","fontSize":10,"color":"#EF4444"}},
                ]
                if lsl_v: mark_lines += [
                    {"yAxis": lsl_v, "lineStyle": {"color":"#EF4444","width":2,"type":"solid"},
                     "label": {"formatter":f"LSL {lsl_v}","fontSize":10,"color":"#EF4444"}},
                ]
                if nom_v: mark_lines += [
                    {"yAxis": nom_v, "lineStyle": {"color":"#22C55E","width":1.5,"type":"dashed"},
                     "label": {"formatter":f"Nom {nom_v}","fontSize":10,"color":"#22C55E"}},
                ]

                # Hitung y_min / y_max agar semua garis referensi terlihat
                all_ref = [ucl_v, lcl_v] + \
                          ([usl_v] if usl_v else []) + \
                          ([lsl_v] if lsl_v else []) + \
                          ([nom_v] if nom_v else [])
                all_y   = y_vals + all_ref
                y_pad   = (max(all_y) - min(all_y)) * 0.1 or sigma_v * 0.5 or 0.01
                y_min_v = round(min(all_y) - y_pad, 5)
                y_max_v = round(max(all_y) + y_pad, 5)

                st_echarts({
                    "title": {"text": f"Tren — {s_ref} · {s_param}" + (f" · No.{s_sno}" if s_sno else ""),
                              "left": 12, "top": 8,
                              "textStyle": {"fontSize":13,"fontWeight":700,"color":"#0F172A"}},
                    "grid": {"top":50,"right":80,"bottom":55,"left":60},
                    "tooltip": {"trigger":"axis","formatter":"{b}<br/>Aktual: <b>{c}</b>"},
                    "xAxis": {"type":"category","data":x_labels,
                              "axisLabel":{"rotate":20,"fontSize":9,"interval":"auto"}},
                    "yAxis": {"type":"value","min":y_min_v,"max":y_max_v,"name":"Aktual",
                              "axisLabel":{"fontSize":10}},
                    "dataZoom": [{"type":"inside","start":0,"end":100},
                                 {"type":"slider","bottom":8,"height":16}],
                    "series": [{
                        "data": series_data, "type": "line",
                        "symbol": "circle", "symbolSize": 8,
                        "lineStyle": {"color":"#6366F1","width":1.5},
                        "markLine": {"symbol":["none","none"],"silent":True,
                                     "data": mark_lines},
                    }],
                }, height="340px", key=f"pred_trend_{s_ref}_{s_param}_{s_sno}")

                # Penjelasan per rule yang terdeteksi
                KONTEKS = {
                    1: "Titik berada di luar batas kendali — indikasi penyebab khusus (special cause) yang perlu segera diinvestigasi.",
                    2: "Proses mengalami pergeseran (shift) dari nilai rata-rata — kemungkinan ada perubahan pada material, mesin, atau operator.",
                    3: "Tren naik atau turun secara konsisten — indikasi adanya drift pada proses, misalnya keausan alat atau perubahan suhu bertahap.",
                    4: "Pola osilasi berlebihan — kemungkinan over-adjustment atau gangguan sistematis pada proses pengukuran.",
                    5: "Peringatan dini pergeseran proses — dua dari tiga titik mendekati batas kendali di sisi yang sama.",
                    6: "Proses bergeser secara halus dari rata-rata — empat dari lima titik berada jauh dari pusat di sisi yang sama.",
                    7: "Proses terlalu konsisten di dekat rata-rata — bisa mengindikasikan stratifikasi data atau masalah pada sistem pengukuran.",
                }
                triggered = [r for r in range(1,8) if vbr[r]]
                if triggered:
                    st.markdown(
                        '<div style="font-size:12px;font-weight:700;color:#0F172A;'
                        'margin:12px 0 6px;">Kondisi Terdeteksi</div>',
                        unsafe_allow_html=True
                    )
                    for r_num in triggered:
                        clr     = RC[r_num]
                        sev     = RULES[r_num]["severity"]
                        desc    = RULES[r_num]["desc"]
                        konteks = KONTEKS[r_num]
                        is_crit = sev == "Critical"
                        sev_bg  = "#FEE2E2" if is_crit else "#FEF3C7"
                        sev_clr = "#991B1B" if is_crit else "#92400E"
                        card_bg = "#FFF0F0" if is_crit else "#F5F7FF"
                        st.markdown(
                            f'<div style="display:flex;align-items:flex-start;gap:12px;'
                            f'background:{card_bg};border:1.5px solid {clr}66;border-left:5px solid {clr};'
                            f'border-radius:10px;padding:12px 16px;margin-bottom:8px;'
                            f'box-shadow:0 2px 8px rgba(0,0,0,0.07);">'
                            f'<div style="min-width:64px;padding-top:1px;">'
                            f'<span style="background:{clr};color:#fff;'
                            f'border-radius:6px;padding:3px 10px;font-size:11px;font-weight:700;'
                            f'white-space:nowrap;">Rule {r_num}</span></div>'
                            f'<div style="flex:1;">'
                            f'<div style="font-size:12px;color:#0F172A;font-weight:600;margin-bottom:3px;">'
                            f'{desc}</div>'
                            f'<div style="font-size:11px;color:#475569;margin-bottom:6px;line-height:1.5;">'
                            f'{konteks}</div>'
                            f'<div style="display:flex;align-items:center;gap:8px;font-size:11px;color:#64748B;">'
                            f'<span>📍 {len(vbr[r_num])} titik terdampak</span>'
                            f'<span style="color:#CBD5E1;">|</span>'
                            f'<span style="background:{sev_bg};color:{sev_clr};'
                            f'border-radius:4px;padding:1px 8px;font-weight:700;font-size:10px;">'
                            f'{sev}</span>'
                            f'</div></div></div>',
                            unsafe_allow_html=True
                        )
            else:
                st.info("Data tidak cukup untuk menampilkan tren.")