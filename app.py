"""
Import Affiliate TikTok -- versi web (Streamlit). Cuma akun @warnaemasindonesia.com yang bisa masuk.
Dua menu: Raw Affiliate (import_aff.py) dan TAP GMV (import_tap.py). Kedua file itu ada satu folder di atas
saat lokal; salin ke folder ini saat deploy.

Jalankan lokal:  streamlit run aff_web/app.py   (butuh .streamlit/secrets.toml, lihat secrets.toml.example)
"""
import base64
import collections
import functools
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from googleapiclient.errors import HttpError

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import import_aff as ia  # noqa: E402
import import_tap as it  # noqa: E402

DOMAIN = 'warnaemasindonesia.com'
HEAD = ['Date Created', 'Date', 'Week', 'Category', 'Product ID', 'Product Name', 'Brand', 'Sub Brand', 'Price',
        'Payment Amount', 'Est Commission Base', 'Quantity', 'Price*Qty', 'Order Status', 'Creator Username',
        'Content Type', 'Content ID', 'Standard commission rate']
HEAD_TAP = ['Date', 'Campaign name', 'Creator name', 'Followers', 'Product ID', 'Product name', 'Brand', 'Sub Brand',
            'All GMV', 'SV GMV', 'LS GMV', 'SL GMV', 'Revenue (Showcase)', 'Link GMV', 'Orders', 'LIVE orders',
            'Video orders', 'LIVE likes', 'Video likes', 'Video views', 'LIVE views', 'LIVE streams', 'Videos',
            'Items sold', 'Avg Item Sold', 'Item Sold Video', 'Item Sold LS', 'Link items sold']


def allowed(email, verified, extra=()):
    """Cek di server: email Google terverifikasi, dan domainnya persis domain perusahaan
    atau emailnya ada di daftar khusus (allowed_emails di secrets)."""
    if not (verified and isinstance(email, str)):
        return False
    email = email.lower()
    return email.rsplit('@', 1)[-1] == DOMAIN or email in {str(e).strip().lower() for e in extra}


def sa_info():
    return dict(st.secrets['gcp_service_account'])


@st.cache_data(show_spinner='Membaca file...')
def parse(name, data):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / Path(name).name
        p.write_bytes(data)
        try:
            return ia.read_raw(p)
        except SystemExit as e:  # read_raw memakai sys.exit('ERROR: ...')
            raise ValueError(str(e.code))


@st.cache_data(ttl=300, show_spinner='Membaca List Produk...')
def brand_data():
    rows, _ = ia.read_brand_sheet(ia.get_service(False, sa_info()))
    return rows, ia.sheet_mapping(rows), {r['pid'] for r in rows}


@st.cache_data(ttl=120, show_spinner='Membaca tab ALL...')
def plan(sid, name, size, filled, _rows, _mapping):
    """sid/name/size/filled jadi kunci cache; _rows/_mapping tidak di-hash."""
    return ia.plan_rows(ia.get_service(False, sa_info()), _rows, _mapping, sid=sid)


@st.cache_data(show_spinner='Membaca file TAP (file besar, bisa 2-3 menit)...')
def parse_tap(name, data):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / Path(name).name
        p.write_bytes(data)
        return it.read_raw(p)


@st.cache_data(ttl=120, show_spinner='Membaca tab all...')
def plan_tap(sid, name, size, filled, _rows, _mapping):
    return it.plan_rows(ia.get_service(False, sa_info()), _rows, _mapping, sid)


