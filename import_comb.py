"""
SHEET GABUNGAN "[AFF - TAP] <bulan>", tab "1-31 (all)"
================================================================================
Setiap import AFF atau TAP ikut ditambahkan ke bawah tab gabungan (kolom A:T):
  A Date  B Week  C Creator Name  D Product ID  E Product name  F Brand  G Sub Brand  H GMV  I Qty
  J Type  K Source  L Creator Check (rumus)  M:S per brand (rumus)  T cek kreator paid (rumus)
- AFF  (Source "SC"):  satu baris per baris yang masuk ke tab ALL. GMV = Est. Commission Base,
  Qty = Quantity, Date berupa teks dd/mm/yyyy (sama dengan blok SC yang sudah ada).
- TAP  (Source "TAP"): tiap baris TAP dipecah per tipe: Video (GMV = SV GMV), Live Streaming
  (GMV = LS GMV), Sharelink (GMV = Revenue Showcase + Link GMV); cuma tipe yang GMV-nya > 0.
  Urutan: semua baris Video, lalu semua Live Streaming, lalu semua Sharelink. Qty = jumlah item
  per tipe (item terjual video / LS / link, sama dengan kolom AA/AB/AC di sheet TAP).
Tanpa cek duplikat; app memberi peringatan kalau tanggal & source yang sama sudah ada.
"""
import collections
import datetime
import itertools

import import_aff as ia

COMB_ID, COMB_TAB = '1tUb-7HE6opq99115OaoHdKVy-drM-NAhsqIRH8DCaoc', '1-31 (all)'
CHUNK = 40000
KREATOR = "'LIST KREATOR'"


def _n(v):
    return ia.num(v) or 0


def aff_rows(rows, mapping):
    """rows = hasil import_aff.read_raw (sudah tanpa Lip Care) -> 11 nilai kolom A..K per baris."""
    out = []
    for r in rows:
        brand, sub = mapping[r['Product ID']]
        t = r['Time Created']
        out.append(["'" + t[:10], ia.week_of(t), "'" + str(r['Creator Username']), ia.txt(r['Product ID']),
                    ia.txt(r['Product Name']), brand, sub, _n(r['Est. Commission Base']), _n(r['Quantity']),
                    ia.CONTENT_TYPE[r['Content Type']], 'SC'])
    return out


def tap_rows(rows, mapping):
    """rows = hasil import_tap.read_raw (GMV != 0) -> 11 nilai kolom A..K, dipecah per tipe."""
    types = (('2. Video', lambda r: _n(r['Affiliate video-attributed GMV'])),
             ('1. Live Streaming', lambda r: _n(r['Creator LIVE-attributed GMV'])),
             ('3. Sharelink', lambda r: _n(r['Revenue (Showcase)']) + _n(r['Link GMV'])))
    out = []
    for typ, gmv_of in types:
        for r in rows:
            gmv = gmv_of(r)
            if gmv <= 0:
                continue
            orders, live, video, items = (_n(r[k]) for k in ('Creator-attributed orders',
                                                              'Creator LIVE-attributed orders',
                                                              'Creator video-attributed orders',
                                                              'Creator-attributed items sold'))
            per_order = items / orders if orders else 0
            qty = {'2. Video': video * per_order, '1. Live Streaming': live * per_order,
                   '3. Sharelink': items - video * per_order - live * per_order}[typ]
            brand, sub = mapping[r['Product ID']]
            name = ' '.join(str(r['Product name']).split())
            out.append([r['Date'], ia.week_of(f"{r['Date'][8:10]}/{r['Date'][5:7]}/{r['Date'][:4]}"),
                        "'" + str(r['Creator name']), ia.txt(r['Product ID']), ia.txt(name), brand, sub,
                        gmv, qty, typ, 'TAP'])
    return out


def with_formulas(vals, n):
    """11 nilai + rumus kolom L:T untuk baris sheet nomor n."""
    check = '=counta(M{0})+counta(N{0})+counta(O{0})+counta(P{0})+counta(Q{0})+counta(R{0})+counta(S{0})'.format(n)
    per_brand = [f"=iferror(vlookup(C{n},{KREATOR}!${c}:${c},1,0))" for c in 'ABCDEFG']
    return vals + [check, *per_brand, f"=iferror(vlookup(C{n},{KREATOR}!J:J,1,0))"]


