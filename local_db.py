"""
local_db.py
───────────
Persistent storage lokal menggunakan CSV + JSON files.

Struktur folder:
  data/
  ├── reports.csv          ← metadata laporan
  ├── messages.csv         ← notifikasi inbox
  └── reports/
      └── {report_id}.json ← data laporan lengkap

Migrasi ke Supabase: ganti fungsi-fungsi di sini,
interface ke report.py dan messages.py tidak perlu berubah.
"""

import os
import json
import csv
import uuid
from datetime import datetime
from pathlib import Path

# ── Folder & file paths ──────────────────────────────────────────
BASE_DIR      = Path(__file__).resolve().parent
DATA_DIR      = BASE_DIR / "data"
REPORTS_DIR   = DATA_DIR / "reports"
REPORTS_CSV     = DATA_DIR / "reports.csv"
MESSAGES_CSV    = DATA_DIR / "messages.csv"
NG_NOTIFS_CSV   = DATA_DIR / "ng_notifs.csv"

# ── CSV Headers ──────────────────────────────────────────────────
REPORT_COLS = [
    "id", "part", "model", "shift", "tanggal",
    "sent_by", "status", "created_at", "sent_at",
    "confirmed_by", "confirmed_at",
]

MESSAGE_COLS = [
    "id", "report_id", "from_user", "to_role",
    "created_at", "is_read",
]

NG_NOTIF_COLS = [
    "id", "from_user", "from_role", "to_role",
    "part", "model", "ref", "parameter", "sampleno",
    "date", "shift", "deviation", "kp",
    "category", "description", "pic", "status",
    "report_id", "created_at", "is_read",
]


# ═════════════════════════════════════════════════════════════════
#  INISIALISASI
# ═════════════════════════════════════════════════════════════════

def init_db() -> None:
    """Buat folder dan file CSV kalau belum ada."""
    DATA_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)

    if not REPORTS_CSV.exists():
        _write_csv(REPORTS_CSV, REPORT_COLS, [])

    if not MESSAGES_CSV.exists():
        _write_csv(MESSAGES_CSV, MESSAGE_COLS, [])

    if not NG_NOTIFS_CSV.exists():
        _write_csv(NG_NOTIFS_CSV, NG_NOTIF_COLS, [])
    else:
        # Migration: kalau header CSV lama, rewrite dengan kolom baru
        try:
            with open(NG_NOTIFS_CSV, "r", encoding="utf-8") as f:
                existing_cols = f.readline().strip().split(",")
            if set(existing_cols) != set(NG_NOTIF_COLS):
                rows = _read_csv(NG_NOTIFS_CSV, NG_NOTIF_COLS)
                _write_csv(NG_NOTIFS_CSV, NG_NOTIF_COLS, rows)
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════
#  HELPERS CSV
# ═════════════════════════════════════════════════════════════════

def _write_csv(path: Path, cols: list, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def _read_csv(path: Path, cols: list) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows   = [row for row in reader]
    # Fill kolom yang tidak ada di CSV lama dengan ""
    for row in rows:
        for c in cols:
            if c not in row:
                row[c] = ""
    return rows


def _append_csv(path: Path, cols: list, row: dict) -> None:
    exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if not exists:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in cols})


def _update_csv(path: Path, cols: list, key: str,
                key_val: str, updates: dict) -> None:
    rows = _read_csv(path, cols)
    for row in rows:
        if row.get(key) == key_val:
            row.update(updates)
    _write_csv(path, cols, rows)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ═════════════════════════════════════════════════════════════════
#  REPORTS
# ═════════════════════════════════════════════════════════════════

def save_report(report: dict, sent_by: str) -> str:
    """
    Simpan/update laporan ke JSON + metadata ke CSV.
    Return report_id.
    """
    init_db()
    rid = report.get("id") or str(uuid.uuid4())[:8]

    # Tulis JSON laporan
    json_path = REPORTS_DIR / f"{rid}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    # Cek apakah sudah ada di CSV
    rows = _read_csv(REPORTS_CSV, REPORT_COLS)
    existing = next((r for r in rows if r["id"] == rid), None)

    h = report.get("header", {})
    meta = {
        "id":           rid,
        "part":         h.get("namaPart", ""),
        "model":        h.get("modelName", ""),
        "shift":        h.get("shift", ""),
        "tanggal":      h.get("tanggal", ""),
        "sent_by":      sent_by,
        "status":       existing.get("status", "draft") if existing else "draft",
        "created_at":   existing.get("created_at", _now()) if existing else _now(),
        "sent_at":      existing.get("sent_at", "") if existing else "",
        "confirmed_by": existing.get("confirmed_by", "") if existing else "",
        "confirmed_at": existing.get("confirmed_at", "") if existing else "",
    }

    if existing:
        _update_csv(REPORTS_CSV, REPORT_COLS, "id", rid, meta)
    else:
        _append_csv(REPORTS_CSV, REPORT_COLS, meta)

    return rid