# Tampilan hitam-putih ala dashboard Cussons: latar abu muda, kartu putih, sidebar hitam, tombol emas.
CSS = """<style>
[data-testid="stHeader"] {background:transparent}
.block-container {padding-top:2rem; max-width:1200px}
[data-testid="stSidebar"] {background:#000; border-right:1px solid rgba(255,255,255,.18)}
[data-testid="stSidebar"] * {color:#fff}
[data-testid="stSidebar"] button {background:none; border:1px solid rgba(255,255,255,.18); border-radius:6px}
[data-testid="stSidebar"] button:hover {border-color:#fff}
.side-logo {height:32px; display:block}
.side-brand {margin:10px 0 24px; color:#c6cbc7; font-size:13px}
[data-testid="stSidebarUserContent"] {display:flex; flex-direction:column; min-height:calc(100vh - 2rem)}
[data-testid="stSidebarUserContent"] > div {flex:1; display:flex; flex-direction:column}
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {flex:1}
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stRadio"]) {width:100% !important}
[data-testid="stSidebar"] [data-testid="stRadio"] {width:100%}
[data-testid="stSidebar"] [data-testid="stLayoutWrapper"]:has(> .st-key-side_foot) {margin-top:auto}
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] {gap:2px; align-items:stretch}
[data-testid="stSidebar"] [data-testid="stRadio"] label {width:100%; padding:10px 12px; border-radius:4px; font-weight:500; cursor:pointer}
[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child {display:none}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {background:rgba(255,255,255,.12)}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {background:#fff}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) * {color:#000}
.st-key-side_foot {gap:12px; padding-top:16px; border-top:1px solid rgba(255,255,255,.18)}
.user {display:flex; gap:10px; align-items:center; min-width:0; margin:4px 0 12px}
.avatar {width:32px; height:32px; border-radius:50%; background:#fff; display:grid; place-items:center; font-weight:700; flex:none}
[data-testid="stSidebar"] .avatar {color:#000}
.me {font-size:13px; color:#c6cbc7; overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.login-logo {height:44px; display:block; margin-bottom:18px}
.hero {background:#000; color:#fff; border-radius:12px; padding:26px 30px; margin-bottom:20px}
.hero h1 {color:#fff; font-size:28px; margin:0; padding:0}
.hero p {color:#c6cbc7; margin:6px 0 0}
[data-testid="stMetric"] {background:#fff; border-radius:10px; padding:16px 18px;
  border:1px solid #e4e4e7}
[data-testid="stMetricLabel"] * {color:#6b6b6b}
[data-testid="stBaseButton-primary"], button[kind="primary"] {background:#ffd700; border:0; border-radius:6px; font-weight:700}
[data-testid="stBaseButton-primary"] *, button[kind="primary"] * {color:#000}
[data-testid="stBaseButton-primary"]:hover, button[kind="primary"]:hover {filter:brightness(.95)}
[data-testid="stAlert"] {background:#fff; border:1px solid #000; border-radius:8px}
[data-testid="stAlert"] * {color:#000}
[data-testid="stFileUploader"] section {background:#fff; border:1px dashed #000; border-radius:8px}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {border:1px solid #e4e4e7; border-radius:8px}
h2, h3 {color:#000}
</style>"""


@functools.cache
def logo_uri():
    return 'data:image/png;base64,' + base64.b64encode((HERE / 'logo-wei.png').read_bytes()).decode()


def hero(sub, title='Import Affiliate TikTok', logo=False):
    img = f'<img class="login-logo" src="{logo_uri()}" alt="WEI">' if logo else ''
    st.markdown(f'<div class="hero">{img}<h1>{title}</h1><p>{sub}</p></div>', unsafe_allow_html=True)


def sidebar(email):
    """Sidebar gaya dashboard Cussons: logo, menu kotak, lalu akun di bawah. Mengembalikan menu yang dipilih."""
    with st.sidebar:
        st.markdown(f'<img class="side-logo" src="{logo_uri()}" alt="WEI"><div class="side-brand">Import TikTok</div>',
                    unsafe_allow_html=True)
        page = st.radio('Menu', ['Raw Affiliate', 'TAP GMV'], label_visibility='collapsed')
        with st.container(key='side_foot'):
            if st.button('Muat ulang data brand', width='stretch'):
                brand_data.clear()
                plan.clear()
                plan_tap.clear()
            st.markdown(f'<div class="user"><div class="avatar">{email[:1].upper()}</div>'
                        f'<div class="me">{email}</div></div>', unsafe_allow_html=True)
            st.button('Keluar', on_click=st.logout, width='stretch')
    return page


