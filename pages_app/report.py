"""
pages/report.py
───────────────
Report Hub — landing page dengan pilihan jenis laporan.
  • WSIRD Produksi  → QCL Inspection (format dari settings.py)
  • QIS Report      → coming soon
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime
import copy
import json

from local_db import save_report, get_reports, load_report_data, get_report_meta, send_ng_notif, update_report_status


def _send_ng_notifs_from_report(report: dict, username: str) -> int:
    """Kirim notifikasi untuk setiap item NG di laporan ke Produksi."""
    items        = report.get('items', [])
    measurements = report.get('measurements', {})
    samples      = report.get('sample_order', report.get('samples', []))
    header       = report.get('header', {})

    model_name = header.get('modelName', '')
    part_name  = header.get('partName', header.get('namaPart', ''))  # partName = PartName murni

    # Konversi tanggal ke format "%d %b %Y" agar match rc_key di diagnostic
    from datetime import datetime as _dt
    tgl_raw = header.get('tanggal', '')
    try:
        date_str = _dt.strptime(tgl_raw, '%d/%m/%Y').strftime('%d %b %Y')
    except Exception:
        date_str = tgl_raw
    shift_str = str(header.get('shift', ''))

    count = 0
    for item in items:
        iid  = item['id']
        meas = measurements.get(iid, {})
        for ni, sname in enumerate(samples):
            val_str = meas.get(f'n{ni+1}', '')
            if not val_str:
                continue
            if is_oot(val_str, item):
                send_ng_notif({
                    "from_user":   username,
                    "from_role":   "Measurement",
                    "to_role":     "Produksi",
                    "part":        part_name,
                    "model":       model_name,
                    "ref":         item.get('g', item.get('id','')),
                    "parameter":   item.get('nm', ''),
                    "sampleno":    sname,
                    "date":        date_str,
                    "shift":       shift_str,
                    "deviation":   val_str,
                    "kp":          "1" if item.get('kp') else "0",
                    "category":    "",
                    "description": "",
                    "pic":         "",
                    "status":      "Open",
                    "report_id":   report.get('id', ''),
                })
                count += 1
    return count



# ─────────────────────────────────────────────────────────────────────────────
# DATA — 110 TITIK INSPEKSI
# id, g=group, nm=nama, t=tools, nom=nominal, tp=tol+, tm=tol-, kp=kritikal, mv=max_val
# ─────────────────────────────────────────────────────────────────────────────
ITEMS = [
    # PAGE 1
    dict(id='B000',  g='B000',   nm='FLATNESS FACE CRANK CASE',       t='CMM',           nom='',       tp=None,  tm=None,  kp=False, mv=0.1 ),
    dict(id='A001a', g='A000-1', nm='KERATAAN SURFACE A',              t='CMM',           nom='',       tp=None,  tm=None,  kp=False, mv=0.05),
    dict(id='A001b', g='A000-1', nm='KERATAAN ADJACENT BOSSES',        t='CMM',           nom='',       tp=None,  tm=None,  kp=False, mv=0.03),
    dict(id='A002a', g='A000-2', nm='KERATAAN SURFACE B',              t='CMM',           nom='',       tp=None,  tm=None,  kp=False, mv=0.05),
    dict(id='A002b', g='A000-2', nm='KERATAAN ADJACENT BOSSES',        t='CMM',           nom='',       tp=None,  tm=None,  kp=False, mv=0.03),
    dict(id='A003a', g='A001',   nm='POSISI X',                        t='CMM',           nom='83',     tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A003b', g='A001',   nm='POSISI Y',                        t='CMM',           nom='110',    tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A003c', g='A001',   nm='POSISI X Tap',                    t='CMM',           nom='83',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A003d', g='A001',   nm='POSISI Y Tap',                    t='CMM',           nom='110',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A004a', g='A002',   nm='DISTANCE X FROM A001',            t='CMM',           nom='136',    tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A004b', g='A002',   nm='DISTANCE Y FROM A001',            t='CMM',           nom='163.5',  tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A004c', g='A002',   nm='DISTANCE X FROM A001 Tap',        t='CMM',           nom='136',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A004d', g='A002',   nm='DISTANCE Y FROM A001 Tap',        t='CMM',           nom='163.5',  tp=0.20,  tm=0.20,  kp=False, mv=None),
    # PAGE 2
    dict(id='A005a', g='A003',   nm='POSISI X DARI A006',              t='CMM',           nom='48.5',   tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A005b', g='A003',   nm='POSISI Y DARI A006',              t='CMM',           nom='20',     tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A006a', g='A004',   nm='POSISI X DARI A003',              t='CMM',           nom='112',    tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A006b', g='A004',   nm='POSISI Y DARI A003',              t='CMM',           nom='112.5',  tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A006c', g='A004',   nm='KETEGAKLURUSAN THD R',            t='CMM',           nom='Max 0.01/10', tp=None, tm=None, kp=False, mv=None),
    dict(id='A007a', g='A005',   nm='POSISI X',                        t='CMM',           nom='0',      tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A007b', g='A005',   nm='POSISI Y',                        t='CMM',           nom='0',      tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A007c', g='A005',   nm='KESUMBUAN DIA 45 THD S',          t='CMM',           nom='',       tp=None,  tm=None,  kp=True,  mv=0.03),
    dict(id='A008a', g='A006',   nm='POSISI X',                        t='CMM',           nom='258',    tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A008b', g='A006',   nm='POSISI Y',                        t='CMM',           nom='0',      tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A008c', g='A006',   nm='KESUMBUAN THD T',                 t='CMM',           nom='',       tp=None,  tm=None,  kp=False, mv=0.03),
    dict(id='A009a', g='A007',   nm='JARAK DARI A006',                 t='CMM',           nom='47',     tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A009b', g='A007',   nm='POSISI Y',                        t='CMM',           nom='0',      tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A010a', g='A008',   nm='POSISI X',                        t='CMM',           nom='62.5',   tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A010b', g='A008',   nm='POSISI Y',                        t='CMM',           nom='22.9',   tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='B011a', g='B011',   nm='POSISI X',                        t='CMM',           nom='62.5',   tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='B011b', g='B011',   nm='POSISI Y',                        t='CMM',           nom='43',     tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='B012a', g='B012',   nm='POSISI X DARI B011',              t='CMM',           nom='405.5',  tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='B012b', g='B012',   nm='POSISI Y DARI B011',              t='CMM',           nom='45.5',   tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='B012c', g='B012',   nm='POSISI X DARI B011 Tap',          t='CMM',           nom='405.5',  tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B012d', g='B012',   nm='POSISI Y DARI B011 Tap',          t='CMM',           nom='45.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A019a', g='A019',   nm='POSISI X',                        t='CMM',           nom='93',     tp=0.1,   tm=0.1,   kp=False, mv=None),
    dict(id='A019b', g='A019',   nm='POSISI Y',                        t='CMM',           nom='80',     tp=0.1,   tm=0.1,   kp=False, mv=None),
    dict(id='A020a', g='A020',   nm='POSISI X',                        t='CMM',           nom='243.5',  tp=0.05,  tm=0.05,  kp=False, mv=None),
    dict(id='A020b', g='A020',   nm='POSISI Y',                        t='CMM',           nom='51',     tp=0.05,  tm=0.05,  kp=False, mv=None),
    # PAGE 3
    dict(id='B021a', g='B021',   nm='POSISI X',                        t='CMM',           nom='126.5',  tp=0.20,  tm=0.20,  kp=True,  mv=None),
    dict(id='B021b', g='B021',   nm='POSISI Y',                        t='CMM',           nom='129',    tp=0.20,  tm=0.20,  kp=True,  mv=None),
    dict(id='B022a', g='B022',   nm='POSISI X',                        t='CMM',           nom='332.5',  tp=0.20,  tm=0.20,  kp=True,  mv=None),
    dict(id='B022b', g='B022',   nm='POSISI Y',                        t='CMM',           nom='119.8',  tp=0.20,  tm=0.20,  kp=True,  mv=None),
    dict(id='B023a', g='B023',   nm='POSISI X',                        t='CMM',           nom='68',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B023b', g='B023',   nm='POSISI Y',                        t='CMM',           nom='120.5',  tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B024a', g='B024',   nm='POSISI X',                        t='CMM',           nom='257',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B024b', g='B024',   nm='POSISI Y',                        t='CMM',           nom='95.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B025a', g='B025',   nm='POSISI X',                        t='CMM',           nom='13',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B025b', g='B025',   nm='POSISI Y',                        t='CMM',           nom='104',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B026a', g='B026',   nm='POSISI X',                        t='CMM',           nom='13',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B026b', g='B026',   nm='POSISI Y',                        t='CMM',           nom='99',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A050a', g='A050',   nm='POSISI X',                        t='CMM',           nom='7',      tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A050b', g='A050',   nm='POSISI Y',                        t='CMM',           nom='142',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B073a', g='B073',   nm='POSISI X',                        t='CMM',           nom='381',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B073b', g='B073',   nm='POSISI Y',                        t='CMM',           nom='8',      tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B051a', g='B051',   nm='POSISI X',                        t='CMM',           nom='50.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B051b', g='B051',   nm='POSISI Y',                        t='CMM',           nom='54.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B052a', g='B052',   nm='POSISI X',                        t='CMM',           nom='50.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B052b', g='B052',   nm='POSISI Y',                        t='CMM',           nom='54.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B053a', g='B053',   nm='POSISI X',                        t='CMM',           nom='22',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B053b', g='B053',   nm='POSISI Y',                        t='CMM',           nom='77',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B054a', g='B054',   nm='POSISI X',                        t='CMM',           nom='117',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B054b', g='B054',   nm='POSISI Y',                        t='CMM',           nom='83.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B055a', g='B055',   nm='POSISI X',                        t='CMM',           nom='258.5',  tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B055b', g='B055',   nm='POSISI Y',                        t='CMM',           nom='87.2',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B056a', g='B056',   nm='POSISI X',                        t='CMM',           nom='287.5',  tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B056b', g='B056',   nm='POSISI Y',                        t='CMM',           nom='86.7',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    # PAGE 4
    dict(id='B057a', g='B057',   nm='POSISI X',                        t='CMM',           nom='157.5',  tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B057b', g='B057',   nm='POSISI Y',                        t='CMM',           nom='83.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B058a', g='B058',   nm='POSISI X',                        t='CMM',           nom='62.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B058b', g='B058',   nm='POSISI Y',                        t='CMM',           nom='78',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B060a', g='B060',   nm='POSISI X',                        t='CMM',           nom='86',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B060b', g='B060',   nm='POSISI Y',                        t='CMM',           nom='86',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B061a', g='B061',   nm='POSISI X',                        t='CMM',           nom='146.5',  tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B061b', g='B061',   nm='POSISI Y',                        t='CMM',           nom='0',      tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B062a', g='B062',   nm='POSISI X',                        t='CMM',           nom='256',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B062b', g='B062',   nm='POSISI Y',                        t='CMM',           nom='94.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B063a', g='B063',   nm='POSISI X',                        t='CMM',           nom='372',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B063b', g='B063',   nm='POSISI Y',                        t='CMM',           nom='56.8',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B064a', g='B064',   nm='POSISI X',                        t='CMM',           nom='66.3',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B064b', g='B064',   nm='POSISI Y',                        t='CMM',           nom='44',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B065a', g='B065',   nm='POSISI X',                        t='CMM',           nom='75.1',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='B065b', g='B065',   nm='POSISI Y',                        t='CMM',           nom='26.2',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A040a', g='A040',   nm='POSISI X',                        t='CMM',           nom='63.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A040b', g='A040',   nm='POSISI Y',                        t='CMM',           nom='8.5',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A041a', g='A041',   nm='POSISI X',                        t='CMM',           nom='77.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A041b', g='A041',   nm='POSISI Y',                        t='CMM',           nom='55',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A042a', g='A042',   nm='POSISI X',                        t='CMM',           nom='30',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A042b', g='A042',   nm='POSISI Y',                        t='CMM',           nom='127',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A043a', g='A043',   nm='POSISI X',                        t='CMM',           nom='39',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A043b', g='A043',   nm='POSISI Y',                        t='CMM',           nom='118.5',  tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A044a', g='A044',   nm='POSISI X',                        t='CMM',           nom='68',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A044b', g='A044',   nm='POSISI Y',                        t='CMM',           nom='60',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A045a', g='A045',   nm='POSISI X',                        t='CMM',           nom='8',      tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A045b', g='A045',   nm='POSISI Y',                        t='CMM',           nom='70',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    # PAGE 5
    dict(id='A046a', g='A046',   nm='POSISI X',                        t='CMM',           nom='57.1',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A046b', g='A046',   nm='POSISI Y',                        t='CMM',           nom='56.6',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A047a', g='A047',   nm='POSISI X',                        t='CMM',           nom='6.5',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A047b', g='A047',   nm='POSISI Y',                        t='CMM',           nom='63',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A071a', g='A071',   nm='POSISI X',                        t='CMM',           nom='110',    tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A071b', g='A071',   nm='POSISI Y',                        t='CMM',           nom='84.5',   tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A151a', g='A151',   nm='POSISI X',                        t='CMM',           nom='36',     tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A151b', g='A151',   nm='POSISI Y',                        t='CMM',           nom='31',     tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A151c', g='A151',   nm='POSISI X TAP',                    t='CMM',           nom='36',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A151d', g='A151',   nm='POSISI Y TAP',                    t='CMM',           nom='31',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A152a', g='A152',   nm='POSISI X',                        t='CMM',           nom='38',     tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A152b', g='A152',   nm='POSISI Y',                        t='CMM',           nom='31',     tp=0.05,  tm=0.05,  kp=True,  mv=None),
    dict(id='A152c', g='A152',   nm='POSISI X TAP',                    t='CMM',           nom='38',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A152d', g='A152',   nm='POSISI Y TAP',                    t='CMM',           nom='31',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A111a', g='A111',   nm='KERATAAN / FLATNESS',             t='CMM',           nom='',       tp=None,  tm=None,  kp=False, mv=0.05),
    dict(id='A111b', g='A111',   nm='SUDUT FACE COMP',                 t='CRM',           nom="10°",    tp=None,  tm=None,  kp=False, mv=None),
    dict(id='A153a', g='A153',   nm='POSISI X',                        t='CMM',           nom='19',     tp=0.15,  tm=0.15,  kp=False, mv=None),
    dict(id='A153b', g='A153',   nm='POSISI Y',                        t='CMM',           nom='15',     tp=0.20,  tm=0.20,  kp=False, mv=None),
    dict(id='A153c', g='A153',   nm='HEIGHT SPOT FACE',                t='CMM',           nom='64',     tp=0.10,  tm=0.10,  kp=False, mv=None),
    dict(id='A153d', g='A153',   nm='ROUGHNESS SPOT FACE',             t='ROUGHNESS TEST',nom='MAX 25S',tp=None,  tm=None,  kp=False, mv=None),
    dict(id='A154a', g='A154',   nm='ANGLE',                           t='CMM',           nom="10°",    tp=None,  tm=None,  kp=False, mv=None),
    dict(id='A154b', g='A154',   nm='POSISI Y',                        t='CMM',           nom='15',     tp=0.20,  tm=0.20,  kp=False, mv=None),
]

HDR_DEF = dict(
    unitProduksi='MACHINING CRANK CASE',
    namaPart='',
    noPart='',
    line='',
    shift='2',
    tanggal='',
    noDies='',
    namaOperator='',
    nrp='',
    noDoc='',
    tglBerlaku='',
)

# ─────────────────────────────────────────────────────────────────────────────
# KONFIGURASI HEADER PER PART + MODEL
# Key = "{PartName}_{ModelName}" — harus sama persis dengan nilai di CSV.
# Field yang tidak dicantumkan akan jatuh ke HDR_DEF.
# ─────────────────────────────────────────────────────────────────────────────
HDR_CONFIG: dict[str, dict] = {
    'CRCS L_K1AL L1': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'CRANK CASE COMP LEFT',
        noPart       = '11200-K1AL-L1-B000',
        line         = 'L1',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CRCS R_K1AL L1': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'CRANK CASE COMP RIGHT',
        noPart       = '11201-K1AL-L1-B000',
        line         = 'L1',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CRCS L_K1AL L2': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'CRANK CASE COMP LEFT',
        noPart       = '11200-K1AL-L2-B000',
        line         = 'L2',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CRCS R_K1AL L2': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'CRANK CASE COMP RIGHT',
        noPart       = '11201-K1AL-L2-B000',
        line         = 'L2',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CRCS L_K1AL L3': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'CRANK CASE COMP LEFT',
        noPart       = '11200-K1AL-L3-B000',
        line         = 'L3',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CRCS R_K1AL L3': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'CRANK CASE COMP RIGHT',
        noPart       = '11201-K1AL-L3-B000',
        line         = 'L3',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CRCS L_K2SA': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'CRANK CASE COMP LEFT',
        noPart       = '11200-K2SA-B000',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CRCS R_K2SA': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'CRANK CASE COMP RIGHT',
        noPart       = '11201-K2SA-B000',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CRCS L_K60': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'CRANK CASE COMP LEFT',
        noPart       = '11200-K60-B000',
        line         = 'N1 ~ N5',
        noDoc        = '64CK-OK6R-402-B01',
        tglBerlaku   = '01-Nov-17',
    ),
    'CRCS R_K60': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'CRANK CASE COMP RIGHT',
        noPart       = '11201-K60-B000',
        line         = 'N1 ~ N5',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'MISSION CASE_K60': dict(
        unitProduksi = 'MACHINING CRANK CASE',
        namaPart     = 'MISSION CASE',
        noPart       = '11300-K60-B000',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    # ── CYL COMP ──────────────────────────────────────────────────────────────
    'CYL COMP_K1AL': dict(
        unitProduksi = 'MACHINING CYLINDER',
        namaPart     = 'CYLINDER COMP',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL COMP_K2V': dict(
        unitProduksi = 'MACHINING CYLINDER',
        namaPart     = 'CYLINDER COMP',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL COMP_K2SA': dict(
        unitProduksi = 'MACHINING CYLINDER',
        namaPart     = 'CYLINDER COMP',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    # ── HOLDER WATER PUMP ────────────────────────────────────────────────────
    'HOLDER WATER PUMP_K60': dict(
        unitProduksi = 'MACHINING',
        namaPart     = 'HOLDER WATER PUMP',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    # ── CYL HEAD — K60 ───────────────────────────────────────────────────────
    'CYL HEAD GV_K60': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD GV',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD CAM_K60': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD CAM',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD NT_K60': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD NT',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD ROUGH_K60': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD ROUGH',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    # ── CYL HEAD — K2SA ──────────────────────────────────────────────────────
    'CYL HEAD GV_K2SA': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD GV',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD CAM_K2SA': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD CAM',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD NT_K2SA': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD NT',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD ROUGH_K2SA': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD ROUGH',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    # ── CYL HEAD — K1AL ──────────────────────────────────────────────────────
    'CYL HEAD GV_K1AL': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD GV',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD CAM_K1AL L2': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD CAM',
        noPart       = '',
        line         = 'L2',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD NT_K1AL L2': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD NT',
        noPart       = '',
        line         = 'L2',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD CAM_K1AL L3': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD CAM',
        noPart       = '',
        line         = 'L3',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD NT_K1AL L3': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD NT',
        noPart       = '',
        line         = 'L3',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    'CYL HEAD ROUGH_K1AL': dict(
        unitProduksi = 'MACHINING CYLINDER HEAD',
        namaPart     = 'CYLINDER HEAD ROUGH',
        noPart       = '',
        line         = '',
        noDoc        = '',
        tglBerlaku   = '',
    ),
    # Tambahkan kombinasi Part+Model lain di sini ↓
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def std_str(item):
    if item['mv'] is not None:
        return f"MAX {item['mv']}"
    if item['nom'] and item['tp'] is not None:
        return f"{item['nom']}  ±{item['tp']}"
    return item['nom'] or '—'

def is_oot(val, item):
    """
    Cek OOT berdasarkan nilai DEVIASI.
    - mv type (flatness): abs(deviation) > mv
    - nominal ± tol type: deviation di luar range [-tm, +tp]
    """
    try:
        v = float(val)
    except (TypeError, ValueError):
        return False
    if item.get('mv') is not None:
        return abs(v) > item['mv']
    tp = item.get('tp')
    tm = item.get('tm')
    if tp is not None and tm is not None:
        return not (-float(tm) <= v <= float(tp))
    return False

def init_meas():
    return {i['id']: {'n1': '', 'n2': '', 'n3': '', 'n4': '', 'n5': ''} for i in ITEMS}

def count_oot(report):
    """Jumlah nilai measurement yang NG (per cell, bukan per item)."""
    m      = report['measurements']
    items  = report.get('items', ITEMS)
    n_samp = len(report.get('samples', ['n1','n2','n3','n4','n5']))
    keys   = [f'n{i+1}' for i in range(n_samp)]
    return sum(
        1 for item in items
        for k in keys
        if is_oot(m.get(item['id'], {}).get(k, ''), item)
    )

def count_filled(report):
    """Jumlah titik inspeksi yang sudah ada minimal satu nilai terisi."""
    m      = report['measurements']
    items  = report.get('items', ITEMS)
    n_samp = len(report.get('samples', ['n1','n2','n3','n4','n5']))
    keys   = [f'n{i+1}' for i in range(n_samp)]
    return sum(
        1 for item in items
        if any(m.get(item['id'], {}).get(k, '') != '' for k in keys)
    )

def count_total_meas(report):
    """Total titik inspeksi (bukan items × samples)."""
    return len(report.get('items', ITEMS))

def count_kp_ng(report):
    """Jumlah nilai KP yang NG (per cell)."""
    m      = report['measurements']
    items  = report.get('items', ITEMS)
    n_samp = len(report.get('samples', ['n1','n2','n3','n4','n5']))
    keys   = [f'n{i+1}' for i in range(n_samp)]
    return sum(
        1 for item in items
        for k in keys
        if item.get('kp') and is_oot(m.get(item['id'], {}).get(k, ''), item)
    )

# Folder ilustrasi — sesuaikan dengan struktur folder proyekmu
# Konvensi nama file: {ModelName}.png, misal K60.png / K2VJ.png
from pathlib import Path as _Path
ILUSTRASI_DIR = str(_Path(__file__).resolve().parent.parent / "assets" / "ilustrasi")

def _load_ilustrasi_b64(model: str) -> str:
    """Return base64 string gambar ilustrasi untuk model, atau '' kalau tidak ada."""
    import base64
    if not model:
        return ''
    for ext in ['.png', '.jpg', '.jpeg', '.PNG', '.JPG']:
        path = _Path(ILUSTRASI_DIR) / f"{model}{ext}"
        if path.is_file():
            return base64.b64encode(path.read_bytes()).decode()
    return ''

def _load_ilustrasi(report: dict) -> None:
    """Patch report['ilustrasi_img'] jika belum ada."""
    if not report.get('ilustrasi_img'):
        model = report.get('header', {}).get('modelName', '')
        report['ilustrasi_img'] = _load_ilustrasi_b64(model)

def today_str():
    d = datetime.now()
    return f"{d.day:02d}/{d.month:02d}/{d.year}"

# ─────────────────────────────────────────────────────────────────────────────
# DUMMY DATA
# ─────────────────────────────────────────────────────────────────────────────

def _dummy_meas():
    import random
    m = init_meas()
    for item in ITEMS:
        if item['tp'] is not None:
            nom = float(item['nom']) if item['nom'] and item['nom'].replace('.','').replace('-','').isdigit() else 0
            for n in ['n1','n2','n3','n4','n5']:
                val = nom + round(random.uniform(-item['tp']*0.9, item['tp']*0.9), 3)
                m[item['id']][n] = str(val)
        elif item['mv'] is not None:
            for n in ['n1','n2','n3','n4','n5']:
                m[item['id']][n] = str(round(random.uniform(0, item['mv']*0.85), 3))
    return m

DUMMY_REPORTS = [
    {
        'id': '1001',
        'createdAt': '2026-04-14T07:00:00',
        'submittedBy': 'Budi Santoso',
        'header': {**HDR_DEF, 'tanggal': '14/04/2026', 'shift': '1', 'namaOperator': 'Budi Santoso', 'nrp': '12345', 'noDies': 'D-001'},
        'measurements': _dummy_meas(),
    },
    {
        'id': '1002',
        'createdAt': '2026-04-14T15:00:00',
        'submittedBy': 'Siti Rahayu',
        'header': {**HDR_DEF, 'tanggal': '14/04/2026', 'shift': '2', 'namaOperator': 'Siti Rahayu', 'nrp': '67890', 'noDies': 'D-001'},
        'measurements': _dummy_meas(),
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# CSV / DATABASE LOADER
# Ganti load_cmm_data() dengan query ke database Anda nanti
# ─────────────────────────────────────────────────────────────────────────────



@st.cache_data
def load_cmm_data(csv_path: str) -> pd.DataFrame:
    """Baca CSV CMM. Ganti dengan query DB nanti."""
    df = pd.read_csv(csv_path, dtype={'SampleNo': str})
    df['Date'] = pd.to_datetime(df['Date'])
    df['DateOnly'] = df['Date'].dt.date.astype(str)
    return df

def get_report_options(df: pd.DataFrame) -> pd.DataFrame:
    """Daftar laporan yang bisa dibuat dari data CSV (Category=Produksi)."""
    prod = df[df['Category'] == 'Produksi']
    opts = (prod.groupby(['DateOnly', 'Shift', 'PartName', 'ModelName'])
                .size().reset_index(name='rows'))
    return opts

def build_report_from_csv(df: pd.DataFrame, model: str, date_str: str, shift: int,
                          part_name: str = '') -> dict:
    """
    Buat report dict dari CSV untuk model+partname+tanggal+shift tertentu.
    Hasilnya sama persis dengan struktur report manual.
    """


    # Filter data — sertakan PartName kalau diberikan
    mask = (
        (df['ModelName'] == model) &
        (df['DateOnly']  == date_str) &
        (df['Shift']     == shift) &
        (df['Category']  == 'Produksi')
    )
    if part_name:
        mask = mask & (df['PartName'] == part_name)
    data = df[mask].copy()

    if data.empty:
        return None

    # Ambil info header dari baris pertama
    first = data.iloc[0]
    tanggal_dt = pd.to_datetime(date_str)
    tanggal_fmt = f"{tanggal_dt.day:02d}/{tanggal_dt.month:02d}/{tanggal_dt.year}"
    _part_name = part_name or str(first['PartName'])

    # Derive samples dari data aktual — urutan kemunculan pertama
    samples = list(dict.fromkeys(
        data.sort_values(['Date', 'Cycle'])['SampleNo'].astype(str).tolist()
    ))
    if not samples:
        samples = ['N1']

    # Lookup HDR_CONFIG dengan key "{PartName}_{ModelName}"
    _cfg_key = f"{_part_name}_{model}"
    _part_cfg = HDR_CONFIG.get(_cfg_key, {})
    header = {
        **HDR_DEF,
        **_part_cfg,                       # override per part+model dari HDR_CONFIG
        'tanggal':   tanggal_fmt,
        'shift':     str(shift),
        'partName':  str(first['PartName']),
        'namaPart':  _part_name,            # langsung dari PartName CSV
        'modelName': model,
    }

    # Pivot Actual
    pivot = (data.pivot_table(
        index=['ref', 'ID', 'point', 'Nominal', 'Uppertol', 'Lowertol', 'KP'],
        columns='SampleNo',
        values='Actual',
        aggfunc='first'
    ).reset_index())
    for s in samples:
        if s not in pivot.columns:
            pivot[s] = ''

    # Pivot Deviation (untuk template Excel)
    pivot_dev = (data.pivot_table(
        index=['ref', 'ID', 'point'],
        columns='SampleNo',
        values='Deviation',
        aggfunc='first'
    ).reset_index())
    for s in samples:
        if s not in pivot_dev.columns:
            pivot_dev[s] = ''
    # Build dict: iid → {n1:dev, n2:dev, ...}
    dev_meas_tmp = {}
    for _, row in pivot_dev.iterrows():
        iid = str(row['ID']).strip()
        meas = {}
        for ni, s in enumerate(samples):
            v = row.get(s, '')
            meas[f'n{ni+1}'] = (
                '' if pd.isna(v) or v == ''
                else f"{float(v):.4f}".rstrip('0').rstrip('.')
            )
        dev_meas_tmp[iid] = meas

    # Build items + measurements dari pivot Actual
    items = []
    measurements       = {}
    deviation_measurements = {}
    for _, row in pivot.iterrows():
        ref   = str(row['ref']).strip()
        iid   = str(row['ID']).strip()
        point = str(row['point']).strip()
        nom   = row['Nominal']
        tp    = row['Uppertol']
        tm    = row['Lowertol']
        kp    = bool(row['KP'])

        if nom == 0 and tm == 0:
            mv = tp; tp_val = None; tm_val = None
        else:
            mv = None; tp_val = tp; tm_val = abs(tm)

        item = dict(
            id=iid, g=ref if ref != '-' else iid,
            nm=point, t='CMM', nom=str(nom),
            tp=tp_val, tm=tm_val, kp=kp, mv=mv,
        )
        items.append(item)

        meas = {}
        for ni, s in enumerate(samples):
            v = row.get(s, '')
            meas[f'n{ni+1}'] = (
                '' if pd.isna(v) or v == ''
                else f"{float(v):.4f}".rstrip('0').rstrip('.')
            )
        measurements[iid]           = dev_meas_tmp.get(iid, meas)
        deviation_measurements[iid] = dev_meas_tmp.get(iid, meas)  # alias, same

    # Cari ilustrasi berdasarkan part+model (bukan model saja)
    _ilustrasi_img  = _get_ilustrasi_b64(model, _part_name)
    _ilustrasi_path = ''
    # Cari file path dari _ILUSTRASI_MAP pakai key yang sama dengan _get_ilustrasi_b64
    _ikey = f"{model}_{_part_name}".replace(' ', '_').upper()
    _best_len, _best_file = 0, ''
    for _mk, _fname in _ILUSTRASI_MAP.items():
        if _ikey.startswith(_mk.upper()) and len(_mk) > _best_len:
            _best_len, _best_file = len(_mk), _fname
    if _best_file:
        _p = _ASSETS_DIR / _best_file
        if _p.exists():
            _ilustrasi_path = str(_p)

    return {
        'id':                    f"{model}_{_part_name}_{date_str}_{shift}".replace(' ', '_'),
        'createdAt':             pd.Timestamp.now().isoformat(),
        'submittedBy':           'CMM Auto',
        'header':                header,
        'items':                 items,
        'samples':               samples,
        'sample_order':          list(samples),
        'measurements':          measurements,
        'deviation_measurements': deviation_measurements,
        'ilustrasi_img':         _ilustrasi_img,
        'ilustrasi_path':        _ilustrasi_path,
    }





# Generates the exact visual replica of the AHM QCL report
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# ILUSTRASI — mapping model+part → file di assets/ilustrasi/
# Key: "{MODEL}_{PART}" dengan spasi diganti _ (sama persis dengan descriptive.py)
# ─────────────────────────────────────────────────────────────────────────────

_ASSETS_DIR = _Path(__file__).resolve().parent.parent / "assets" / "ilustrasi"

_ILUSTRASI_MAP: dict[str, str] = {
    "K2VJ_CYL_COMP":   "K2VJ.png",
    "K60_CRCS_L":      "K60.png",
    "K2SA_CYL_COMP":   "K2SA.png",
    "K1AL_L1_CRCS_L":  "K1AL_L1.jpg",
    "K1AL_L1_CRCS_R":  "K1AL_L1_R.jpg",
    "K1AL_L2_CRCS_L":  "K1AL_L2.jpg",
    "K1AL_L2_CRCS_R":  "K1AL_L2_R.jpg",
    "K1AL_L3_CRCS_L":  "K1AL_L3.jpg",
    "K1AL_L3_CRCS_R":  "K1AL_L3_R.jpg",
    "K2SA_CRCS_L":     "K2SA_CRCS_L.jpg",
    "K2SA_CRCS_R":     "K2SA_CRCS_R.jpg",
    "K60_CRCS_R":      "K60_R.jpg",
    "K60_MISSION":     "K60_MISSION.jpg",
    # ── CYL COMP (placeholder — isi filename saat file tersedia) ─────────────
    "K1AL_CYL_COMP":           "K1AL_CYL_COMP.jpg",       # TODO: sediakan file
    "K2V_CYL_COMP":            "K2V.png",        # TODO: sediakan file
    # K2SA_CYL_COMP sudah ada di atas
    # ── HOLDER WATER PUMP ────────────────────────────────────────────────────
    "K60_HOLDER_WATER_PUMP":   "K60_WP.jpg",  # TODO: sediakan file
    # ── CYL HEAD — K60 ───────────────────────────────────────────────────────
    "K60_CYL_HEAD_GV":         "K60_GV.jpg",     # TODO: sediakan file
    "K60_CYL_HEAD_CAM":        "K60_CAM.jpg",    # TODO: sediakan file
    "K60_CYL_HEAD_NT":         "K60_NT.jpg",     # TODO: sediakan file
    "K60_CYL_HEAD_ROUGH":      "K60_ROUGH.jpg",  # TODO: sediakan file
    # ── CYL HEAD — K2SA ──────────────────────────────────────────────────────
    "K2SA_CYL_HEAD_GV":        "K2SA_GV.jpg",    # TODO: sediakan file
    "K2SA_CYL_HEAD_CAM":       "K2SA.jpg",   # TODO: sediakan file
    "K2SA_CYL_HEAD_NT":        "K2SA_NT.jpg",    # TODO: sediakan file
    "K2SA_CYL_HEAD_ROUGH":     "K2SA_ROUGH.jpg", # TODO: sediakan file
    # ── CYL HEAD — K1AL ──────────────────────────────────────────────────────
    "K1AL_CYL_HEAD_GV":        "K1AL_GV.jpg",    # TODO: sediakan file
    "K1AL_L2_CYL_HEAD_CAM":    "K1AL_CAM.jpg", # TODO: sediakan file
    "K1AL_L2_CYL_HEAD_NT":     "K1AL_NT.jpg",  # TODO: sediakan file
    "K1AL_L3_CYL_HEAD_CAM":    "K1AL_CAM.jpg", # TODO: sediakan file
    "K1AL_L3_CYL_HEAD_NT":     "K1AL_NT.jpg",  # TODO: sediakan file
    "K1AL_CYL_HEAD_ROUGH":     "K1AL_ROUGH.jpg", # TODO: sediakan file
}

_ILUSTRASI_B64_CACHE: dict[str, str] = {}

def _get_ilustrasi_b64(model: str, part_name: str) -> str:
    """Cari ilustrasi berdasarkan key '{MODEL}_{PART}' (sama dengan descriptive.py)."""
    key = f"{model}_{part_name}".replace(' ', '_').upper()

    # Cari key yang paling panjang cocok (spesifik ke umum)
    matched_file = ''
    best_len = 0
    for map_key, fname in _ILUSTRASI_MAP.items():
        mk = map_key.upper()
        if key.startswith(mk) and len(mk) > best_len:
            matched_file = fname
            best_len = len(mk)

    if not matched_file:
        return ''
    if matched_file in _ILUSTRASI_B64_CACHE:
        return _ILUSTRASI_B64_CACHE[matched_file]

    img_path = _ASSETS_DIR / matched_file
    if not img_path.exists():
        return ''

    import base64
    ext    = img_path.suffix.lower()
    mime   = 'image/png' if ext == '.png' else 'image/jpeg'
    result = f'data:{mime};base64,{base64.b64encode(img_path.read_bytes()).decode()}'
    _ILUSTRASI_B64_CACHE[matched_file] = result
    return result


def build_report_html(report) -> str:
    """Render laporan QCL sebagai HTML read-only (view mode)."""
    h = report['header']
    m = report['measurements']
    illustration = report.get('illustration', '')  # base64 image or empty

    # Build illustration HTML
    if illustration:
        illustration_html = f'<img src="data:image/png;base64,{illustration}" style="max-width:100%; max-height:80px; object-fit:contain;" />'
    else:
        illustration_html = '<div style="font-size:8px; color:#bbb; margin-top:20px;">(logo/stamp)</div>'

    # Build ILUSTRASI section HTML — auto-load dari assets/ilustrasi
    _model    = h.get('modelName', '')
    _part     = h.get('partName',  h.get('namaPart', ''))
    _img_data = report.get('ilustrasi_img', '') or _get_ilustrasi_b64(_model, _part)
    if _img_data:
        # strip prefix kalau sudah ada (dari cache _get_ilustrasi_b64 sudah include prefix)
        if _img_data.startswith('data:'):
            _img_src = _img_data
        else:
            _img_src = f'data:image/jpeg;base64,{_img_data}'
        ilustrasi_section = f'<img src="{_img_src}" style="max-width:100%; max-height:260px; object-fit:contain;" />'
    else:
        ilustrasi_section = '<div style="font-size:11px; color:#ccc; padding-top:100px;">[ Ilustrasi tidak tersedia ]</div>'

    # Use dynamic items from CSV report, or fall back to static ITEMS
    items_to_render  = report.get('items', ITEMS)
    samples_data     = report.get('samples', ['N1','N2','N3','N4','N5'])  # data keys (n1..nN)
    sample_order     = report.get('sample_order', samples_data)           # display labels (reorderable)
    # Guard: sample_order bisa beda panjang dgn samples_data (rename/edit)
    if len(sample_order) != len(samples_data):
        sample_order = list(samples_data)  # fallback ke samples asli
    n_samples        = len(sample_order)
    samples_to_render = sample_order  # used for TH labels
    sample_labels    = {f'n{i+1}': sample_order[i] for i in range(n_samples)}

    # Compute group rowspans
    span = {}
    for item in items_to_render:
        span[item['g']] = span.get(item['g'], 0) + 1

    # Build inspection rows
    seen = {}
    rows_html = ''
    for item in items_to_render:
        is_first = item['g'] not in seen
        if is_first:
            seen[item['g']] = True

        meas = m.get(item['id'], {})
        cell_style_base = 'padding:2px 5px; border:1px solid #888; font-size:9.5px; vertical-align:middle;'

        # Sample value cells (read-only)
        sample_cells = ''
        for n in [f'n{i+1}' for i in range(len(samples_to_render))]:
            val = meas.get(n, '')
            oot = is_oot(val, item)
            val_style = cell_style_base + 'text-align:center; font-family:Arial,monospace; background:#f0f4ff;'
            if oot:
                if item.get('kp'):
                    val_style += 'color:#92400E; font-weight:bold; background:#FEF9C3;'  # KP: kuning
                else:
                    val_style += 'color:#cc0000; font-weight:bold; background:#ffe8e8;'  # NG biasa: merah
            sample_cells += f'<td style="{val_style}">{val}</td>'

        # Group cell (rowspan on first)
        grp_cell = ''
        if is_first:
            grp_cell = f'''<td rowspan="{span[item['g']]}" style="
                {cell_style_base}
                text-align:center; font-weight:bold; font-family:Arial,monospace;
                background:#dce8ff; color:#0a1e45; border-right:2px solid #1a4080;
                font-size:9px; white-space:nowrap;">
                {item['g']}
            </td>'''

        nm_style = cell_style_base
        if item['kp']:
            nm_style += 'color:#92400E; font-weight:bold; background:#FFFBEB;'

        kp_cell = '<span style="background:#FEF08A;color:#713F12;font-weight:bold;font-size:8px;padding:1px 3px;border-radius:2px;">KP</span>' if item['kp'] else ''

        rows_html += f'''<tr>
            {grp_cell}
            <td style="{nm_style}">{item['nm']}</td>
            <td style="{cell_style_base} text-align:center; font-size:9px; color:#555;">{item['t']}</td>
            <td style="{cell_style_base} text-align:center; font-family:Arial,monospace; font-size:9px; white-space:nowrap;">{std_str(item)}</td>
            <td style="{cell_style_base} text-align:center;">{kp_cell}</td>
            <td style="{cell_style_base} text-align:center; font-size:9px; color:#555;">HB</td>
            {sample_cells}
        </tr>'''

    form_start = ''
    form_end   = ''
    save_btn   = ''

    # JS drag-and-drop: swap kolom dan tulis order baru ke URL query param
    _so_json = json.dumps(sample_order)
    rid      = report.get('id', 'rpt').replace('-','_')
    js = f'''
    <style>
      th.sample-th {{ cursor:grab; user-select:none; }}
      th.sample-th.drag-over {{ outline:2px solid #60a5fa !important; outline-offset:-2px; }}
    </style>
    <script>
    (function(){{
      var order = {_so_json};
      var src = null;
      document.querySelectorAll('th.sample-th').forEach(function(th){{
        th.draggable = true;
        th.addEventListener('dragstart', function(){{
          src = th.textContent.trim(); th.style.opacity='0.45';
        }});
        th.addEventListener('dragend', function(){{
          th.style.opacity='';
          document.querySelectorAll('th.sample-th').forEach(function(t){{t.classList.remove('drag-over');}});
        }});
        th.addEventListener('dragover', function(e){{
          e.preventDefault(); th.classList.add('drag-over');
        }});
        th.addEventListener('dragleave', function(){{
          th.classList.remove('drag-over');
        }});
        th.addEventListener('drop', function(e){{
          e.preventDefault(); th.classList.remove('drag-over');
          var tgt = th.textContent.trim();
          if (!src || src===tgt) return;
          // Swap DOM
          document.querySelectorAll('th.sample-th').forEach(function(t){{
            var txt=t.textContent.trim();
            if(txt===src) t.textContent=tgt;
            else if(txt===tgt) t.textContent=src;
          }});
          // Swap array
          var si=order.indexOf(src), ti=order.indexOf(tgt);
          if(si>=0&&ti>=0){{var tmp=order[si];order[si]=order[ti];order[ti]=tmp;}}
          src = null;
          // Tulis ke URL — satu key, value = rid:json agar tidak menumpuk
          try{{
            var u=new URL(window.parent.location.href);
            u.searchParams.set('_so', '{rid}:' + JSON.stringify(order));
            window.parent.history.replaceState({{}}, '', u.toString());
          }}catch(err){{}}
        }});
      }});
    }})();
    </script>
    '''

    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
        * {{ box-sizing: border-box; margin:0; padding:0; }}
        body {{ font-family: Arial, sans-serif; font-size:10px; background:white; }}
        table {{ border-collapse: collapse; }}
        input:focus {{ border-color:#1a4080 !important; box-shadow:0 0 0 2px rgba(26,64,128,.2); }}
        @media print {{
            .no-print {{ display:none !important; }}
            body {{ background:white; }}
        }}
    </style>
    </head>
    <body style="padding:12px 12px 4px 12px;">

    {form_start}

    <table style="width:100%; border-collapse:collapse; border:1.5px solid #333; table-layout:fixed;">
      <colgroup>
        <col style="width:10%;"> <col style="width:8%;">  <col style="width:10%;"> <col style="width:15%;"> <col style="width:10%;"> <col style="width:7%;">  <col style="width:10%;"> <col style="width:10%;"> <col style="width:10%;"> <col style="width:10%;"> </colgroup>

      <tr>
        <td colspan="3" rowspan="2" style="text-align:center; padding:10px 4px; border:1px solid #333; vertical-align:middle;">
          <div style="color:#cc0000; font-weight:900; font-size:28px; letter-spacing:2px; line-height:1;">AHM</div>
          <div style="font-size:10px; color:#333; font-weight:700; margin-top:2px;">PT Astra Honda Motor</div>
        </td>
        <td colspan="4" rowspan="3" style="text-align:center; font-weight:900; font-size:16px; letter-spacing:0.5px; padding:7px 4px; border:1px solid #333; vertical-align:middle;">
          WORK STATION INSPECTION RESULT DATA QCL
        </td>
        <td colspan="2" style="padding:2px 5px; border:1px solid #333; font-size:9px; text-align:center; font-weight:bold;">NO.<br>DOKUMEN</td>
        <td colspan="1" style="padding:2px 5px; border:1px solid #333; font-weight:bold; font-size:10px; text-align:center;">{h.get('noDoc','')}</td>
      </tr>

      <tr>
        <td colspan="2" style="padding:2px 5px; border:1px solid #333; font-size:9px; text-align:center; font-weight:bold;">TGL<br>BERLAKU</td>
        <td colspan="1" style="padding:2px 5px; border:1px solid #333; font-size:10px; text-align:center; font-weight:bold;">{h.get('tglBerlaku','')}</td>
      </tr>

      <tr>
        <td colspan="3" style="padding:4px 6px; border:1px solid #333; font-size:9px; font-weight:bold;">PROCESS ENGINEERING B DEPT.</td>
        <td colspan="1" style="padding:4px 5px; border:1px solid #333; font-size:9px; text-align:center; font-weight:bold;">REV &nbsp; 0</td>
        <td colspan="1" style="padding:4px 5px; border:1px solid #333; font-size:9px; text-align:center; font-weight:bold;">HAL</td>
        <td colspan="1" style="padding:4px 5px; border:1px solid #333; font-size:9px; text-align:center; font-weight:bold;">1 DARI 5</td>
      </tr>

      <tr>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:9px; font-weight:bold; white-space:nowrap;">UNIT PRODUKSI</td>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:10px; font-weight:bold;">: {h.get('unitProduksi','')}</td>
        <td colspan="3" style="padding:3px 5px; border:1px solid #333; font-size:11px; font-weight:900; background:#FFFF00; color:#000; text-align:center; letter-spacing:1px;">CONFIDENTIAL STATUS</td>
        <td colspan="1" style="padding:3px 4px; border:1px solid #333; font-size:10px; font-weight:bold; text-align:center;">QCL 1</td>
        <td colspan="1" style="padding:3px 4px; border:1px solid #333; font-size:10px; font-weight:bold; text-align:center;">QCL 2</td>
        <td colspan="1" style="padding:3px 4px; border:1px solid #333; font-size:10px; font-weight:bold; text-align:center;">QCL 3</td>
      </tr>

      <tr>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:9px; font-weight:bold; white-space:nowrap;">NAMA PART</td>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:10px; font-weight:bold;">: {h.get('namaPart','')}</td>
        <td colspan="2" rowspan="5" style="border:1px solid #333; padding:6px; vertical-align:middle; text-align:center;">
          {illustration_html}
        </td>
        <td colspan="1" style="padding:3px 5px; border:1px solid #333; font-size:9px; font-weight:bold; text-align:center;">TANGGAL</td>
        <td colspan="1" style="border:1px solid #333;"></td>
        <td colspan="1" style="border:1px solid #333;"></td>
        <td colspan="1" style="border:1px solid #333;"></td>
      </tr>

      <tr>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:9px; font-weight:bold; white-space:nowrap;">NO. PART</td>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:10px; font-weight:bold;">: {h.get('noPart','')}</td>
        <td colspan="1" rowspan="3" style="padding:3px 5px; border:1px solid #333; font-size:9px; font-weight:bold; text-align:center; vertical-align:middle;">TANDA<br>TANGAN</td>
        <td colspan="1" rowspan="3" style="border:1px solid #333;"></td>
        <td colspan="1" rowspan="3" style="border:1px solid #333;"></td>
        <td colspan="1" rowspan="3" style="border:1px solid #333;"></td>
      </tr>

      <tr>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:9px; font-weight:bold; white-space:nowrap;">LINE</td>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:10px; font-weight:bold;">: {h.get('line','')}</td>
      </tr>

      <tr>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:9px; font-weight:bold; white-space:nowrap;">SHIFT</td>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:10px; font-weight:bold;">: {h.get('shift','')}</td>
      </tr>

      <tr>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:9px; font-weight:bold; white-space:nowrap;">TANGGAL</td>
        <td colspan="2" style="padding:3px 5px; border:1px solid #333; font-size:10px; font-weight:bold;">
            <div style="display:flex; justify-content:space-between;">
                <span>: {h.get('tanggal','')}</span>
                <span style="font-size:9px;">NO DIES: {h.get('noDies','')}</span>
            </div>
        </td>
        <td colspan="1" style="padding:3px 5px; border:1px solid #333; font-size:9px; font-weight:bold; text-align:center;">NAMA /<br>NRP</td>
        <td colspan="1" style="border:1px solid #333; font-size:9px; text-align:center; font-weight:bold; vertical-align:bottom; padding-bottom:2px;">
            {h.get('namaOperator','')}<br>{h.get('nrp','')}
        </td>
        <td colspan="1" style="border:1px solid #333;"></td>
        <td colspan="1" style="border:1px solid #333;"></td>
      </tr>

    </table>

    <!-- ══ ILUSTRASI ════════════════════════════════════════════════════ -->
    <div style="border:1px solid #333; border-top:none; padding:6px 8px;
         text-align:center; background:#fafafa; min-height:50px;">
      {ilustrasi_section}
    </div>

    <!-- ══ INSPECTION TABLE ═══════════════════════════════════════════ -->
    <table style="width:100%; border-collapse:collapse; margin-top:0;">
      <thead>
        <tr>
          <th style="background:#0a1e45; color:#cce0ff; padding:5px 6px; border:1px solid #333; font-size:9px; text-align:center; width:65px;">NO</th>
          <th style="background:#0a1e45; color:#cce0ff; padding:5px 6px; border:1px solid #333; font-size:9px; text-align:left; min-width:175px;">POINT PEMERIKSAAN</th>
          <th style="background:#0a1e45; color:#cce0ff; padding:5px 6px; border:1px solid #333; font-size:9px; text-align:center; width:80px;">INSPECTION TOOL</th>
          <th style="background:#0a1e45; color:#cce0ff; padding:5px 6px; border:1px solid #333; font-size:9px; text-align:center; width:115px;">STANDARD (mm)</th>
          <th style="background:#0a1e45; color:#cce0ff; padding:5px 4px; border:1px solid #333; font-size:9px; text-align:center; width:70px;">KRITIKAL POINT</th>
          <th style="background:#0a1e45; color:#cce0ff; padding:5px 4px; border:1px solid #333; font-size:9px; text-align:center; width:70px;">KRITERIA SAFETY</th>
          {
            "".join(
                f'<th class="sample-th" style="background:#122850;color:#cce0ff;padding:5px 4px;border:1px solid #333;font-size:9px;text-align:center;width:52px;">{s}</th>'
                for s in sample_order
            )
          }
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>

    {save_btn}
    {form_end}
    {js}
    </body>
    </html>
    '''
    return html

# ─────────────────────────────────────────────────────────────────────────────
# PDF EXPORT — via browser window.print() (dipanggil dari build_report_html)
# Tidak perlu fungsi Python khusus; cukup inject <script>window.print()</script>
# ke dalam HTML yang sudah dirender oleh build_report_html().
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PAGE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class ReportPage:
    def __init__(self, df_all: pd.DataFrame, current_user: str = 'Operator'):
        # DateOnly dihitung sekali di sini, bukan di dalam render method
        if not df_all.empty and 'DateOnly' not in df_all.columns:
            df_all = df_all.copy()
            df_all['DateOnly'] = pd.to_datetime(df_all['Date']).dt.date.astype(str)
        self.df_all       = df_all
        self.current_user = current_user
        self._init_state()

    def _init_state(self):
        defaults = {
            'report_page':    'landing',
            'qcl_reports':    [],
            'qcl_view':       'list',
            'qcl_current':    None,
            'qcl_saved_data': None,
            'rpt_dirty':      True,    # flag cache laporan (ikut pola diagnostic.py)
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v

    # ── Cache helpers (pola diagnostic.py) ────────────────────────────────

    def _get_reports_cached(self) -> list:
        """Ambil laporan dari DB, cache di session_state, invalidate via rpt_dirty."""
        role     = st.session_state.get('role', 'Operator')
        username = st.session_state.get('username', '')
        if st.session_state.get('rpt_dirty', True) or 'rpt_cached' not in st.session_state:
            st.session_state['rpt_cached'] = get_reports(role, username)
            st.session_state['rpt_dirty']  = False
        return st.session_state['rpt_cached']

    @staticmethod
    def _invalidate_rpt_cache():
        st.session_state['rpt_dirty'] = True

    
    def _get_html_cached(self, report: dict) -> str:
        """Cache HTML laporan di session_state — regenerasi hanya jika header berubah."""
        rid  = report['id']
        hkey = f'_rpt_html_{rid}'
        vkey = f'_rpt_html_v_{rid}'
        # versi = hash header (measurements tidak berubah di view-only flow)
        ver  = hash(json.dumps({'h': report.get('header', {}), 'so': report.get('sample_order', [])}, sort_keys=True, default=str))
        if st.session_state.get(vkey) != ver or hkey not in st.session_state:
            st.session_state[hkey] = build_report_html(report)
            st.session_state[vkey] = ver
        return st.session_state[hkey]


    def render(self):
        page = st.session_state.report_page
        if page == 'landing':
            self._render_landing()
        elif page == 'wsird':
            self._render_wsird()

    def _render_landing(self):
        st.markdown("""
        <div class="page-hdr">
          <span class="page-title">Report</span>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(
            '<p style="font-size:13px;color:#64748B;margin-bottom:24px;">' +
            'Pilih jenis laporan yang ingin dibuat.</p>',
            unsafe_allow_html=True
        )
        col1, col2, col3 = st.columns(3, gap="medium")
        with col1:
            st.markdown("""
            <div style="background:white;border:0.5px solid #E2E8F0;border-radius:12px;
                 padding:24px 20px;box-shadow:0 1px 3px rgba(0,0,0,.05);">
              <div style="font-size:28px;margin-bottom:12px;">📋</div>
              <div style="font-size:15px;font-weight:700;color:#0F172A;margin-bottom:6px;">
                WSIRD Produksi</div>
              <div style="font-size:12px;color:#64748B;line-height:1.5;margin-bottom:20px;">
                Work Station Inspection Result Data.<br/>
                Laporan harian inspeksi per shift.</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Buka →", key="open_wsird", type="primary", use_container_width=True):
                st.session_state.report_page = 'wsird'
                st.session_state.qcl_view    = 'list'
                st.rerun()
        with col2:
            st.markdown("""
            <div style="background:#F8FAFC;border:0.5px solid #E2E8F0;border-radius:12px;
                 padding:24px 20px;opacity:0.7;">
              <div style="font-size:28px;margin-bottom:12px;">📄</div>
              <div style="font-size:15px;font-weight:700;color:#94A3B8;margin-bottom:6px;">
                QIS Report</div>
              <div style="font-size:12px;color:#94A3B8;line-height:1.5;margin-bottom:20px;">
                Quality Inspection Standard.<br/>Untuk customer &amp; audit.</div>
              <div style="font-size:11px;font-weight:600;color:#CBD5E1;background:#F1F5F9;
                   padding:4px 12px;border-radius:12px;display:inline-block;">
                Coming Soon</div>
            </div>
            """, unsafe_allow_html=True)

    def _render_wsird(self):
        view = st.session_state.qcl_view
        if view == 'list':
            self._render_list()
        elif view == 'edit':
            self._render_edit()
        elif view == 'view':
            self._render_view()

    # ── LIST VIEW ──────────────────────────────────────────────────────────
    @st.fragment
    def _render_list(self):
        role     = st.session_state.get("role", "Operator")
        username = st.session_state.get("username", "")

        col_bc, col_title = st.columns([1, 5])
        with col_bc:
            if st.button("← Report", type="tertiary"):
                st.session_state.report_page = 'landing'; st.rerun()
        with col_title:
            st.markdown(
                '<div style="font-size:20px;font-weight:700;color:#0F172A;">'
                'WSIRD Produksi</div>', unsafe_allow_html=True
            )
        st.divider()

        # Laporan dari cache (bukan query DB tiap rerun)
        all_reports = self._get_reports_cached()
        if not all_reports:
            # Coba load dari session state
            all_reports = st.session_state.get('qcl_reports', [])

        # ── Generate (hanya Measurement & Admin) ─────────────────────────
        if role != "Produksi":
          with st.expander("📂 Generate Laporan", expanded=True):
            if not self.df_all.empty:
                opts = get_report_options(self.df_all)
                if not opts.empty:
                    st.caption(f"{len(opts)} kombinasi tersedia")
                    opts['label']  = opts['PartName'] + ' · ' + opts['ModelName']
                    label_to_model = dict(zip(opts['label'], opts['ModelName']))
                    label_to_part  = dict(zip(opts['label'], opts['PartName']))

                    c1, c2, c3, c4 = st.columns(4)
                    sel_label  = c1.selectbox("Part / Model", opts['label'].unique().tolist(), key="sel_model")
                    sel_model  = label_to_model[sel_label]
                    sel_part   = label_to_part[sel_label]
                    date_opts  = sorted(
                        opts[(opts['ModelName'] == sel_model) &
                             (opts['PartName']  == sel_part)]['DateOnly'].unique().tolist(),
                        reverse=True
                    )
                    # key pakai sel_label agar selectbox reset saat model berubah
                    sel_date   = c2.selectbox("Tanggal", date_opts,
                                              key=f"sel_date_{sel_label}")
                    shift_opts = sorted(
                        opts[(opts['ModelName'] == sel_model) &
                             (opts['PartName']  == sel_part) &
                             (opts['DateOnly']  == sel_date)]['Shift']
                        .unique().tolist()
                    )
                    sel_shift  = c3.selectbox("Shift", shift_opts,
                                              format_func=lambda x: f"Shift {x}",
                                              key=f"sel_shift_{sel_label}_{sel_date}")

                    # Cek apakah laporan sudah ada (untuk info note saja)
                    candidate_id  = f"{sel_model}_{sel_part}_{sel_date}_{sel_shift}".replace(' ', '_')
                    existing_meta = get_report_meta(candidate_id)
                    if existing_meta:
                        _created = existing_meta.get('createdAt', '')[:10] if existing_meta else ''
                        st.caption(f"ℹ️ Sudah ada laporan untuk kombinasi ini"
                                   + (f" (dibuat {_created})" if _created else "")
                                   + " — klik Buat Laporan untuk timpa.")

                    if st.button("＋ Buat Laporan", type="primary",
                                 use_container_width=True):
                            with st.spinner("Membuat laporan..."):
                                r = build_report_from_csv(
                                    self.df_all, sel_model, sel_date, int(sel_shift),
                                    part_name=sel_part)
                            if r:
                                with st.spinner("Menyimpan..."):
                                    rid = save_report(r, username)
                                r['id'] = rid
                                self._invalidate_rpt_cache()
                                reports  = st.session_state.qcl_reports
                                existing = next((i for i, x in enumerate(reports)
                                                 if x['id'] == rid), None)
                                if existing is not None:
                                    reports[existing] = r
                                else:
                                    reports.insert(0, r)
                                st.session_state.qcl_reports = reports
                                st.session_state.qcl_current = copy.deepcopy(r)
                                st.session_state.qcl_view    = 'edit'
                                st.rerun()
                            else:
                                st.warning("Tidak ada data untuk kombinasi yang dipilih.")
                else:
                    st.info("Tidak ada data Produksi tersedia.")
            else:
                st.info("Data CMM belum tersedia.")

        st.divider()

        # ── Load laporan dari DB ke session state ─────────────────────────
        db_reports = self._get_reports_cached()
        session_ids = {r['id'] for r in st.session_state.qcl_reports}
        for meta in db_reports:
            if meta['id'] not in session_ids:
                r_data = load_report_data(meta['id'])
                if r_data:
                    st.session_state.qcl_reports.append(r_data)

        all_reports = st.session_state.qcl_reports

        # Role Produksi hanya lihat laporan yang sudah Terkirim
        if role == "Produksi":
            all_reports = [r for r in all_reports
                           if (get_report_meta(r['id']) or {}).get('status','draft') == 'sent']

        # ── Filter + Sort + Pagination ────────────────────────────────────
        # Baris 1: Part·Model, Status, Shift
        fa1, fa2, fa3 = st.columns([3, 2, 2])
        with fa1:
            if not self.df_all.empty:
                combos = (self.df_all[["PartName","ModelName"]].dropna()
                          .drop_duplicates().sort_values(["PartName","ModelName"]))
                pm_opts = ["— Semua Part & Model —"] + [
                    f"{r.PartName} · {r.ModelName}" for _, r in combos.iterrows()
                ]
            else:
                pm_opts = ["— Semua Part & Model —"]
            flt_pm = st.selectbox("Part · Model", pm_opts, key="rpt_flt_pm") or "— Semua Part & Model —"
        with fa2:
            flt_status = st.selectbox(
                "Status", ["— Semua Status —","Draft","Terkirim"],
                key="rpt_flt_status"
            )
        with fa3:
            flt_shift = st.selectbox(
                "Shift", ["— Semua Shift —","Shift 1","Shift 2","Shift 3"],
                key="rpt_flt_shift"
            )

        # Baris 2: Tanggal, Urutkan
        fb1, fb2 = st.columns([2, 2])
        with fb1:
            _all_dates = sorted(
                {r['header'].get('tanggal','') for r in all_reports
                 if r['header'].get('tanggal','')},
                reverse=True
            )
            date_opts_flt = ["— Semua Tanggal —"] + _all_dates
            flt_date = st.selectbox("Tanggal", date_opts_flt, key="rpt_flt_date")
        with fb2:
            flt_sort = st.selectbox(
                "Urutkan",
                ["Terbaru", "Terlama", "Part A→Z", "NG Terbanyak"],
                key="rpt_flt_sort"
            )
        PER_PAGE = 25

        # Terapkan filter
        filtered = list(all_reports)
        if flt_pm != "— Semua Part & Model —":
            filtered = [r for r in filtered
                if f"{r['header'].get('partName', r['header'].get('namaPart',''))} · {r['header'].get('modelName','')}" == flt_pm]
        if flt_shift != "— Semua Shift —":
            filtered = [r for r in filtered
                if str(r['header'].get('shift','')) == flt_shift.replace('Shift ', '')]
        if flt_date != "— Semua Tanggal —":
            filtered = [r for r in filtered
                if r['header'].get('tanggal','') == flt_date]
        if flt_status != "— Semua Status —":
            s_map = {"Terkirim":"sent","Draft":"draft"}
            target = s_map.get(flt_status,"")
            def _get_status(r):
                m = get_report_meta(r['id'])
                return m.get("status","draft") if m else "draft"
            filtered = [r for r in filtered if _get_status(r) == target]

        # Terapkan sort
        def _parse_tgl(r):
            t = r['header'].get('tanggal','')
            try:
                from datetime import datetime as _dt
                return _dt.strptime(t, '%d/%m/%Y')
            except Exception:
                return _dt.min
        if flt_sort == "Terbaru":
            filtered.sort(key=_parse_tgl, reverse=True)
        elif flt_sort == "Terlama":
            filtered.sort(key=_parse_tgl, reverse=False)
        elif flt_sort == "Part A→Z":
            filtered.sort(key=lambda r: (
                r['header'].get('partName', r['header'].get('namaPart','')),
                r['header'].get('modelName','')
            ))
        elif flt_sort == "NG Terbanyak":
            filtered.sort(key=lambda r: count_oot(r), reverse=True)

        # Pagination
        total       = len(filtered)
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

        # Reset halaman kalau filter berubah
        _flt_sig = f"{flt_pm}|{flt_status}|{flt_shift}|{flt_date}|{flt_sort}"
        if st.session_state.get('_rpt_flt_sig') != _flt_sig:
            st.session_state['_rpt_flt_sig'] = _flt_sig
            st.session_state['rpt_page'] = 1

        cur_page = st.session_state.get('rpt_page', 1)
        cur_page = max(1, min(cur_page, total_pages))

        # Header: count + nav
        hc1, hc2, hc3, hc4, hc5 = st.columns([2, 1, 2, 1, 2])
        hc1.caption(f"{total} laporan · halaman {cur_page}/{total_pages}")
        if hc2.button("‹", key="rpt_prev", disabled=(cur_page <= 1)):
            st.session_state['rpt_page'] = cur_page - 1
            st.rerun()
        hc3.markdown(
            f"<div style='text-align:center;font-size:12px;padding-top:6px;color:#64748B;'>"
            f"Hal. {cur_page} / {total_pages}</div>",
            unsafe_allow_html=True
        )
        if hc4.button("›", key="rpt_next", disabled=(cur_page >= total_pages)):
            st.session_state['rpt_page'] = cur_page + 1
            st.rerun()
        hc5.empty()

        page_reports = filtered[(cur_page-1)*PER_PAGE : cur_page*PER_PAGE]

        for r in page_reports:
            ng       = count_oot(r)
            kp_ng    = count_kp_ng(r)
            filled   = count_filled(r)
            _n_total = count_total_meas(r)

            meta_db   = get_report_meta(r['id'])
            db_status = meta_db.get("status", "draft") if meta_db else "draft"
            _pname = r['header'].get('partName') or r['header'].get('namaPart', '')
            _mname = r['header'].get('modelName', '')
            nm = f"{_pname} {_mname}".strip() or r['header'].get('noPart') or r['id']

            # Badge NG/OK (inline kiri)
            if ng > 0:
                ng_badge = '<span style="background:#FEE2E2;color:#991B1B;font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;">NG</span>'
            elif filled > 0:
                ng_badge = '<span style="background:#DCFCE7;color:#166534;font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;">OK</span>'
            else:
                ng_badge = ''

            # Badge status workflow (kanan)
            if db_status == "sent":
                status_badge = '<span style="background:#DBEAFE;color:#1E40AF;font-size:10px;font-weight:600;padding:2px 10px;border-radius:10px;">📤 Terkirim</span>'
            else:
                status_badge = '<span style="background:#F1F5F9;color:#64748B;font-size:10px;font-weight:600;padding:2px 10px;border-radius:10px;">📝 Draft</span>'

            # info NG inline
            ng_info = ''
            if ng > 0:
                ng_info += f' &nbsp;·&nbsp; <span style="color:#DC2626;font-weight:600;">🔴 {ng} NG</span>'
            if kp_ng > 0:
                ng_info += f' &nbsp;·&nbsp; <span style="color:#D97706;font-weight:600;">⚠ {kp_ng} KP NG</span>'

            st.markdown(f"""
            <div style="background:white;border:1px solid #E2E8F0;border-radius:10px;
                 padding:14px 20px;margin-bottom:4px;
                 box-shadow:0 1px 3px rgba(15,23,42,.05);">
              <div style="display:flex;align-items:center;justify-content:space-between;">
                <div style="display:flex;align-items:center;gap:8px;font-size:15px;font-weight:700;color:#0F172A;">
                  {nm}
                  <span style="font-weight:500;color:#64748B;font-size:13px;">· Shift {r['header']['shift']}</span>
                  {ng_badge}
                </div>
                <div>{status_badge}</div>
              </div>
              <div style="font-size:11px;color:#64748B;margin-top:4px;">
                📅 {r['header']['tanggal']} &nbsp;·&nbsp;
                👤 {r['header'].get('namaOperator','—')} &nbsp;·&nbsp;
                📊 {filled}/{_n_total} titik{ng_info}
              </div>
            </div>
            """, unsafe_allow_html=True)

            c1, c2, c3, c4 = st.columns([1, 1, 1, 0.4])
            with c1:
                if st.button("👁 Lihat", key=f"view_{r['id']}", use_container_width=True):
                    st.session_state.qcl_current = copy.deepcopy(r)
                    st.session_state.qcl_view    = 'view'
                    st.rerun()
            with c2:
                if role != "Produksi":
                    if st.button("✏ Edit", key=f"edit_{r['id']}", use_container_width=True):
                        st.session_state.qcl_current = copy.deepcopy(r)
                        st.session_state.qcl_view    = 'edit'
                        st.rerun()
            with c3:
                if st.button("🖨 PDF", key=f"pdf_{r['id']}", use_container_width=True):
                    st.session_state.qcl_current = copy.deepcopy(r)
                    st.session_state['_print_rpt'] = r['id']
                    st.session_state.qcl_view = 'view'
                    st.rerun()
            with c4:
                if st.button("🗑", key=f"del_{r['id']}", use_container_width=True,
                             help="Hapus laporan"):
                    rid = r['id']
                    st.session_state.qcl_reports = [
                        x for x in st.session_state.qcl_reports if x['id'] != rid
                    ]
                    from local_db import delete_report as _del_rpt
                    _del_rpt(rid)
                    self._invalidate_rpt_cache()
                    st.rerun()
            st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

        # Pagination bawah
        if total_pages > 1:
            bc1, bc2, bc3, bc4, bc5 = st.columns([2, 1, 2, 1, 2])
            if bc2.button("‹ Prev", key="rpt_prev_bot", disabled=(cur_page <= 1)):
                st.session_state['rpt_page'] = cur_page - 1; st.rerun()
            bc3.markdown(
                f"<div style='text-align:center;font-size:12px;padding-top:6px;color:#64748B;'>"
                f"Hal. {cur_page} / {total_pages}</div>", unsafe_allow_html=True
            )
            if bc4.button("Next ›", key="rpt_next_bot", disabled=(cur_page >= total_pages)):
                st.session_state['rpt_page'] = cur_page + 1; st.rerun()

    # ── EDIT VIEW (header only) ────────────────────────────────────────────
    @st.fragment
    def _render_edit(self):
        r = st.session_state.qcl_current
        if not r:
            st.session_state.qcl_view = 'list'; st.rerun()

        components.html("""<script>
setTimeout(function(){
  try{
    var d=window.parent.document;
    ['[data-testid="stMainBlockContainer"]','[data-testid="stMain"]',
     '.main','section.main','.block-container'].forEach(function(s){
      var e=d.querySelector(s); if(e) e.scrollTop=0;
    });
    window.parent.scrollTo(0,0);
    d.documentElement.scrollTop=0; d.body.scrollTop=0;
  }catch(e){}
},120);
</script>""", height=0)
        # Status badge untuk indikator draft
        _meta_edit  = get_report_meta(r['id'])
        _db_status  = _meta_edit.get('status', 'draft') if _meta_edit else 'draft'
        _status_cfg = {
            'draft': ('📝 Draft',   '#F1F5F9', '#475569'),
            'sent':  ('📤 Terkirim','#DBEAFE', '#1E40AF'),
        }
        _slabel, _sbg, _sclr = _status_cfg.get(_db_status, _status_cfg['draft'])

        col_back, col_title, col_save = st.columns([1, 5, 1.5])
        with col_back:
            if st.button("← Kembali"):
                st.session_state.qcl_view = 'list'; st.rerun()
        with col_title:
            _part_lbl = (r['header'].get('partName') or r['header'].get('namaPart',''))
            _model_lbl = r['header'].get('modelName','')
            _shift_lbl = r['header'].get('shift','')
            st.markdown(
                f"**Edit** · {_part_lbl} {_model_lbl} · Shift {_shift_lbl} "
                f'&nbsp;<span style="background:{_sbg};color:{_sclr};'
                f'font-size:11px;font-weight:600;padding:2px 10px;'
                f'border-radius:10px;vertical-align:middle;">{_slabel}</span>',
                unsafe_allow_html=True
            )
        with col_save:
            if st.button("💾 Simpan", type="primary", use_container_width=True):
                # Baca _so: format "rid:json_order" — cek rid cocok dulu
                _so_raw = st.query_params.get('_so', '')
                if _so_raw and ':' in _so_raw:
                    try:
                        _so_rid, _so_json = _so_raw.split(':', 1)
                        if _so_rid == r['id'].replace('-', '_'):
                            _new_so = json.loads(_so_json)
                            if isinstance(_new_so, list) and _new_so:
                                r['sample_order'] = _new_so
                    except Exception:
                        pass
                with st.spinner("Menyimpan..."):
                    self._save_current()
                # Auto kirim ke Produksi + notif NG
                _uname = st.session_state.get("username", "")
                update_report_status(r['id'], 'sent')
                n_notif = _send_ng_notifs_from_report(r, _uname)
                # Invalidate cache
                rid = r['id']
                for pfx in ('_rpt_html_', '_rpt_html_v_'):
                    st.session_state.pop(f'{pfx}{rid}', None)
                self._invalidate_rpt_cache()
                _msg = "Tersimpan & terkirim ke Produksi ✓"
                if n_notif > 0:
                    _msg += f" · {n_notif} notifikasi NG"
                st.success(_msg)
                st.session_state.qcl_view = 'view'
                st.rerun()

        st.divider()

        h = r['header']
        # Baris 1: info part (config header)
        c1, c2, c3, c4 = st.columns(4)
        h['unitProduksi'] = c1.text_input("Unit Produksi", h.get('unitProduksi', ''))
        h['namaPart']     = c2.text_input("Nama Part",     h.get('namaPart', ''))
        h['noPart']       = c3.text_input("No. Part",      h.get('noPart', ''))
        h['line']         = c4.text_input("Line",          h.get('line', ''))
        # Baris 2: info operator
        c1, c2, c3, c4 = st.columns(4)
        h['namaOperator'] = c1.text_input("Nama Operator", h.get('namaOperator', ''))
        h['nrp']          = c2.text_input("NRP",           h.get('nrp', ''))
        h['noDies']       = c3.text_input("No. Dies",      h.get('noDies', ''))
        h['noDoc']        = c4.text_input("No. Dokumen",   h.get('noDoc', ''))
        # Baris 3: info dokumen
        c1, _ = st.columns([2, 2])
        h['tglBerlaku']   = c1.text_input("Tgl Berlaku",   h.get('tglBerlaku', ''))
        r['header'] = h

        # ── Preview laporan dengan drag-and-drop kolom sampel ───────────────────
        st.divider()
        st.caption("↔ Geser header kolom sampel langsung di tabel untuk ubah urutan, lalu klik Simpan")
        with st.spinner("Memuat laporan..."):
            _html = self._get_html_cached(r)
        _h    = max(700, 480 + len(r.get('items', ITEMS)) * 23)
        components.html(_html, height=_h, scrolling=True)

    # ── VIEW MODE ──────────────────────────────────────────────────────────
    @st.fragment
    def _render_view(self):
        r = st.session_state.qcl_current
        if not r:
            st.session_state.qcl_view = 'list'; st.rerun()

        components.html("""<script>
setTimeout(function(){
  try{
    var d=window.parent.document;
    ['[data-testid="stMainBlockContainer"]','[data-testid="stMain"]',
     '.main','section.main','.block-container'].forEach(function(s){
      var e=d.querySelector(s); if(e) e.scrollTop=0;
    });
    window.parent.scrollTo(0,0);
    d.documentElement.scrollTop=0; d.body.scrollTop=0;
  }catch(e){}
},120);
</script>""", height=0)
        col_back, col_title, col_print = st.columns([1, 5, 1.5])
        with col_back:
            if st.button("← Kembali"):
                st.session_state.qcl_view = 'list'; st.rerun()
        with col_title:
            _ng    = count_oot(r)
            _kp_ng = count_kp_ng(r)
            _parts = []
            if _ng    > 0: _parts.append(f"🔴 {_ng} NG")
            if _kp_ng > 0: _parts.append(f"⚠ {_kp_ng} KP NG")
            status = " · ".join(_parts) if _parts else "✓ Semua OK"
            st.markdown(f"**{r['header']['noPart']}** · Shift {r['header']['shift']} · {r['header']['tanggal']}  {status}")
        with col_print:
            if st.button("🖨 Print / PDF", use_container_width=True):
                with st.spinner("Menyiapkan PDF..."):
                    st.session_state['_print_rpt'] = r['id']
                st.rerun()

        n_items = len(r.get('items', ITEMS))
        html_h  = max(700, 480 + n_items * 23)
        with st.spinner("Memuat laporan..."):
            _html_v = self._get_html_cached(r)
        if st.session_state.get('_print_rpt') == r['id']:
            st.session_state.pop('_print_rpt', None)
            _html_v += '<script>setTimeout(function(){window.print();},350);</script>'
        components.html(_html_v, height=html_h, scrolling=True)

    # ── INTERNAL ───────────────────────────────────────────────────────────
    def _new_report(self):
        st.session_state.qcl_current = {
            'id': str(int(datetime.now().timestamp())),
            'createdAt': datetime.now().isoformat(),
            'submittedBy': self.current_user,
            'header': {**HDR_DEF, 'tanggal': today_str()},
            'measurements': init_meas(),
        }
        st.session_state.qcl_view = 'edit'

    def _save_current(self):
        r = st.session_state.qcl_current
        if not r:
            return
        # Persist ke local_db
        try:
            saved_id = save_report(r, self.current_user)
            if saved_id:
                r['id'] = saved_id
        except Exception:
            pass
        # Update session state
        reports = st.session_state.qcl_reports
        idx = next((i for i, x in enumerate(reports) if x['id'] == r['id']), None)
        if idx is not None:
            reports[idx] = copy.deepcopy(r)
        else:
            reports.insert(0, copy.deepcopy(r))
        st.session_state.qcl_reports = reports