def update_report_status(report_id: str, status: str) -> bool:
    """Update status laporan: 'draft' atau 'sent'."""
    init_db()
    rows = _read_csv(REPORTS_CSV, REPORT_COLS)
    if not any(r["id"] == report_id for r in rows):
        return False
    updates = {"status": status}
    if status == "sent":
        updates["sent_at"] = _now()
    elif status == "draft":
        updates["sent_at"] = ""
    _update_csv(REPORTS_CSV, REPORT_COLS, "id", report_id, updates)
    return True


def confirm_report(report_id: str, confirmed_by: str) -> bool:
    """Produksi konfirmasi laporan sudah diterima."""
    init_db()
    _update_csv(REPORTS_CSV, REPORT_COLS, "id", report_id, {
        "status":       "confirmed",
        "confirmed_by": confirmed_by,
        "confirmed_at": _now(),
    })
    # Tandai semua pesan terkait sebagai dibaca
    msgs = _read_csv(MESSAGES_CSV, MESSAGE_COLS)
    for m in msgs:
        if m["report_id"] == report_id:
            m["is_read"] = "1"
    _write_csv(MESSAGES_CSV, MESSAGE_COLS, msgs)
    return True


def load_report_data(report_id: str) -> dict | None:
    """Baca data JSON laporan lengkap."""
    init_db()
    path = REPORTS_DIR / f"{report_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_reports(role: str, username: str) -> list[dict]:
    """
    Ambil daftar laporan sesuai role:
      - Measurement: laporan yang dikirim oleh username ini
      - Produksi: laporan yang sudah dikirim (status = sent / confirmed)
      - Admin: semua laporan
    """
    init_db()
    rows = _read_csv(REPORTS_CSV, REPORT_COLS)
    rows = sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)

    if role == "Measurement":
        return [r for r in rows if r["sent_by"] == username]
    else:  # Produksi, Admin — lihat semua laporan
        return rows


def get_report_meta(report_id: str) -> dict | None:
    """Ambil metadata laporan dari CSV."""
    init_db()
    rows = _read_csv(REPORTS_CSV, REPORT_COLS)
    return next((r for r in rows if r["id"] == report_id), None)


def delete_report(report_id: str) -> None:
    """Hapus laporan dari CSV + JSON file."""
    init_db()
    # Hapus dari CSV
    rows = _read_csv(REPORTS_CSV, REPORT_COLS)
    _write_csv(REPORTS_CSV, REPORT_COLS, [r for r in rows if r["id"] != report_id])
    # Hapus JSON
    json_path = REPORTS_DIR / f"{report_id}.json"
    if json_path.exists():
        json_path.unlink()


# ═════════════════════════════════════════════════════════════════
#  MESSAGES
# ═════════════════════════════════════════════════════════════════

def get_messages(role: str) -> list[dict]:
    """
    Ambil pesan inbox sesuai role.
    Return list dict dengan info laporan digabung.
    """
    init_db()
    msgs = _read_csv(MESSAGES_CSV, MESSAGE_COLS)
    msgs = [m for m in msgs if m.get("to_role") == role]
    msgs = sorted(msgs, key=lambda m: m.get("created_at", ""), reverse=True)

    # Gabungkan dengan metadata laporan
    result = []
    for m in msgs:
        meta = get_report_meta(m["report_id"]) or {}
        result.append({**m, **{f"rpt_{k}": v for k, v in meta.items()}})
    return result


def get_sent_messages(username: str) -> list[dict]:
    """Ambil pesan yang sudah dikirim oleh username ini (sent box)."""
    init_db()
    msgs = _read_csv(MESSAGES_CSV, MESSAGE_COLS)
    msgs = [m for m in msgs if m.get("from_user") == username]
    msgs = sorted(msgs, key=lambda m: m.get("created_at", ""), reverse=True)

    result = []
    for m in msgs:
        meta = get_report_meta(m["report_id"]) or {}
        result.append({**m, **{f"rpt_{k}": v for k, v in meta.items()}})
    return result