def explain(e, doing):
    """Pesan error Google Sheets yang menyebut penyebab dan langkah berikutnya."""
    if isinstance(e, SystemExit):  # grid_rows/read_raw memakai sys.exit('ERROR: ...')
        return str(e.code).removeprefix('ERROR: ')
    status = getattr(e.resp, 'status', None)
    if status == 403:
        return (f'Gagal {doing}: tidak ada akses ke sheet. Bagikan sheet sebagai Editor ke '
                f'{sa_info()["client_email"]}, lalu coba lagi.')
    if status == 404:
        return f'Gagal {doing}: sheet tidak ditemukan. Cek lagi link Google Sheet tujuan.'
    return f'Gagal {doing}: {e}'


def n(x):
    return f'{x:,}'.replace(',', '.')


def rp(x):
    return 'Rp ' + f'{x:,.0f}'.replace(',', '.')


def fill_brands(key, names, count):
    """Tabel isian untuk Product ID yang belum punya brand -> (mapping, ID baru, isian), atau None kalau belum lengkap."""
    sheet_rows, mapping, sheet_pids = brand_data()
    mapping = dict(mapping)
    unknown = [p for p in names if p not in mapping]
    new_ids, filled = [], ()
    if unknown:
        brands = sorted({r['brand'] for r in sheet_rows if r['brand'] and r['brand'] != ia.UNKNOWN})
        st.warning(f'{len(unknown)} Product ID belum punya brand. Isi Brand dan Sub Brand di tabel ini '
                   '(Product Name boleh dibetulkan).')
        df = pd.DataFrame({'Product ID': unknown, 'Product Name': [names[p] for p in unknown],
                           'Brand': None, 'Sub Brand': None, 'Jumlah Baris': [count[p] for p in unknown]})
        edited = st.data_editor(
            df, hide_index=True, width='stretch', key=f'fill_{key}',
            disabled=['Product ID', 'Jumlah Baris'],
            column_config={'Brand': st.column_config.SelectboxColumn(options=brands),
                           'Sub Brand': st.column_config.TextColumn(help='Contoh: Gluta Hya, Hair Shampoo')})
        blank = edited['Brand'].fillna('').str.strip().eq('') | edited['Sub Brand'].fillna('').str.strip().eq('')
        if blank.any():
            st.info(f'Masih {int(blank.sum())} baris yang belum lengkap.')
            return None
        for _, r in edited.iterrows():
            p, b, s = r['Product ID'], r['Brand'].strip(), r['Sub Brand'].strip()
            mapping[p] = [b, s]
            if p not in sheet_pids:
                new_ids.append((p, (r['Product Name'] or names[p]).strip(), b, s))
        filled = tuple((p, *mapping[p]) for p in unknown)
        stale = [p for p in unknown if p in sheet_pids]
        if stale:
            st.caption(f'{len(stale)} ID ada di List Produk sebagai "{ia.UNKNOWN}" -- dipakai untuk import ini, '
                       'barisnya di List Produk tidak diubah (ubah manual).')

    return mapping, new_ids, filled


