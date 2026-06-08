"""
pages_app/prescriptive.py
─────────────────────────
Prescriptive Analytics — Rekomendasi Tindakan
"""
import streamlit as st
import pandas as pd
from streamlit_echarts import st_echarts

from local_db import (
    get_root_causes,
    RC_CATEGORIES, RC_STATUSES,
)

STATUS_COLOR = {
    "Open":         ("#DC2626", "#FEE2E2"),
    "Investigated": ("#D97706", "#FEF3C7"),
    "Resolved":     ("#16A34A", "#DCFCE7"),
}

REKOMENDASI = {
    "Mesin / Machine": [
        "Lakukan kalibrasi probe CMM sebelum shift berikutnya",
        "Cek kondisi spindle dan thermal compensation mesin",
        "Verifikasi backlash pada axis yang bermasalah",
        "Jadwalkan preventive maintenance jika belum dilakukan",
    ],
    "Setup / Fixture": [
        "Verifikasi posisi fixture sesuai drawing sebelum produksi",
        "Pastikan semua clamp terkunci sempurna",
        "Cek datum reference — pastikan tidak ada burr atau kotoran",
        "Lakukan re-setup dan verifikasi dengan sampel pertama",
    ],
    "Material": [
        "Lakukan incoming inspection material sebelum diproses",
        "Koordinasi dengan supplier untuk review dimensi raw material",
        "Pisahkan material suspect — jangan proses dulu",
        "Minta sample report dari supplier untuk batch ini",
    ],
    "Operator": [
        "Brief operator sebelum shift dimulai untuk titik ini",
        "Review SOP setup dan mounting bersama operator",
        "Assign operator berpengalaman untuk titik kritis",
        "Lakukan observasi langsung saat setup pertama",
    ],
    "Program CMM": [
        "Update program CMM sesuai revisi drawing terbaru",
        "Verifikasi reference point dan approach speed",
        "Test run program dengan part master sebelum produksi",
        "Review path program untuk potensi probe collision",
    ],
    "Tooling": [
        "Ganti tool yang wear — verifikasi dengan tool life record",
        "Cek kondisi insert dan holder sebelum produksi",
        "Verifikasi coolant flow tidak tersumbat",
        "Ukur dimensi tool aktual sebelum dipakai",
    ],
    "Lainnya": [
        "Lakukan investigasi lebih lanjut bersama engineer",
        "Dokumentasikan temuan untuk analisis root cause",
        "Eskalasi ke supervisor jika belum teridentifikasi",
    ],
}


