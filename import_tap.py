"""
IMPORT TAP GMV -> tab "all" di "[TAP] TT <bulan>"
================================================================================
Satu file per kali (xlsx, tab "Custom report"). Cuma baris yang Creator-attributed GMV-nya
bukan 0 yang dibawa (laporan TAP itu cross-join, hampir semua barisnya 0).
Brand + Sub Brand dicari dari List Produk lewat Product ID (sama dengan import_aff.py).
Produk dengan Sub Brand di SKIP_SUBS (Lip Care) tidak dimasukkan.
Kolom B:AC ditulis ke bawah data yang ada; kolom A (penanda manual "batas 18") tidak disentuh.
TANPA CEK DUPLIKAT: jangan upload rentang tanggal yang sudah ada (app memberi peringatan).
Kolom M, Z:AC ditulis sebagai rumus, sama dengan baris yang sudah ada di sheet.
"""
import collections
import datetime
import re
import xml.etree.ElementTree as ET
import zipfile

import openpyxl

import import_aff as ia

TARGET_ID, TARGET_TAB = '1HfwlqHLKzZ11f9LCxwhqzUfm_kGeHtqzardBLFMFrak', 'all'
SOURCE_TAB = 'Custom report'
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}$')
GMV = 'Creator-attributed GMV'
# kolom file mentah yang dipakai
NEED = ['Date', 'Campaign name', 'Creator name', 'Creator follower count', 'Product ID', 'Product name', GMV,
        'Affiliate video-attributed GMV', 'Creator LIVE-attributed GMV', 'Revenue (Showcase)', 'Link GMV',
        'Creator-attributed orders', 'Creator LIVE-attributed orders', 'Creator video-attributed orders',
        'LIVE likes', 'Video likes', 'Video views', 'LIVE views', 'LIVE streams', 'Videos',
        'Creator-attributed items sold']


NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def read_raw(path):
    """-> (baris dengan GMV != 0 sebagai dict header -> nilai, jumlah baris yang dipindai).
    xlsx dibaca langsung dari XML-nya: jauh lebih hemat RAM dan cepat daripada openpyxl untuk file 90 MB /
    500 ribu baris. Kalau susunan file tidak terduga, jatuh ke openpyxl."""
    try:
        with zipfile.ZipFile(path) as z:
            return _collect(_stream_rows(z))
    except zipfile.BadZipFile:
        raise ValueError('File ini bukan xlsx yang valid.')
    except (KeyError, ET.ParseError):
        wb = openpyxl.load_workbook(path, read_only=True)
        try:
            ws = wb[SOURCE_TAB] if SOURCE_TAB in wb.sheetnames else wb.worksheets[0]
            return _collect(ws.iter_rows(values_only=True))
        finally:
            wb.close()


def _cell(el, strings):
    t, v = el.get('t'), el.find(NS + 'v')
    if t == 'inlineStr':
        return ''.join(x.text or '' for x in el.iter(NS + 't'))
    if v is None or v.text is None:
        return None
    if t == 's':
        return strings[int(v.text)]
    if t in ('str', 'e'):
        return v.text
    if t == 'b':
        return v.text == '1'
    f = float(v.text)
    return int(f) if f.is_integer() else f


def _to_list(row):
    """{'AB12': nilai, ...} -> list nilai, posisi = nomor kolom."""
    out = []
    for ref, v in row.items():
        n = 0
        for ch in ref:
            if not ch.isalpha():
                break
            n = n * 26 + ord(ch) - 64
        out.extend([None] * (n - len(out)))
        out[n - 1] = v
    return out


def _stream_rows(z):
    """Baris sheet "Custom report" (atau sheet pertama) sebagai list nilai, dibaca bertahap tanpa memuat semuanya."""
    strings = []
    if 'xl/sharedStrings.xml' in z.namelist():
        with z.open('xl/sharedStrings.xml') as f:
            for _, el in ET.iterparse(f):
                if el.tag == NS + 'si':
                    strings.append(''.join(t.text or '' for t in el.iter(NS + 't')))
                    el.clear()
    sheets = list(ET.fromstring(z.read('xl/workbook.xml')).find(NS + 'sheets'))
    rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    sheet = next((s for s in sheets if s.get('name') == SOURCE_TAB), sheets[0])
    target = rels[sheet.get(RID)]
    row = {}
    with z.open(target[1:] if target.startswith('/') else 'xl/' + target) as f:
        for _, el in ET.iterparse(f):
            if el.tag == NS + 'c':
                row[el.get('r')] = _cell(el, strings)
                el.clear()
            elif el.tag == NS + 'row':
                yield _to_list(row)
                row = {}
                el.clear()


