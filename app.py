"""
Import Affiliate TikTok -- versi web (Streamlit). Cuma akun @warnaemasindonesia.com yang bisa masuk.
Logika import ada di import_aff.py (satu folder di atas saat lokal; salin ke folder ini saat deploy).

Jalankan lokal:  streamlit run aff_web/app.py   (butuh .streamlit/secrets.toml, lihat secrets.toml.example)
"""
import collections
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from googleapiclient.errors import HttpError

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import import_aff as ia  # noqa: E402

DOMAIN = 'warnaemasindonesia.com'
HEAD = ['Date Created', 'Date', 'Week', 'Category', 'Product ID', 'Product Name', 'Brand', 'Sub Brand', 'Price',
        'Payment Amount', 'Est Commission Base', 'Quantity', 'Price*Qty', 'Order Status', 'Creator Username',
        'Content Type', 'Content ID', 'Standard commission rate']


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
def plan(name, size, filled, _rows, _mapping):
    """name/size/filled jadi kunci cache; _rows/_mapping tidak di-hash."""
    return ia.plan_rows(ia.get_service(False, sa_info()), _rows, _mapping)


# Tampilan hitam-putih ala dashboard Cussons: latar abu muda, kartu putih, sidebar hitam, tombol emas.
CSS = """<style>
.stApp, .stApp * {font-family:"Helvetica Neue",Helvetica,Arial,sans-serif}
[data-testid="stHeader"] {background:transparent}
.block-container {padding-top:2rem; max-width:1200px}
[data-testid="stSidebar"] {background:#000}
[data-testid="stSidebar"] * {color:#fff}
[data-testid="stSidebar"] button {background:none; border:1px solid rgba(255,255,255,.18); border-radius:6px}
[data-testid="stSidebar"] button:hover {border-color:#fff}
.hero {background:#000; color:#fff; border-radius:12px; padding:26px 30px; margin-bottom:20px}
.hero h1 {color:#fff; font-size:28px; margin:0; padding:0}
.hero p {color:#c6cbc7; margin:6px 0 0}
.hero .brand {color:#ffd700; font-weight:700; letter-spacing:.04em; font-size:13px; margin-bottom:8px}
[data-testid="stMetric"] {background:#fff; border-radius:10px; padding:16px 18px;
  box-shadow:0 1px 2px rgba(16,16,16,.05), 0 8px 24px rgba(16,16,16,.06)}
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


def hero(sub):
    st.markdown(f'<div class="hero"><div class="brand">⚡ AUTOMASI</div><h1>Import Affiliate TikTok</h1>'
                f'<p>{sub}</p></div>', unsafe_allow_html=True)


def n(x):
    return f'{x:,}'.replace(',', '.')


def rp(x):
    return 'Rp ' + f'{x:,.0f}'.replace(',', '.')


def flow(name, data, email):
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
            df, hide_index=True, use_container_width=True, key=f'fill_{name}_{len(data)}',
            disabled=['Product ID', 'Jumlah Baris'],
            column_config={'Brand': st.column_config.SelectboxColumn(options=brands),
                           'Sub Brand': st.column_config.TextColumn(help='Contoh: Gluta Hya, Hair Shampoo')})
        blank = edited['Brand'].fillna('').str.strip().eq('') | edited['Sub Brand'].fillna('').str.strip().eq('')
        if blank.any():
            st.info(f'Masih {int(blank.sum())} baris yang belum lengkap.')
            return
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

    total = len(rows)
    rows, skipped = ia.drop_skipped(rows, mapping)
    try:
        new_idx, first, last_row, out = plan(name, len(data), filled, rows, mapping)
    except HttpError as e:
        st.error(f'Gagal membaca Google Sheets: {e}')
        return

    key = (name, len(data))
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

    if st.button('▶   Jalankan Import', type='primary', disabled=not (out or new_ids)):
        try:
            with st.spinner('Menulis ke Google Sheets...'):
                svc = ia.get_service(True, sa_info())
                # hitung ulang tepat sebelum menulis, supaya aman kalau ada yang menulis di antaranya
                _, first, _, out = ia.plan_rows(svc, rows, mapping)
                n_ids = ia.write_new_ids(svc, new_ids)
                n_rows = ia.write_rows(svc, out, first)
            print(f'[APPLY] {email} | {name} | {n_rows} baris di {first}, {n_ids} ID baru')
            st.session_state['done'] = (key, f'Selesai: {n(n_rows)} baris ditulis mulai baris {first}, '
                                              f'{n_ids} ID baru ke List Produk.')
            plan.clear()
            brand_data.clear()
            st.rerun()
        except HttpError as e:
            st.error(f'Gagal menulis ke Google Sheets: {e}')


def main():
    st.set_page_config(page_title='Import Affiliate TikTok', layout='wide')
    st.markdown(CSS, unsafe_allow_html=True)
    if not st.user.is_logged_in:
        _, mid, _ = st.columns([1, 1.4, 1])
        with mid:
            hero(f'Masuk dengan akun Google perusahaan (@{DOMAIN}).')
            st.button('Login dengan Google', on_click=st.login, type='primary', use_container_width=True)
        st.stop()
    email = st.user.get('email')
    if not allowed(email, st.user.get('email_verified'), st.secrets.get('allowed_emails', [])):
        st.error(f'Akun {email} tidak punya akses. Pakai akun @{DOMAIN}.')
        st.button('Keluar', on_click=st.logout)
        st.stop()

    st.sidebar.markdown('**⚡ Automasi**  '+chr(10)+'Affiliate TikTok')
    st.sidebar.write(email)
    st.sidebar.button('Keluar', on_click=st.logout)
    if st.sidebar.button('Muat ulang data brand'):
        brand_data.clear()
        plan.clear()
    hero('Satu file per kali: upload file, isi brand yang belum ada, cek ringkasan, lalu Jalankan Import.')
    up = st.file_uploader('File raw AFF (CSV / Excel)', type=['csv', 'xlsx', 'xlsm'])
    if up:
        flow(up.name, up.getvalue(), email)


if __name__ == '__main__':
    main()