class PrescriptivePage:
    def __init__(self, df_all: pd.DataFrame):
        self.df_all = df_all

    def render(self):
        st.markdown(
            '<div class="page-hdr">'
            '<span class="page-title">Prescriptive</span>'
            '<span style="font-size:12px;color:#64748B;font-weight:500;margin-left:8px;">'
            'Rekomendasi Tindakan</span></div>',
            unsafe_allow_html=True
        )

        @st.cache_data(ttl=120)
        def _load_rc():
            return get_root_causes()

        all_rcs = _load_rc()
        if not all_rcs:
            st.info("Belum ada root cause tersimpan. Isi Root Cause di halaman Messages atau Diagnostic terlebih dahulu.")
            return

        df_rc = pd.DataFrame(all_rcs)

        # Pastikan kolom date bisa diparse
        df_rc["_date_dt"] = pd.to_datetime(df_rc["date"], format="%d %b %Y", errors="coerce")

        # ── Filter bar Row 1: Waktu + Kategori ───────────────────
        r1c1, r1c2, r1c3 = st.columns([2, 2, 1], gap="small")
        with r1c1:
            time_opts = ["Today", "7 Hari", "30 Hari", "Semua", "Custom"]
            f_time = st.pills("Waktu", time_opts, default="30 Hari",
                              key="presc_time", selection_mode="single",
                              label_visibility="collapsed") or "30 Hari"

        # Custom date picker — muncul kalau pilih Custom
        from datetime import timedelta as _td
        _now = pd.Timestamp.now()
        if f_time == "Custom":
            cd1, cd2 = st.columns(2, gap="small")
            with cd1:
                d1 = st.date_input("Dari", value=_now.date() - _td(days=30),
                                   key="presc_d1", label_visibility="visible")
            with cd2:
                d2 = st.date_input("Sampai", value=_now.date(),
                                   key="presc_d2", label_visibility="visible")
        with r1c2:
            f_cat_filter = st.pills("Kategori Root Cause", ["Produksi", "QIS", "Semua"],
                                    default="Produksi",
                                    key="presc_cat_filter", selection_mode="single",
                                    label_visibility="collapsed") or "Produksi"
        with r1c3:
            f_status = st.pills("Status", ["Semua", "Open", "Investigated", "Resolved"],
                                default="Semua", key="presc_status",
                                selection_mode="single",
                                label_visibility="collapsed") or "Semua"

        # ── Filter bar Row 2: Part + Model ───────────────────────
        r2c1, r2c2 = st.columns(2, gap="small")
        with r2c1:
            parts = ["Semua Part"] + sorted(df_rc["part"].dropna().unique().tolist())
            f_part = st.pills("Part", parts, default="Semua Part",
                              key="presc_part", selection_mode="single",
                              label_visibility="collapsed") or "Semua Part"
        with r2c2:
            if f_part != "Semua Part":
                models = ["Semua Model"] + sorted(df_rc[df_rc["part"]==f_part]["model"].dropna().unique().tolist())
            else:
                models = ["Semua Model"] + sorted(df_rc["model"].dropna().unique().tolist())
            f_model = st.pills("Model", models, default="Semua Model",
                               key=f"presc_model_{f_part}", selection_mode="single",
                               label_visibility="collapsed") or "Semua Model"

        # Apply filter waktu
        df_f = df_rc.copy()
        if f_time == "Today":
            df_f = df_f[df_f["_date_dt"].dt.date == _now.date()]
        elif f_time == "7 Hari":
            df_f = df_f[df_f["_date_dt"] >= _now - _td(days=7)]
        elif f_time == "30 Hari":
            df_f = df_f[df_f["_date_dt"] >= _now - _td(days=30)]
        elif f_time == "Custom":
            df_f = df_f[(df_f["_date_dt"].dt.date >= d1) & (df_f["_date_dt"].dt.date <= d2)]

        # Filter QIS/Produksi — dari kolom 'category' di CMM data via df_all
        if f_cat_filter != "Semua" and "sampleno" in df_f.columns:
            # Mapping QIS → Category="QIS" di RC pakai join dengan df_all
            if not self.df_all.empty and "Category" in self.df_all.columns:
                _cat_map = (self.df_all.groupby(["PartName","ModelName","ref","point"])["Category"]
                           .agg(lambda x: x.mode()[0] if len(x)>0 else "Produksi")
                           .reset_index())
                _cat_map.columns = ["part","model","ref","parameter","_cmm_cat"]
                df_f = df_f.merge(_cat_map, on=["part","model","ref","parameter"], how="left")
                df_f["_cmm_cat"] = df_f["_cmm_cat"].fillna("Produksi")
                if f_cat_filter == "QIS":
                    df_f = df_f[df_f["_cmm_cat"] == "QIS"]
                elif f_cat_filter == "Produksi":
                    df_f = df_f[df_f["_cmm_cat"] == "Produksi"]

        if f_part != "Semua Part":
            df_f = df_f[df_f["part"] == f_part]
        if f_model != "Semua Model":
            df_f = df_f[df_f["model"] == f_model]
        if f_status != "Semua":
            df_f = df_f[df_f["status"] == f_status]

        if df_f.empty:
            st.info("Tidak ada data untuk filter ini.")
            return

        # ── KPI Cards ─────────────────────────────────────────────
        n_total    = len(df_rc)
        n_open     = int((df_rc["status"] == "Open").sum())
        n_invest   = int((df_rc["status"] == "Investigated").sum())
        n_resolved = int((df_rc["status"] == "Resolved").sum())
        pct_done   = round(n_resolved / n_total * 100, 1) if n_total else 0

        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px;">'
            + "".join([
                f'<div style="background:{bg};border-radius:10px;border:1px solid {bc};'
                f'padding:16px;text-align:center;">'
                f'<div style="font-size:26px;font-weight:800;color:{fc};">{val}</div>'
                f'<div style="font-size:11px;font-weight:600;color:#64748B;margin-top:4px;">{lbl}</div>'
                f'</div>'
                for bg, bc, fc, val, lbl in [
                    ("#F8FAFC","#E2E8F0","#0F172A", n_total,      "Total Root Cause"),
                    ("#FEF2F2","#FECACA","#DC2626", n_open,       "Open"),
                    ("#FFFBEB","#FDE68A","#D97706", n_invest,     "Investigated"),
                    ("#F0FDF4","#BBF7D0","#16A34A", f"{pct_done}%","% Resolved"),
                ]
            ])
            + '</div>',
            unsafe_allow_html=True
        )

        # ── Tabs ──────────────────────────────────────────────────
        tab1, tab2, tab3 = st.tabs([
            "📋 History Saran",
            "🎯 Prioritas Tindakan",
            "📊 Pola & Tren",
        ])

        with tab1:
            self._render_history_saran()
        with tab2:
            @st.fragment
            def _tab2():
                self._render_prioritas(df_f, df_rc)
            _tab2()
        with tab3:
            self._render_pola(df_f)

    # ════════════════════════════════════════════════════════════
    # TAB 1 — PRIORITAS TINDAKAN
    # ════════════════════════════════════════════════════════════
    def _render_prioritas(self, df_f: pd.DataFrame, df_rc: pd.DataFrame):
        st.markdown(
            '<div style="font-size:13px;font-weight:600;color:#0F172A;margin:8px 0 12px;">'
            'Titik yang perlu ditindaklanjuti — urut prioritas</div>',
            unsafe_allow_html=True
        )

        @st.cache_data(ttl=120, show_spinner=False)
        def _compute_scores(_df):
            grp = _df.groupby(["part","model","ref","parameter"])
            rows = []
            for (part, model, ref, param), g in grp:
                n_ng  = len(g)
                n_o   = int((g["status"]=="Open").sum())
                n_i   = int((g["status"]=="Investigated").sum())
                n_r   = int((g["status"]=="Resolved").sum())
                score = n_ng*2 + n_o*3 + n_i*1
                top_c = g["category"].value_counts().index[0] if len(g) else "-"
                rows.append({"part":part,"model":model,"ref":ref,"parameter":param,
                             "score":score,"n_ng":n_ng,"n_open":n_o,
                             "n_invest":n_i,"n_resolved":n_r,"top_cat":top_c})
            return pd.DataFrame(rows).sort_values("score", ascending=False)

        df_score = _compute_scores(df_rc)

        if not df_f.empty:
            f_refs = set(zip(df_f["part"],df_f["model"],df_f["ref"],df_f["parameter"]))
            df_score = df_score[df_score.apply(
                lambda r: (r["part"],r["model"],r["ref"],r["parameter"]) in f_refs, axis=1
            )]

        if df_score.empty:
            st.info("Tidak ada titik untuk ditampilkan.")
            return

        # ── Pagination ────────────────────────────────────────────
        PAGE_SIZE = 10
        n_total_items = len(df_score)
        n_pages = max(1, -(-n_total_items // PAGE_SIZE))  # ceiling division

        if n_pages > 1:
            pc1, pc2, pc3 = st.columns([1, 3, 1], gap="small")
            cur_page = st.session_state.get("presc_page", 1)
            with pc1:
                if st.button("← Prev", key="presc_prev",
                             disabled=cur_page<=1,
                             use_container_width=True):
                    st.session_state.presc_page = cur_page - 1
                    st.session_state.presc_open_titik = None
                    st.rerun()
            with pc2:
                st.markdown(
                    f'<div style="text-align:center;font-size:12px;color:#64748B;padding-top:6px;">'
                    f'Halaman <b>{cur_page}</b> dari <b>{n_pages}</b> '
                    f'({n_total_items} titik)</div>',
                    unsafe_allow_html=True
                )
            with pc3:
                if st.button("Next →", key="presc_next",
                             disabled=cur_page>=n_pages,
                             use_container_width=True):
                    st.session_state.presc_page = cur_page + 1
                    st.session_state.presc_open_titik = None
                    st.rerun()
            st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
        else:
            cur_page = 1

        start_idx = (cur_page - 1) * PAGE_SIZE
        df_page   = df_score.iloc[start_idx : start_idx + PAGE_SIZE]

        def _priority(score):
            if score >= 15: return ("🔴 Kritis", "#DC2626","#FEE2E2")
            if score >= 8:  return ("🟡 Tinggi", "#D97706","#FEF3C7")
            return              ("🟢 Sedang", "#16A34A","#DCFCE7")

        open_titik = st.session_state.get("presc_open_titik")

        for _, row in df_page.iterrows():
            label   = f"{row['ref']} · {row['parameter']}"
            tid     = f"{row['part']}_{row['model']}_{row['ref']}_{row['parameter']}"
            p_lbl, p_fc, p_bg = _priority(row["score"])
            is_open = open_titik == tid
            border  = "#EF4444" if row["n_open"] > 0 else "#E2E8F0"

            st.markdown(
                f'<div style="background:white;border:1px solid {border};'
                f'border-left:4px solid {border};border-radius:10px;'
                f'padding:12px 16px;margin-bottom:4px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<div style="font-size:14px;font-weight:700;color:#0F172A;">{label}</div>'
                f'<div style="font-size:11px;color:#64748B;margin-top:2px;">'
                f'<b>{row["part"]} {row["model"]}</b> &nbsp;·&nbsp; '
                f'{row["n_ng"]} NG &nbsp;·&nbsp; '
                f'<span style="color:#DC2626;font-weight:600;">{row["n_open"]} Open</span>'
                f' &nbsp;·&nbsp; Dominan: <b>{row["top_cat"]}</b></div>'
                f'</div>'
                f'<span style="background:{p_bg};color:{p_fc};font-size:10px;'
                f'font-weight:700;padding:3px 10px;border-radius:99px;">{p_lbl}</span>'
                f'</div></div>',
                unsafe_allow_html=True
            )

            col_btn, _ = st.columns([1,6])
            with col_btn:
                btn_lbl = "✕ Tutup" if is_open else "📋 Rekomendasi"
                if st.button(btn_lbl, key=f"presc_btn_{tid}",
                             use_container_width=True,
                             type="secondary" if is_open else "primary"):
                    st.session_state.presc_open_titik = None if is_open else tid
                    st.rerun()

            if is_open:
                self._render_rekomendasi_detail(row, df_rc)

            st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)


    def _render_rekomendasi_detail(self, row: pd.Series, df_rc: pd.DataFrame):
        df_titik = df_rc[
            (df_rc["part"]==row["part"]) & (df_rc["model"]==row["model"]) &
            (df_rc["ref"]==row["ref"]) & (df_rc["parameter"]==row["parameter"])
        ]

        with st.container(border=True):
            cat_counts = df_titik["category"].value_counts()
            top_cat    = cat_counts.index[0] if len(cat_counts) else "Lainnya"
            top_pct    = round(cat_counts.iloc[0]/len(df_titik)*100) if len(df_titik) else 0

            # ── Insight shift ────────────────────────────────────
            shift_counts = df_titik["shift"].value_counts() if "shift" in df_titik.columns else None
            shift_insight = ""
            if shift_counts is not None and len(shift_counts) > 0:
                top_shift = shift_counts.index[0]
                top_shift_pct = round(shift_counts.iloc[0]/len(df_titik)*100)
                shift_insight = f' · <b>Dominan di Shift {top_shift}</b> ({top_shift_pct}%)'

            # ── Insight Part+Model spesifik ──────────────────────
            pm_key = f"{row['part']} {row['model']}"
            df_pm  = df_rc[(df_rc["part"]==row["part"]) & (df_rc["model"]==row["model"])]
            pm_top_cat = df_pm["category"].value_counts().index[0] if len(df_pm) else top_cat
            pm_top_pct = round(df_pm["category"].value_counts().iloc[0]/len(df_pm)*100) if len(df_pm) else top_pct

            st.markdown(
                f'<div style="background:#F1F5F9;border-radius:8px;padding:8px 12px;'
                f'margin-bottom:10px;font-size:11px;color:#475569;">'
                f'<b>{pm_key}</b> — secara keseluruhan dominan: '
                f'<b style="color:#0F172A;">{pm_top_cat}</b> ({pm_top_pct}%){shift_insight}'
                f'</div>',
                unsafe_allow_html=True
            )

            col_a, col_b = st.columns(2, gap="medium")

            with col_a:
                st.markdown('<div style="font-size:12px;font-weight:700;color:#0F172A;margin-bottom:8px;">📊 Distribusi Penyebab</div>', unsafe_allow_html=True)
                # Shift breakdown bar
                if shift_counts is not None and len(shift_counts) > 1:
                    shift_cat_df = df_titik.groupby(["shift","category"]).size().reset_index(name="n")
                    shifts_u = sorted(df_titik["shift"].dropna().unique())
                    COLORS_P = ["#EF4444","#F59E0B","#8B5CF6","#06B6D4","#10B981","#6366F1","#94A3B8"]
                    ser_sc = []
                    for i2, cat2 in enumerate(RC_CATEGORIES):
                        vals2 = []
                        for sh2 in shifts_u:
                            sub2 = shift_cat_df[(shift_cat_df["shift"]==sh2)&(shift_cat_df["category"]==cat2)]
                            vals2.append(int(sub2["n"].sum()) if not sub2.empty else 0)
                        if any(v2>0 for v2 in vals2):
                            ser_sc.append({"name":cat2,"type":"bar","stack":"s","data":vals2,
                                           "itemStyle":{"color":COLORS_P[i2%len(COLORS_P)]}})
                    st_echarts({
                        "tooltip":{"trigger":"axis","axisPointer":{"type":"shadow"}},
                        "legend":{"bottom":0,"icon":"roundRect","itemWidth":8,"textStyle":{"fontSize":8}},
                        "grid":{"top":8,"bottom":60,"left":30,"right":8},
                        "xAxis":{"type":"category","data":[f"S{s2}" for s2 in shifts_u]},
                        "yAxis":{"type":"value","axisLabel":{"fontSize":9}},
                        "series":ser_sc,
                    }, height="220px", key=f"presc_shift_{row['ref']}_{row['parameter']}")
                else:
                    st_echarts({
                        "tooltip": {"trigger":"item"},
                        "series": [{"type":"pie","radius":["40%","70%"],
                            "data":[{"name":l,"value":v} for l,v in zip(cat_counts.index.tolist(),cat_counts.values.tolist())],
                            "label":{"fontSize":10},
                            "itemStyle":{"borderRadius":6,"borderWidth":2,"borderColor":"#fff"}}],
                        "color":["#EF4444","#F59E0B","#8B5CF6","#06B6D4","#10B981","#6366F1","#94A3B8"],
                    }, height="220px", key=f"presc_pie_{row['ref']}_{row['parameter']}")

            with col_b:
                st.markdown('<div style="font-size:12px;font-weight:700;color:#0F172A;margin-bottom:8px;">✅ Rekomendasi Tindakan</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:11px;color:#64748B;margin-bottom:8px;">Untuk titik ini: <b style="color:#0F172A;">{top_cat}</b> ({top_pct}%)</div>', unsafe_allow_html=True)
                for i, rec in enumerate(REKOMENDASI.get(top_cat, REKOMENDASI["Lainnya"]), 1):
                    st.markdown(
                        f'<div style="display:flex;gap:8px;align-items:flex-start;margin-bottom:6px;">'
                        f'<span style="background:#DBEAFE;color:#1D4ED8;border-radius:50%;width:18px;height:18px;'
                        f'display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;flex-shrink:0;">{i}</span>'
                        f'<span style="font-size:11px;color:#334155;">{rec}</span></div>',
                        unsafe_allow_html=True
                    )

            resolved = df_titik[
                (df_titik["status"]=="Resolved") &
                (df_titik["corrective_action"].notna()) &
                (df_titik["corrective_action"].astype(str).str.strip() != "")
            ]["corrective_action"].unique().tolist()

            if resolved:
                st.markdown('<div style="font-size:12px;font-weight:700;color:#0F172A;margin:12px 0 6px;">💡 Action yang Pernah Berhasil</div>', unsafe_allow_html=True)
                for act in resolved[:3]:
                    st.markdown(f'<div style="background:#F0FDF4;border-left:3px solid #22C55E;border-radius:0 6px 6px 0;padding:6px 10px;margin-bottom:4px;font-size:11px;color:#334155;">✓ {act}</div>', unsafe_allow_html=True)

            st.markdown(
                '<div style="display:flex;gap:8px;margin-top:10px;">'
                + "".join([f'<span style="background:{bg};color:{fc};font-size:10px;font-weight:600;padding:3px 10px;border-radius:99px;">{s}: {int((df_titik["status"]==s).sum())}</span>'
                           for s,(fc,bg) in STATUS_COLOR.items()])
                + '</div>', unsafe_allow_html=True
            )

    # ════════════════════════════════════════════════════════════
    # TAB 2 — POLA & TREN
    # ════════════════════════════════════════════════════════════
    def _render_pola(self, df_f: pd.DataFrame):
        if df_f.empty:
            st.info("Tidak ada data.")
            return

        COLORS = ["#EF4444","#F59E0B","#8B5CF6","#06B6D4","#10B981","#6366F1","#94A3B8"]

        # ── Row 1: RC per Shift + Tren Status ────────────────────
        col1, col2 = st.columns(2, gap="medium")

        with col1:
            if "shift" in df_f.columns:
                shift_cat = df_f.groupby(["shift","category"]).size().reset_index(name="n")
                shifts    = sorted(df_f["shift"].dropna().unique())
                series_sc = []
                for i, cat in enumerate(RC_CATEGORIES):
                    vals = []
                    for sh in shifts:
                        sub = shift_cat[(shift_cat["shift"]==sh)&(shift_cat["category"]==cat)]
                        vals.append(int(sub["n"].sum()) if not sub.empty else 0)
                    if any(v>0 for v in vals):
                        series_sc.append({"name":cat,"type":"bar","stack":"total","data":vals,
                                          "itemStyle":{"color":COLORS[i%len(COLORS)]}})
                st_echarts({
                    "title":{"text":"Pola Root Cause per Shift","textStyle":{"fontSize":13,"fontWeight":700}},
                    "tooltip":{"trigger":"axis","axisPointer":{"type":"shadow"}},
                    "legend":{"bottom":0,"icon":"roundRect","itemWidth":10,"textStyle":{"fontSize":9}},
                    "grid":{"top":36,"bottom":80,"left":40,"right":10},
                    "xAxis":{"type":"category","data":[f"S{s}" for s in shifts],"axisLabel":{"fontSize":11}},
                    "yAxis":{"type":"value","axisLabel":{"fontSize":10}},
                    "series":series_sc,
                }, height="320px", key="presc_shift_cat")

        with col2:
            if "inputted_at" in df_f.columns:
                df_t = df_f.copy()
                df_t["_day"] = pd.to_datetime(df_t["inputted_at"], errors="coerce").dt.strftime("%d %b")
                df_t = df_t.dropna(subset=["_day"])
                days = df_t["_day"].unique().tolist()
                SCLR = {"Open":"#EF4444","Investigated":"#F59E0B","Resolved":"#22C55E"}
                series_st = []
                for status, clr in SCLR.items():
                    vals = [len(df_t[(df_t["_day"]==d)&(df_t["status"]==status)]) for d in days]
                    series_st.append({"name":status,"type":"line","data":vals,"smooth":True,
                                      "symbol":"circle","symbolSize":6,
                                      "lineStyle":{"color":clr,"width":2},
                                      "itemStyle":{"color":clr},"areaStyle":{"opacity":0.08}})
                st_echarts({
                    "title":{"text":"Tren Status Root Cause per Hari","textStyle":{"fontSize":13,"fontWeight":700}},
                    "tooltip":{"trigger":"axis"},
                    "legend":{"data":list(SCLR.keys()),"top":8,"right":8,"icon":"circle","itemWidth":8,"textStyle":{"fontSize":10}},
                    "grid":{"top":36,"bottom":32,"left":40,"right":20},
                    "xAxis":{"type":"category","data":days,"axisLabel":{"fontSize":9,"rotate":20}},
                    "yAxis":{"type":"value","axisLabel":{"fontSize":10}},
                    "dataZoom":[{"type":"inside"}],
                    "series":series_st,
                }, height="320px", key="presc_tren_status")

        st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

        # ── Row 2: Heatmap Part+Model × Kategori ─────────────────
        st.markdown('<div style="font-size:13px;font-weight:600;color:#0F172A;margin-bottom:8px;">Part+Model × Kategori Root Cause</div>', unsafe_allow_html=True)
        pm_cat = df_f.groupby(["part","model","category"]).size().reset_index(name="n")
        pm_keys = sorted((df_f["part"] + "|||" + df_f["model"]).unique().tolist())
        hm_data = []
        max_val = 0
        for xi, cat in enumerate(RC_CATEGORIES):
            for yi, pm in enumerate(pm_keys):
                parts2 = pm.split("|||", 1)
                p2, m2 = (parts2[0], parts2[1]) if len(parts2)==2 else (pm, "")
                sub = pm_cat[(pm_cat["part"]==p2)&(pm_cat["model"]==m2)&(pm_cat["category"]==cat)]
                val = int(sub["n"].sum()) if not sub.empty else 0
                if val > max_val: max_val = val
                hm_data.append([xi, yi, val])

        h_hm = max(180, len(pm_keys)*36 + 100)
        st_echarts({
            "tooltip":{"formatter":"function(p){return p.data[2]>0?'<b>'+p.marker+p.name+'</b><br/>'+p.data[2]:'';}"},
            "grid":{"top":24,"bottom":80,"left":120,"right":20},
            "xAxis":{"type":"category","data":RC_CATEGORIES,
                     "axisLabel":{"rotate":30,"fontSize":10},"splitArea":{"show":True}},
            "yAxis":{"type":"category","data":[p.replace("|||"," ") for p in pm_keys],
                     "axisLabel":{"fontSize":10},"splitArea":{"show":True}},
            "visualMap":{"min":0,"max":max(max_val,1),"calculable":True,
                         "orient":"horizontal","left":"center","bottom":10,
                         "inRange":{"color":["#FFF5F5","#EF4444"]},"textStyle":{"fontSize":9}},
            "series":[{"type":"heatmap","data":hm_data,
                       "label":{"show":True,"fontSize":9},
                       "emphasis":{"itemStyle":{"shadowBlur":10}}}],
        }, height=f"{h_hm}px", key="presc_hm_pm_cat")

        st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

        # ── Row 3: Top Backlog Open ───────────────────────────────
        df_open = df_f[df_f["status"]=="Open"].copy()
        if not df_open.empty:
            st.markdown('<div style="font-size:13px;font-weight:600;color:#DC2626;margin-bottom:8px;">🔴 Backlog Open — Belum Ditindaklanjuti</div>', unsafe_allow_html=True)
            top_open = (df_open.groupby(["part","model","ref","parameter","category"])
                        .size().reset_index(name="n")
                        .sort_values("n", ascending=False).head(15))
            labels_o = [f"{r['ref']} · {r['parameter']} ({r['part']} {r['model']})"
                        for _, r in top_open.iterrows()]
            values_o = top_open["n"].tolist()
            cats_o   = top_open["category"].tolist()
            CAT_CLR  = {"Mesin / Machine":"#EF4444","Setup / Fixture":"#F59E0B",
                        "Material":"#8B5CF6","Operator":"#06B6D4",
                        "Program CMM":"#10B981","Tooling":"#6366F1","Lainnya":"#94A3B8"}
            h_open = max(260, len(labels_o)*28+60)
            st_echarts({
                "tooltip":{"trigger":"axis","axisPointer":{"type":"shadow"}},
                "grid":{"top":12,"right":80,"bottom":8,"left":8,"containLabel":True},
                "xAxis":{"type":"value"},
                "yAxis":{"type":"category","data":list(reversed(labels_o)),"axisLabel":{"fontSize":9}},
                "dataZoom":[{"type":"slider","yAxisIndex":0,
                             "start":max(0,100-round(10/max(len(labels_o),1)*100)),"end":100,
                             "width":15,"right":5,"borderColor":"transparent",
                             "fillerColor":"rgba(220,38,38,0.15)",
                             "handleStyle":{"color":"#DC2626"}}],
                "series":[{"type":"bar",
                           "data":[{"value":v,"itemStyle":{"color":CAT_CLR.get(c,"#94A3B8"),
                                                           "borderRadius":[0,4,4,0]}}
                                   for v,c in zip(reversed(values_o),reversed(cats_o))],
                           "label":{"show":True,"position":"right","fontSize":10}}],
            }, height=f"{h_open}px", key="presc_backlog_open")
        else:
            st.success("✅ Tidak ada backlog Open saat ini.")

    # ════════════════════════════════════════════════════════════
    # TAB 3 — HISTORY SARAN
    # ════════════════════════════════════════════════════════════
    def _render_history_saran(self):
        """Riwayat alert NG yang pernah muncul di dashboard + sarannya."""
        from local_db import get_ng_notifs, get_root_causes

        _REKOMENDASI_SINGKAT = {
            "Mesin / Machine":  "Cek kalibrasi probe dan kondisi mesin sebelum lanjut produksi",
            "Setup / Fixture":  "Verifikasi posisi fixture dan datum reference",
            "Material":         "Lakukan incoming inspection — pisahkan material suspect",
            "Operator":         "Brief operator terkait SOP setup titik ini",
            "Program CMM":      "Update program CMM sesuai revisi drawing terbaru",
            "Tooling":          "Cek tool wear — ganti insert jika perlu",
            "Lainnya":          "Investigasi lebih lanjut bersama engineer",
        }
        _SARAN_PARAM = {
            "posisi": "Cek fixture dan datum reference",
            "position": "Cek fixture dan datum reference",
            "distance": "Verifikasi tool wear dan probe approach",
            "diameter": "Cek tool wear dan kondisi tooling",
        }

        notifs = get_ng_notifs()
        if not notifs:
            st.info("Belum ada alert NG yang tercatat di dashboard.")
            return

        # Buat lookup RC
        all_rcs = get_root_causes()
        df_rc = pd.DataFrame(all_rcs) if all_rcs else pd.DataFrame()
        rc_lookup = {}
        if not df_rc.empty:
            for (part, model, ref, param), g in df_rc.groupby(["part","model","ref","parameter"]):
                cat_counts = g["category"].value_counts()
                if len(cat_counts):
                    rc_lookup[(str(part),str(model),str(ref),str(param))] = {
                        "cat": cat_counts.index[0],
                        "pct": round(cat_counts.iloc[0]/len(g)*100),
                    }

        # Sort notifs terbaru duluan
        notifs_sorted = sorted(notifs, key=lambda x: x.get("created_at",""), reverse=True)

        # Filter
        fc1, fc2 = st.columns([2,1], gap="small")
        with fc1:
            parts_h = ["Semua"] + sorted({n.get("part","") for n in notifs if n.get("part")})
            fp = st.pills("Part", parts_h, default="Semua",
                          key="hist_part", selection_mode="single",
                          label_visibility="collapsed") or "Semua"
        with fc2:
            only_open = st.checkbox("Belum Ada Root Cause", key="hist_open", value=False)

        st.markdown(f'<div style="font-size:11px;color:#64748B;margin:6px 0 10px;">{len(notifs_sorted)} alert tercatat</div>', unsafe_allow_html=True)

        for n in notifs_sorted[:50]:
            part  = n.get("part","")
            model = n.get("model","")
            ref   = n.get("ref","")
            param = n.get("parameter","")
            sno   = n.get("sampleno","")
            dev   = n.get("deviation","")
            ts    = n.get("created_at","")[:16] if n.get("created_at") else "-"
            shift = n.get("shift","")

            if fp != "Semua" and part != fp:
                continue

            # Lookup saran
            key = (part, model, ref, param)
            if key in rc_lookup:
                info = rc_lookup[key]
                saran = _REKOMENDASI_SINGKAT.get(info["cat"], "Investigasi bersama engineer")
                saran_label = f"{saran} (dominan: {info['cat']} {info['pct']}%)"
            else:
                param_lower = str(param).lower()
                saran_label = next((v for k,v in _SARAN_PARAM.items() if k in param_lower),
                                   "Investigasi penyebab bersama engineer")

            # Cek apakah sudah ada RC
            has_rc = key in rc_lookup
            if only_open and has_rc:
                continue

            badge_bg = "#DCFCE7" if has_rc else "#FEE2E2"
            badge_fc = "#16A34A" if has_rc else "#DC2626"
            badge_lbl = "Root Cause Ada" if has_rc else "Belum Ada Root Cause"

            st.markdown(
                f'<div style="background:white;border:1px solid #E2E8F0;border-radius:10px;'
                f'padding:10px 14px;margin-bottom:4px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                f'<div style="flex:1;">'
                f'<div style="font-size:13px;font-weight:700;color:#0F172A;">'
                f'{part} {model} · Sample {sno}</div>'
                f'<div style="font-size:11px;color:#64748B;margin-top:2px;">'
                f'{ref} · {param} &nbsp;·&nbsp; Deviasi <b style="color:#DC2626;">{dev}</b>'
                f' &nbsp;·&nbsp; Shift {shift} &nbsp;·&nbsp; {ts}</div>'
                f'<div style="font-size:10px;color:#9A3412;margin-top:4px;background:#FFF7ED;'
                f'border-radius:4px;padding:2px 8px;display:inline-block;">💡 {saran_label}</div>'
                f'</div>'
                f'<span style="background:{badge_bg};color:{badge_fc};font-size:10px;'
                f'font-weight:700;padding:2px 8px;border-radius:99px;flex-shrink:0;'
                f'margin-left:10px;">{badge_lbl}</span>'
                f'</div></div>',
                unsafe_allow_html=True
            )