def _collect(rows_iter):
    rows_iter = iter(rows_iter)
    header = [str(h).strip() if h is not None else '' for h in next(rows_iter, [])]
    missing = [c for c in NEED if c not in header]
    if missing:
        raise ValueError(f'Kolom ini tidak ada di file: {", ".join(missing)}. Bukan laporan TAP GMV?')
    idx = [header.index(c) for c in NEED]
    rows, scanned = [], 0
    width = max(idx) + 1
    for r in rows_iter:
        r = list(r) + [None] * (width - len(r))
        if r[idx[0]] is None:
            continue
        scanned += 1
        row = dict(zip(NEED, (r[i] for i in idx)))
        try:
            if ia.num(row[GMV]) in ('', 0):
                continue
        except ValueError:
            raise ValueError(f'Baris {scanned + 1}: {GMV} bukan angka ({row[GMV]!r}).')
        if isinstance(row['Date'], (int, float)) and 30000 < row['Date'] < 80000:  # tanggal Excel (serial)
            row['Date'] = datetime.date(1899, 12, 30) + datetime.timedelta(days=int(row['Date']))
        if isinstance(row['Date'], (datetime.date, datetime.datetime)):
            row['Date'] = row['Date'].strftime('%Y-%m-%d')
        row['Date'] = str(row['Date']).strip()
        if not DATE_RE.match(row['Date']):
            raise ValueError(f'Baris {scanned + 1}: format Date tidak dikenal ({row["Date"]!r}), harusnya YYYY-MM-DD.')
        row['Product ID'] = str(row['Product ID']).strip()
        rows.append(row)
    return rows, scanned


def build_row(r, n, brand, sub):
    """28 nilai kolom B..AC untuk baris sheet nomor n."""
    name, campaign = (' '.join(str(r[k]).split()) for k in ('Product name', 'Campaign name'))
    return [
        r['Date'], campaign, ia.txt(r['Creator name']), ia.num(r['Creator follower count']),
        ia.txt(r['Product ID']), ia.txt(name), brand, sub,
        ia.num(r[GMV]), ia.num(r['Affiliate video-attributed GMV']), ia.num(r['Creator LIVE-attributed GMV']),
        f'=sum(N{n}:O{n})', ia.num(r['Revenue (Showcase)']), ia.num(r['Link GMV']),
        ia.num(r['Creator-attributed orders']), ia.num(r['Creator LIVE-attributed orders']),
        ia.num(r['Creator video-attributed orders']),
        ia.num(r['LIVE likes']), ia.num(r['Video likes']), ia.num(r['Video views']), ia.num(r['LIVE views']),
        ia.num(r['LIVE streams']), ia.num(r['Videos']), ia.num(r['Creator-attributed items sold']),
        f'=Y{n}/P{n}', f'=R{n}*Z{n}', f'=Q{n}*Z{n}', f'=Y{n}-sum(AA{n}:AB{n})',
    ]


def read_dates(svc, sid=TARGET_ID):
    """(baris terakhir terisi di kolom B, Counter tanggal ISO -> jumlah baris) dari tab all."""
    vals = svc.values().get(spreadsheetId=sid, range=f"'{TARGET_TAB}'!B2:B",
                            valueRenderOption='UNFORMATTED_VALUE').execute().get('values', [])
    base = datetime.date(1899, 12, 30)
    dates = collections.Counter(
        (base + datetime.timedelta(days=int(v[0]))).isoformat()
        for v in vals if v and isinstance(v[0], (int, float)))
    return 1 + len(vals), dates


def plan_rows(svc, rows, mapping, sid=TARGET_ID):
    """-> (baris pertama, baris terakhir sekarang, nilai B..AC yang akan ditulis, Counter tanggal yang sudah ada)."""
    last_row, dates = read_dates(svc, sid)
    first = last_row + 1
    out = [build_row(r, first + j, *mapping[r['Product ID']]) for j, r in enumerate(rows)]
    return first, last_row, out, dates


def write_rows(svc, out, first, sid=TARGET_ID):
    if not out:
        return 0
    ia.ensure_rows(svc, sid, TARGET_TAB, first + len(out) - 1)
    for s in range(0, len(out), 2000):
        chunk = out[s:s + 2000]
        svc.values().update(
            spreadsheetId=sid, range=f"'{TARGET_TAB}'!B{first + s}:AC{first + s + len(chunk) - 1}",
            valueInputOption='USER_ENTERED', body={'values': chunk}).execute()
        print(f'Tertulis {s + len(chunk)}/{len(out)} baris.')
    return len(out)