def flow(sid, name, data, email):
    try:
        rows = parse(name, data)
    except ValueError as e:
        st.error(str(e))
        return
    names, count = {}, collections.Counter()
    for r in rows:
        names.setdefault(r['Product ID'], r['Product Name'])
        count[r['Product ID']] += 1
    st.success(f'{n(len(rows))} baris terbaca, {len(names)} Product ID. Semua baris dibawa (tanpa filter).')

    res = fill_brands(f'{name}_{len(data)}', names, count)
    if res is None:
        return
    mapping, new_ids, filled = res

    total = len(rows)
    rows, skipped = ia.drop_skipped(rows, mapping)
    try:
        new_idx, first, last_row, out = plan(sid, name, len(data), filled, rows, mapping)
    except (HttpError, SystemExit) as e:
        st.error(explain(e, 'membaca Google Sheets'))
        return

    key = (sid, name, len(data))
    if st.session_state.get('done', (None, ''))[0] == key:
        st.success(st.session_state['done'][1])

    last = first + len(out) - 1
    gmv = sum(float(ia.num(rows[i]['Payment Amount']) or 0) for i in new_idx)
    comm = sum(float(ia.num(rows[i]['Est. Commission Base']) or 0) for i in new_idx)
    by_brand = collections.Counter(mapping[rows[i]['Product ID']][0] for i in new_idx)
    pids = {rows[i]['Product ID'] for i in new_idx}

    st.subheader('Ringkasan')
    if out:
        st.info(f'Akan ditambahkan ke tab **ALL** baris **{n(first)} - {n(last)}** ({n(len(out))} baris).')
    else:
        st.info('Tidak ada baris baru untuk ditambahkan ke tab ALL.')
    c = st.columns(4)
    c[0].metric('Baris baru', f'{n(len(out))}')
    c[1].metric('Product ID', f'{n(len(pids))}')
    c[2].metric('GMV (Payment Amount)', rp(gmv))
    c[3].metric('Est. Commission Base', rp(comm))
    c = st.columns(2)
    c[0].metric(f'Dilewati ({", ".join(sorted(ia.SKIP_SUBS)).title()})', f'{n(len(skipped))}')
    c[1].metric('ID baru ke List Produk', len(new_ids))

    log = [f'{name}: {n(total)} baris, {len(names)} Product ID, tanpa filter.']
    if skipped:
        log.append(f'Dilewati (Sub Brand {sorted(ia.SKIP_SUBS)}): {n(len(skipped))} baris dari '
                   f'{len({r["Product ID"] for r in skipped})} produk, tidak dimasukkan ke ALL.')
    log += [f'Baris baru: {n(len(out))} -> baris {first}-{last} di ALL (baris terakhir sekarang {last_row})',
            f'Per brand: {dict(by_brand)}',
            f'ID baru untuk List Produk: {len(new_ids)}']
    log += [f'  {p} | {n[:60]} | {b} | {s}' for p, n, b, s in new_ids]
    st.code(chr(10).join(log), language=None)

    if by_brand:
        st.dataframe(pd.DataFrame(by_brand.items(), columns=['Brand', 'Baris baru']), hide_index=True)
    if out:
        with st.expander('Contoh 15 baris pertama (kolom A-R)'):
            st.dataframe(pd.DataFrame([[str(v).lstrip("'") for v in r[:18]] for r in out[:15]], columns=HEAD),
                         hide_index=True)
    if new_ids:
        st.dataframe(pd.DataFrame(new_ids, columns=['Product ID', 'Product Name', 'Brand', 'Sub Brand']),
                     hide_index=True)

    if st.button('Jalankan Import', type='primary', disabled=not (out or new_ids)):
        try:
            with st.spinner('Menulis ke Google Sheets...'):
                svc = ia.get_service(True, sa_info())
                # hitung ulang tepat sebelum menulis, supaya aman kalau ada yang menulis di antaranya
                _, first, _, out = ia.plan_rows(svc, rows, mapping, sid=sid)
                n_ids = ia.write_new_ids(svc, new_ids)
                n_rows = ia.write_rows(svc, out, first, sid)
            print(f'[APPLY] {email} | {name} | {n_rows} baris di {first}, {n_ids} ID baru')
            st.session_state['done'] = (key, f'Selesai: {n(n_rows)} baris ditulis mulai baris {first}, '
                                              f'{n_ids} ID baru ke List Produk.')
            plan.clear()
            brand_data.clear()
            st.rerun()
        except (HttpError, SystemExit) as e:
            st.error(explain(e, 'menulis ke Google Sheets'))