def mark_read(message_id: str) -> None:
    """Tandai pesan sudah dibaca."""
    init_db()
    _update_csv(MESSAGES_CSV, MESSAGE_COLS, "id", message_id, {"is_read": "1"})


def get_unread_count(role: str) -> int:
    """Hitung pesan belum dibaca untuk role tertentu (untuk badge sidebar)."""
    init_db()
    msgs = _read_csv(MESSAGES_CSV, MESSAGE_COLS)
    return sum(
        1 for m in msgs
        if m.get("to_role") == role and m.get("is_read") == "0"
    )


# ═════════════════════════════════════════════════════════════════
#  ROOT CAUSE
# ═════════════════════════════════════════════════════════════════

ROOT_CAUSES_CSV = DATA_DIR / "root_causes.csv"

RC_COLS = [
    "id", "rc_key",
    "date", "shift", "sampleno", "part", "model",
    "ref", "id_ukur", "parameter", "deviation",
    "category", "description", "corrective_action",
    "status", "inputted_by", "inputted_role", "pic",
    "inputted_at", "updated_at",
]

RC_CATEGORIES = [
    "Mesin / Machine",
    "Setup / Fixture",
    "Material",
    "Operator",
    "Program CMM",
    "Tooling",
    "Lainnya",
]

RC_STATUSES = ["Open", "Investigated", "Resolved"]


def _rc_key(date: str, shift: str, sampleno: str,
             part: str, model: str, ref: str, parameter: str) -> str:
    """Composite key unik per kejadian NG."""
    return f"{date}|{shift}|{sampleno}|{part}|{model}|{ref}|{parameter}"


def _init_rc() -> None:
    init_db()
    if not ROOT_CAUSES_CSV.exists():
        _write_csv(ROOT_CAUSES_CSV, RC_COLS, [])


def save_root_cause(data: dict) -> str:
    """
    Simpan atau update root cause.
    data harus berisi rc_key (atau field untuk membangunnya).
    Return rc_id.
    """
    _init_rc()
    key = data.get("rc_key") or _rc_key(
        data.get("date",""), data.get("shift",""),
        data.get("sampleno",""), data.get("part",""),
        data.get("model",""), data.get("ref",""),
        data.get("parameter",""),
    )

    rows     = _read_csv(ROOT_CAUSES_CSV, RC_COLS)
    existing = next((r for r in rows if r.get("rc_key") == key), None)
    rc_id    = existing["id"] if existing else str(uuid.uuid4())[:8]

    row = {
        "id":               rc_id,
        "rc_key":           key,
        "date":             data.get("date",""),
        "shift":            data.get("shift",""),
        "sampleno":         data.get("sampleno",""),
        "part":             data.get("part",""),
        "model":            data.get("model",""),
        "ref":              data.get("ref",""),
        "id_ukur":          data.get("id_ukur",""),
        "parameter":        data.get("parameter",""),
        "deviation":        data.get("deviation",""),
        "category":         data.get("category",""),
        "description":      data.get("description",""),
        "corrective_action":data.get("corrective_action",""),
        "status":           data.get("status","Investigated"),
        "inputted_by":      data.get("inputted_by",""),
        "inputted_role":    data.get("inputted_role",""),
        "pic":              data.get("pic",""),
        "inputted_at":      existing.get("inputted_at","") if existing else _now(),
        "updated_at":       _now(),
    }

    if existing:
        _update_csv(ROOT_CAUSES_CSV, RC_COLS, "rc_key", key, row)
    else:
        _append_csv(ROOT_CAUSES_CSV, RC_COLS, row)

    return rc_id


def get_root_causes(
    part: str = None, model: str = None,
    status: str = None,
) -> list[dict]:
    """Ambil semua root cause, dengan filter opsional."""
    _init_rc()
    rows = _read_csv(ROOT_CAUSES_CSV, RC_COLS)
    if part:
        rows = [r for r in rows if r.get("part") == part]
    if model:
        rows = [r for r in rows if r.get("model") == model]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return sorted(rows, key=lambda r: r.get("updated_at",""), reverse=True)


def get_root_cause_by_key(key: str) -> dict | None:
    """Ambil root cause berdasarkan composite key."""
    _init_rc()
    rows = _read_csv(ROOT_CAUSES_CSV, RC_COLS)
    return next((r for r in rows if r.get("rc_key") == key), None)


