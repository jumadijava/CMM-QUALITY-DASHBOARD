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
            ["🎯 Klasifikasi", "📈 Forecasting", "🔍 Anomaly", "💬 AI Insight"],
            default="🎯 Klasifikasi",
            key="pred_ai_tab",
            label_visibility="collapsed",
        ) or "🎯 Klasifikasi"

        if ai_tab == "🎯 Klasifikasi":
            self._render_klasifikasi()
        elif ai_tab == "📈 Forecasting":
            self._render_forecasting()
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

        # ── Selector ─────────────────────────────────────────────
        c1, c2, c3 = st.columns(3, gap="small")
        with c1:
            parts  = sorted(df["PartName"].dropna().unique().tolist())
            f_part = st.selectbox("Part", parts, key="fc_part")
        with c2:
            models = sorted(df[df["PartName"]==f_part]["ModelName"].dropna().unique().tolist())
            f_model = st.selectbox("Model", models, key="fc_model")
        with c3:
            snos   = sorted(df[(df["PartName"]==f_part)&(df["ModelName"]==f_model)]["SampleNo"].dropna().astype(str).unique().tolist(),
                            key=lambda s: (0,int(s)) if s.isdigit() else (1,s))
            f_sno  = st.selectbox("SampleNo", snos, key="fc_sno")

        param_col = "point" if "point" in df.columns else "Parameter"
        df_pm = df[(df["PartName"]==f_part)&(df["ModelName"]==f_model)&(df["SampleNo"].astype(str)==f_sno)]
        refs   = sorted(df_pm["ref"].dropna().astype(str).unique().tolist())
        refs   = [r for r in refs if r not in ("-","nan","")]

        c4, c5, c6 = st.columns(3, gap="small")
        with c4:
            f_ref  = st.selectbox("Ref", refs, key="fc_ref") if refs else None
        with c5:
            params = sorted(df_pm[df_pm["ref"].astype(str)==f_ref][param_col].dropna().unique().tolist()) if f_ref else []
            f_param = st.selectbox("Parameter", params, key="fc_param") if params else None
        with c6:
            fc_n = st.number_input("Horizon (shift ke depan)", min_value=5, max_value=90, value=30, step=5, key="fc_n")

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

        # ── Filter pills ──────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4, gap="small")
        with c1:
            f_risk = st.pills("Filter risiko",
                ["Semua","Prediksi NG","🔴 Tinggi","🟡 Sedang","🟢 Rendah"],
                default="🔴 Tinggi", key="cls_filter",
                selection_mode="single", label_visibility="collapsed") or "Semua"
        with c2:
            parts_avail = sorted(result["PartName"].unique().tolist())
            f_pf = st.pills("Part", parts_avail, default=parts_avail[0],
                            key="cls_part_f", selection_mode="single",
                            label_visibility="collapsed") or parts_avail[0]
        with c3:
            models_avail = sorted(result[result["PartName"]==f_pf]["ModelName"].unique().tolist())
            f_model_f = st.pills("Model", models_avail, default=models_avail[0],
                                 key=f"cls_model_f_{f_pf}", selection_mode="single",
                                 label_visibility="collapsed") or models_avail[0]
        with c4:
            f_cat = st.pills("Kategori", ["Produksi","QIS","Semua"],
                             default="Produksi", key="cls_cat",
                             selection_mode="single",
                             label_visibility="collapsed") or "Produksi"

        df_filtered = result.copy()
        if f_risk == "Prediksi NG":
            df_filtered = df_filtered[df_filtered["Pred"]=="NG"]
        elif f_risk != "Semua":
            df_filtered = df_filtered[df_filtered["Risiko"]==f_risk]
        df_filtered = df_filtered[(df_filtered["PartName"]==f_pf) & (df_filtered["ModelName"]==f_model_f)]
        if f_cat != "Semua" and "Category" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["Category"]==f_cat]

        sample_opts = ["Semua"] + sorted(
            df_filtered["SampleNo"].dropna().unique().tolist(),
            key=lambda s: (0, int(str(s))) if str(s).isdigit() else (1, str(s))
        )
        f_sample = st.pills("SampleNo", sample_opts, default="Semua",
                            key="cls_sample_f", selection_mode="single",
                            label_visibility="collapsed") or "Semua"

        df_show = df_filtered.copy()
        if f_sample != "Semua":
            df_show = df_show[df_show["SampleNo"]==f_sample]

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

        sc = ["PartName","ModelName","ref","point","SampleNo","Prob_NG","Pred","Risiko"]
        sc = [c for c in sc if c in df_show.columns]
        df_tbl = df_show[sc].sort_values("Prob_NG", ascending=False).reset_index(drop=True)
        df_tbl.columns = ["Part","Model","Ref","Parameter","SampleNo",
                          "Prob NG (%)","Prediksi","Risiko"][:len(sc)]
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

        # ── Filter pills ──────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4, gap="small")
        with c1:
            parts_avail = ["Semua Part"] + sorted(self.df_all["PartName"].dropna().unique().tolist())
            f_part = st.pills("Part", parts_avail, default="Semua Part",
                              key="pred_part", label_visibility="collapsed",
                              selection_mode="single") or "Semua Part"
        with c2:
            if f_part == "Semua Part":
                models_avail = ["Semua Model"] + sorted(self.df_all["ModelName"].dropna().unique().tolist())
            else:
                models_avail = ["Semua Model"] + sorted(self.df_all[self.df_all["PartName"]==f_part]["ModelName"].dropna().unique().tolist())
            f_model = st.pills("Model", models_avail, default="Semua Model",
                               key=f"pred_model_{f_part}", label_visibility="collapsed",
                               selection_mode="single") or "Semua Model"
        with c3:
            f_cat = st.pills("Category", ["Produksi","QIS","Semua"], default="Produksi",
                             key="pred_cat", label_visibility="collapsed",
                             selection_mode="single") or "Produksi"
        with c4:
            rule_opts = ["Semua"] + [f"Rule {i}" for i in range(1,8)]
            f_rule = st.pills("Rule", rule_opts, default="Semua",
                              key="pred_rule", label_visibility="collapsed",
                              selection_mode="single") or "Semua"

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
            if f_cat != "Semua" and "Category" in df_src.columns:
                df_src = df_src[df_src["Category"] == f_cat]
            with st.spinner("Mendeteksi kondisi proses di luar kendali..."):
                st.session_state[nelson_key] = _build_kendali_history(df_src)
                st.session_state[ts_key]     = _time.time()

        df_hist = st.session_state[nelson_key]

        if df_hist.empty:
            st.success("Tidak ada kondisi proses di luar kendali yang terdeteksi.")
            return

        if f_rule != "Semua":
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
                        f'<div style="margin-top:8px;padding:6px 8px;background:rgba(255,255,255,0.6);'
                        f'border-radius:4px;font-size:10px;color:#94A3B8;text-align:center;'
                        f'border:1px dashed {clr}66;">ilustrasi</div>'
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