def flow_tap(sid, name, data, email):
    try:
        rows, scanned = parse_tap(name, data)
    except ValueError as e:
        st.error(str(e))
        return
    if not rows:
        st.error('Tidak ada baris dengan GMV selain 0 di file ini.')
        return
    names, count = {}, collections.Counter()
    for r in rows:
        names.setdefault(r['Product ID'], r['Product name'])
        count[r['Product ID']] += 1
    st.success(f'{n(scanned)} baris dipindai, {n(len(rows))} baris dengan GMV selain 0, {len(names)} Product ID.')

    res = fill_brands(f'tap_{name}_{len(data)}', names, count)
    if res is None:
        return
    mapping, new_ids, filled = res

    total = len(rows)
    rows, skipped = ia.drop_skipped(rows, mapping)
    try:
        first, last_row, out, dates = plan_tap(sid, name, len(data), filled, rows, mapping)
    except (HttpError, SystemExit) as e:
        st.error(explain(e, 'membaca Google Sheets'))
        return

    key = ('tap', sid, name, len(data))
    if st.session_state.get('done', (None, ''))[0] == key:
        st.success(st.session_state['done'][1])

    last = first + len(out) - 1
    in_file = collections.Counter(r['Date'] for r in rows)
    overlap = {d: dates[d] for d in in_file if dates.get(d)}
    if overlap:
        st.warning(f'Tab **{it.TARGET_TAB}** sudah berisi {n(sum(overlap.values()))} baris untuk '
                   f'{len(overlap)} tanggal yang juga ada di file ini ({min(overlap)} s/d {max(overlap)}). '
                   'Tidak ada cek duplikat, jadi kalau dilanjut datanya dobel.')
    gmv = {k: sum(float(ia.num(r[c]) or 0) for r in rows) for k, c in
           (('All', it.GMV), ('SV', 'Affiliate video-attributed GMV'), ('LS', 'Creator LIVE-attributed GMV'))}
    by_brand = collections.defaultdict(lambda: [0, 0.0])
    for r in rows:
        b = by_brand[mapping[r['Product ID']][0]]
        b[0] += 1
        b[1] += float(ia.num(r[it.GMV]) or 0)

    st.subheader('Ringkasan')
    if out:
        st.info(f'Akan ditambahkan ke tab **{it.TARGET_TAB}** baris **{n(first)} - {n(last)}** ({n(len(out))} baris).')
    else:
        st.info(f'Tidak ada baris untuk ditambahkan ke tab {it.TARGET_TAB}.')
    c = st.columns(4)
    c[0].metric('Baris', n(len(out)))
    c[1].metric('Product ID', n(len({r['Product ID'] for r in rows})))
    c[2].metric('Tanggal', f'{min(in_file)} s/d {max(in_file)}' if in_file else '-')
    c[3].metric('All GMV', rp(gmv['All']))
    c = st.columns(4)
    c[0].metric('SV GMV', rp(gmv['SV']))
    c[1].metric('LS GMV', rp(gmv['LS']))
    c[2].metric(f'Dilewati ({", ".join(sorted(ia.SKIP_SUBS)).title()})', n(len(skipped)))
    c[3].metric('ID baru ke List Produk', len(new_ids))

    log = [f'{name}: {n(scanned)} baris dipindai, {n(total)} baris GMV selain 0, {len(names)} Product ID.']
    if skipped:
        log.append(f'Dilewati (Sub Brand {sorted(ia.SKIP_SUBS)}): {n(len(skipped))} baris dari '
                   f'{len({r["Product ID"] for r in skipped})} produk, tidak dimasukkan.')
    log += [f'Baris: {n(len(out))} -> baris {first}-{last} di {it.TARGET_TAB} (baris terakhir sekarang {last_row})',
            f'Tanggal di file: {", ".join(f"{d} ({n(c)})" for d, c in sorted(in_file.items()))}',
            f'ID baru untuk List Produk: {len(new_ids)}']
    log += [f'  {p} | {nm[:60]} | {b} | {sb}' for p, nm, b, sb in new_ids]
    st.code(chr(10).join(log), language=None)

    if by_brand:
        st.dataframe(pd.DataFrame([(k, v[0], rp(v[1])) for k, v in sorted(by_brand.items())],
                                  columns=['Brand', 'Baris', 'All GMV']), hide_index=True)
    if out:
        with st.expander('Contoh 15 baris pertama (kolom B-AC)'):
            st.dataframe(pd.DataFrame([[str(v).lstrip("'") for v in r] for r in out[:15]], columns=HEAD_TAP),
                         hide_index=True)
    if new_ids:
        st.dataframe(pd.DataFrame(new_ids, columns=['Product ID', 'Product Name', 'Brand', 'Sub Brand']),
                     hide_index=True)

    if st.button('Jalankan Import', type='primary', disabled=not (out or new_ids), key='run_tap'):
        try:
            with st.spinner('Menulis ke Google Sheets...'):
                svc = ia.get_service(True, sa_info())
                first, _, out, _ = it.plan_rows(svc, rows, mapping, sid)  # hitung ulang tepat sebelum menulis
                n_ids = ia.write_new_ids(svc, new_ids)
                n_rows = it.write_rows(svc, out, first, sid)
            print(f'[APPLY TAP] {email} | {name} | {n_rows} baris di {first}, {n_ids} ID baru')
            st.session_state['done'] = (key, f'Selesai: {n(n_rows)} baris ditulis mulai baris {first}, '
                                              f'{n_ids} ID baru ke List Produk.')
            plan_tap.clear()
            brand_data.clear()
            st.rerun()
        except (HttpError, SystemExit) as e:
            st.error(explain(e, 'menulis ke Google Sheets'))