def read_state(svc, sid=COMB_ID):
    """(baris terakhir terisi di kolom A, Counter (source, tanggal ISO) -> jumlah baris).
    Dibaca per 40 ribu baris: httplib2 menolak respons yang terbuka lebih dari 10 MB dengan rasio kompresi > 100,
    dan kolom A/K sheet ini sangat repetitif."""
    _, total = ia.grid_rows(svc, sid, COMB_TAB)
    base = datetime.date(1899, 12, 30)
    seen, last = collections.Counter(), 1
    for start in range(2, total + 1, CHUNK):
        end = min(start + CHUNK - 1, total)
        resp = svc.values().batchGet(spreadsheetId=sid, ranges=[f"'{COMB_TAB}'!A{start}:A{end}",
                                                                f"'{COMB_TAB}'!K{start}:K{end}"],
                                     valueRenderOption='UNFORMATTED_VALUE').execute(num_retries=3)['valueRanges']
        dates, sources = ([(x[0] if x else '') for x in vr.get('values', [])] for vr in resp)
        if dates:
            last = start + len(dates) - 1
        for d, src in itertools.zip_longest(dates, sources, fillvalue=''):
            if isinstance(d, (int, float)):
                iso = (base + datetime.timedelta(days=int(d))).isoformat()
            elif isinstance(d, str) and len(d) == 10 and d[2] == '/':
                iso = f'{d[6:]}-{d[3:5]}-{d[:2]}'
            else:
                continue
            seen[(str(src).upper(), iso)] += 1
    return last, seen


def overlap(seen, source, rows):
    """{tanggal ISO: jumlah baris yang sudah ada} untuk tanggal di rows (kolom A) dengan source itu."""
    iso = {r[0][1:] if r[0].startswith("'") else r[0] for r in rows}
    iso = {f'{d[6:]}-{d[3:5]}-{d[:2]}' if d[2:3] == '/' else d for d in iso}
    return {d: seen[(source, d)] for d in sorted(iso) if seen.get((source, d))}


def plan_rows(svc, base_rows, sid=COMB_ID):
    """-> (baris pertama, baris terakhir sekarang, nilai A..T yang akan ditulis, state tab gabungan)."""
    last_row, seen = read_state(svc, sid)
    first = last_row + 1
    return first, last_row, [with_formulas(v, first + j) for j, v in enumerate(base_rows)], seen


def write_rows(svc, out, first, sid=COMB_ID):
    if not out:
        return 0
    ia.ensure_rows(svc, sid, COMB_TAB, first + len(out) - 1)
    for s in range(0, len(out), 2000):
        chunk = out[s:s + 2000]
        svc.values().update(
            spreadsheetId=sid, range=f"'{COMB_TAB}'!A{first + s}:T{first + s + len(chunk) - 1}",
            valueInputOption='USER_ENTERED', body={'values': chunk}).execute(num_retries=3)
        print(f'Gabungan: tertulis {s + len(chunk)}/{len(out)} baris.')
    return len(out)


def explain(e):
    """Pesan HttpError Google Sheets yang menyebut penyebab dan langkah berikutnya."""
    status = getattr(getattr(e, 'resp', None), 'status', None)
    if status == 403:
        return 'tidak ada akses ke sheet gabungan. Bagikan sebagai Editor ke email service account di credentials.json.'
    if status == 404:
        return 'sheet gabungan tidak ditemukan. Cek COMB_ID di import_comb.py.'
    return str(e)


def run(svc, base, source, apply, sid=COMB_ID):
    """Jalur terminal/desktop: rencana, dan kalau apply, tulis ke sheet gabungan."""
    first, last_row, out, seen = plan_rows(svc, base, sid)
    print(f'\nSheet gabungan (tab {COMB_TAB}): {len(out)} baris Source {source} -> baris {first}-{first + len(out) - 1}'
          f' (baris terakhir sekarang {last_row})')
    if apply and out:
        write_rows(svc, out, first, sid)