def delete_root_cause(rc_id: str) -> None:
    """Hapus root cause by id."""
    _init_rc()
    rows = [r for r in _read_csv(ROOT_CAUSES_CSV, RC_COLS)
            if r.get("id") != rc_id]
    _write_csv(ROOT_CAUSES_CSV, RC_COLS, rows)


def get_rc_stats() -> dict:
    """
    Statistik untuk pareto + heatmap.
    Return:
      category_counts : dict {category: count}
      ref_category    : dict {ref: {category: count}}
      shift_category  : dict {shift: {category: count}}
    """
    _init_rc()
    rows = _read_csv(ROOT_CAUSES_CSV, RC_COLS)
    rows = [r for r in rows if r.get("category")]

    cat_counts:  dict = {}
    ref_cat:     dict = {}
    shift_cat:   dict = {}

    for r in rows:
        cat   = r.get("category","Lainnya")
        ref   = r.get("ref","—")
        shift = r.get("shift","—")

        cat_counts[cat]  = cat_counts.get(cat, 0) + 1

        ref_cat.setdefault(ref, {})
        ref_cat[ref][cat] = ref_cat[ref].get(cat, 0) + 1

        shift_cat.setdefault(shift, {})
        shift_cat[shift][cat] = shift_cat[shift].get(cat, 0) + 1

    return {
        "category_counts": cat_counts,
        "ref_category":    ref_cat,
        "shift_category":  shift_cat,
    }


# ═════════════════════════════════════════════════════════════════
#  NG NOTIFICATIONS
# ═════════════════════════════════════════════════════════════════

def send_ng_notif(data: dict) -> str:
    """Kirim notifikasi titik NG ke Produksi. Dipanggil otomatis saat save RC."""
    init_db()
    nid = str(uuid.uuid4())[:8]
    row = {
        "id":          nid,
        "from_user":   data.get("from_user", ""),
        "from_role":   data.get("from_role", ""),
        "to_role":     data.get("to_role", "Produksi"),
        "part":        data.get("part", ""),
        "model":       data.get("model", ""),
        "ref":         data.get("ref", ""),
        "parameter":   data.get("parameter", ""),
        "sampleno":    data.get("sampleno", ""),
        "date":        data.get("date", ""),
        "shift":       data.get("shift", ""),
        "deviation":   data.get("deviation", ""),
        "kp":          data.get("kp", "0"),
        "category":    data.get("category", ""),
        "description": data.get("description", ""),
        "pic":         data.get("pic", ""),
        "status":      data.get("status", "Open"),
        "report_id":   data.get("report_id", ""),
        "created_at":  _now(),
        "is_read":     "0",
    }
    rows = _read_csv(NG_NOTIFS_CSV, NG_NOTIF_COLS)
    rows.append(row)
    _write_csv(NG_NOTIFS_CSV, NG_NOTIF_COLS, rows)
    return nid


def get_ng_notifs(to_role: str = "Produksi") -> list:
    """Ambil notifikasi NG untuk role tertentu, terbaru dulu."""
    init_db()
    rows = _read_csv(NG_NOTIFS_CSV, NG_NOTIF_COLS)
    rows = [r for r in rows if r.get("to_role") == to_role]
    return sorted(rows, key=lambda r: r.get("created_at",""), reverse=True)


def get_ng_notifs_sent(from_user: str) -> list:
    """Ambil notifikasi yang dikirim oleh user tertentu."""
    init_db()
    rows = _read_csv(NG_NOTIFS_CSV, NG_NOTIF_COLS)
    rows = [r for r in rows if r.get("from_user") == from_user]
    return sorted(rows, key=lambda r: r.get("created_at",""), reverse=True)


def mark_ng_notif_read(notif_id: str) -> None:
    init_db()
    rows = _read_csv(NG_NOTIFS_CSV, NG_NOTIF_COLS)
    for r in rows:
        if r["id"] == notif_id:
            r["is_read"] = "1"
    _write_csv(NG_NOTIFS_CSV, NG_NOTIF_COLS, rows)


def get_unread_ng_count(to_role: str = "Produksi") -> int:
    init_db()
    rows = _read_csv(NG_NOTIFS_CSV, NG_NOTIF_COLS)
    return sum(1 for r in rows
               if r.get("to_role") == to_role and r.get("is_read") == "0")