def sheet_link(default_id, tab, key):
    link = st.text_input(f'Link Google Sheet tujuan (data masuk ke tab {tab})', key=key,
                         value=f'https://docs.google.com/spreadsheets/d/{default_id}/edit',
                         help='Sheet harus sudah dibagikan (Editor) ke service account.')
    try:
        return ia.sheet_id_from(link)
    except ValueError as e:
        st.error(str(e))
        st.stop()


def main():
    st.set_page_config(page_title='Import Affiliate TikTok', layout='wide')
    st.markdown(CSS, unsafe_allow_html=True)
    if not st.user.is_logged_in:
        _, mid, _ = st.columns([1, 1.4, 1])
        with mid:
            hero(f'Masuk dengan akun Google perusahaan (@{DOMAIN}).', logo=True)
            st.button('Login dengan Google', on_click=st.login, type='primary', width='stretch')
        st.stop()
    email = st.user.get('email')
    if not allowed(email, st.user.get('email_verified'), st.secrets.get('allowed_emails', [])):
        st.error(f'Akun {email} tidak punya akses. Pakai akun @{DOMAIN}.')
        st.button('Keluar', on_click=st.logout)
        st.stop()

    page = sidebar(email)
    if page == 'TAP GMV':
        hero('Upload laporan TAP GMV (xlsx), isi brand yang belum ada, cek ringkasan, lalu Jalankan Import. '
             'Hanya baris dengan GMV selain 0 yang dibawa.', 'Import TAP GMV')
        sid = sheet_link(it.TARGET_ID, it.TARGET_TAB, 'link_tap')
        up = st.file_uploader('File TAP GMV (Excel)', type=['xlsx', 'xlsm'], key='up_tap')
        if up:
            flow_tap(sid, up.name, up.getvalue(), email)
        return
    hero('Satu file per kali: upload file, isi brand yang belum ada, cek ringkasan, lalu Jalankan Import.')
    sid = sheet_link(ia.TARGET_ID, ia.TARGET_TAB, 'link_aff')
    up = st.file_uploader('File raw AFF (CSV / Excel)', type=['csv', 'xlsx', 'xlsm'], key='up_aff')
    if up:
        flow(sid, up.name, up.getvalue(), email)


if __name__ == '__main__':
    main()
