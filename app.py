"""
Import Affiliate TikTok -- versi web (Streamlit). Cuma akun @warnaemasindonesia.com yang bisa masuk.
Dua menu: Raw Affiliate (import_aff.py) dan TAP GMV (import_tap.py); keduanya juga mengisi sheet gabungan (import_comb.py). Kedua file itu ada satu folder di atas
saat lokal; salin ke folder ini saat deploy.

Jalankan lokal:  streamlit run aff_web/app.py   (butuh .streamlit/secrets.toml, lihat secrets.toml.example)
"""
import base64
import collections
import contextlib
import functools
import io
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import streamlit as st
from googleapiclient.errors import HttpError

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import import_aff as ia  # noqa: E402
import import_comb as ic  # noqa: E402
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


@st.cache_data(max_entries=2, show_spinner='Membaca file...')
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


@st.cache_data(max_entries=2, ttl=120, show_spinner='Membaca tab ALL...')
def plan(sid, name, size, filled, _rows, _mapping):
    """sid/name/size/filled jadi kunci cache; _rows/_mapping tidak di-hash."""
    return ia.plan_rows(ia.get_service(False, sa_info()), _rows, _mapping, sid=sid)


@st.cache_data(max_entries=2, show_spinner='Membaca file TAP (file besar, bisa 2-3 menit)...')
def parse_tap(name, data):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / Path(name).name
        p.write_bytes(data)
        return it.read_raw(p)


@st.cache_data(max_entries=2, ttl=120, show_spinner='Membaca tab all...')
def plan_tap(sid, name, size, filled, _rows, _mapping):
    return it.plan_rows(ia.get_service(False, sa_info()), _rows, _mapping, sid)


@st.cache_data(max_entries=2, ttl=120, show_spinner='Membaca sheet gabungan...')
def plan_comb(csid, ckey, _base):
    return ic.plan_rows(ia.get_service(False, sa_info()), _base, csid)


# Tampilan sama dengan app import Cussons/NPURE/Blood (Streamlit_Import): latar abu, kartu putih berbayang,
# sidebar hitam, tombol aksi emas, layar masuk berkartu.
CSS = """<style>
:root{--bg:#f4f4f5;--panel:#fff;--ink:#000;--ink2:#3d3d3d;--muted:#6b6b6b;--line:#e4e4e7;--gold:#ffd700;
  --shadow:0 1px 2px rgba(16,16,16,.05),0 8px 24px rgba(16,16,16,.06)}
html,body,[data-testid="stApp"]{font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;font-variant-numeric:tabular-nums}
[data-testid="stApp"],[data-testid="stAppViewContainer"]{background:var(--bg)}
[data-testid="stHeader"]{background:transparent}
[data-testid="stToolbar"],[data-testid="stDecoration"],#MainMenu,footer{display:none}
.block-container{max-width:1280px;padding:28px 32px 64px}

/* sidebar */
section[data-testid="stSidebar"]{background:#000;width:250px !important;min-width:250px !important;border-right:1px solid rgba(255,255,255,.18)}
section[data-testid="stSidebar"] *{color:#fff}
section[data-testid="stSidebar"] .side-brand{color:#c6cbc7;font-size:13px;margin:10px 0 12px}
section[data-testid="stSidebar"] .side-label{color:#c6cbc7;font-size:12px;letter-spacing:.08em;text-transform:uppercase;margin:20px 0 6px}
section[data-testid="stSidebar"] .stButton button{background:transparent;border:1px solid transparent;border-radius:4px;
  justify-content:flex-start;padding:10px 12px;min-height:44px;font-weight:500;text-align:left}
section[data-testid="stSidebar"] .stButton button > div,section[data-testid="stSidebar"] .stButton button p{width:100%;justify-content:flex-start;text-align:left}
section[data-testid="stSidebar"] .stButton button:hover{background:rgba(255,255,255,.12)}
section[data-testid="stSidebar"] .stButton button[data-testid="stBaseButton-primary"]{background:#fff;border-color:#fff}
section[data-testid="stSidebar"] .stButton button[data-testid="stBaseButton-primary"] *{color:#000}
section[data-testid="stSidebar"] .st-key-reload button,section[data-testid="stSidebar"] .st-key-logout button{
  border:1px solid rgba(255,255,255,.18);border-radius:6px;font-size:13px}
.user{display:flex;gap:10px;align-items:center;min-width:0;padding-top:16px;border-top:1px solid rgba(255,255,255,.18);margin-top:24px}
.avatar{width:32px;height:32px;border-radius:50%;background:#fff;color:#000 !important;display:grid;place-items:center;font-weight:700;flex:none;overflow:hidden}
.avatar img{width:100%;height:100%;object-fit:cover}
.uname{font-weight:700;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.umail{color:#c6cbc7 !important;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* judul halaman */
h1.ptitle{font-size:32px;line-height:1.1;margin:0 0 6px;letter-spacing:-.01em;padding:0}
.psub{margin:0 0 24px;color:var(--muted);font-size:16px}

/* tombol utama = emas (hanya tombol aksi) */
.stMain .stButton button[data-testid="stBaseButton-primary"]{background:var(--gold);color:#000;border:0;border-radius:6px;
  font-weight:700;min-height:44px}
.stMain .stButton button[data-testid="stBaseButton-primary"] *{color:#000}
.stMain .stButton button[data-testid="stBaseButton-primary"]:hover{filter:brightness(.95)}
.stMain .stButton button[data-testid="stBaseButton-primary"]:disabled{opacity:.5}

/* kartu isi */
.st-key-form,.st-key-summary{background:var(--panel);border-radius:10px;padding:22px 24px;box-shadow:var(--shadow)}
.st-key-summary{margin-top:24px}
.banner{display:flex;gap:10px;align-items:flex-start;border:1px solid #000;background:var(--panel);border-radius:8px;padding:12px 14px;margin:12px 0}
.banner.bad{border-color:#d03b3b;background:#fbe9e9}

/* ringkasan: metrik, tabel, uploader */
[data-testid="stMetric"]{background:var(--bg);border-radius:10px;padding:16px 18px}
[data-testid="stMetricLabel"] *{color:var(--muted)}
[data-testid="stFileUploader"] section{background:#fff;border:1px dashed #000;border-radius:8px}
[data-testid="stDataFrame"],[data-testid="stDataEditor"]{border:1px solid var(--line);border-radius:8px}
h2,h3{color:#000}

/* login */
.st-key-login{background:var(--panel);border:1px solid #000;overflow:hidden;gap:0 !important}
.login-head{background:#000;padding:28px 24px}
.login-head img{height:56px;display:block}
.login-body{padding:24px 24px 8px}
.login-body h1{margin:0 0 6px;font-size:22px;padding:0}
.login-body p{margin:0 0 12px;color:var(--ink2)}
.st-key-login [data-testid="stElementContainer"]:has(.stButton){padding:0 24px 24px}
.st-key-login .stButton button{background:#000;color:#fff;border:0;border-radius:6px;min-height:44px;font-weight:700}
.st-key-login .stButton button *{color:#fff}

@media (max-width:720px){.block-container{padding:20px 16px 40px}h1.ptitle{font-size:25px}}
</style>"""

MENU = {'AFF': 'Raw Affiliate', 'TAP': 'TAP GMV'}


@functools.cache
def logo_uri():
    return 'data:image/png;base64,' + base64.b64encode((HERE / 'logo-wei.png').read_bytes()).decode()


def header(title, sub):
    st.markdown(f'<h1 class="ptitle">{title}</h1><p class="psub">{sub}</p>', unsafe_allow_html=True)


def login_page(message=None, can_logout=False):
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown('<div style="height:12vh"></div>', unsafe_allow_html=True)
        with st.container(key='login'):
            st.markdown(
                f'<div class="login-head"><img src="{logo_uri()}" alt="WEI"></div>'
                f'<div class="login-body"><h1>Masuk</h1><p>Gunakan akun Google @{DOMAIN}.</p>'
                + (f'<div class="banner bad">{message}</div>' if message else '') + '</div>',
                unsafe_allow_html=True)
            if can_logout:
                st.button('Keluar dan coba akun lain', on_click=st.logout, width='stretch')
            else:
                st.button('Masuk dengan Google', on_click=st.login, width='stretch')


def sidebar(email):
    """Sidebar gaya import Cussons: logo, menu, akun. Mengembalikan menu yang dipilih ('AFF' / 'TAP')."""
    label = st.user.get('name') or email.split('@')[0]
    pic = st.user.get('picture')
    avatar = f'<img src="{pic}" alt="" referrerpolicy="no-referrer">' if pic else (label[:1] or '?').upper()
    with st.sidebar:
        st.markdown(f'<img src="{logo_uri()}" alt="WEI" style="height:32px"><div class="side-brand">Import TikTok</div>'
                    '<div class="side-label">Import</div>', unsafe_allow_html=True)
        for page, text in MENU.items():
            if st.button(text, key=f'nav_{page}', width='stretch',
                         type='primary' if st.session_state.page == page else 'secondary'):
                st.session_state.page = page
                st.rerun()
        st.markdown('<div class="side-label">Data</div>', unsafe_allow_html=True)
        if st.button('Muat ulang data brand', key='reload', width='stretch'):
            brand_data.clear()
            plan.clear()
            plan_tap.clear()
            plan_comb.clear()
        st.markdown(f'<div class="user"><div class="avatar">{avatar}</div><div style="min-width:0">'
                    f'<div class="uname">{label}</div><div class="umail">{email}</div></div></div>',
                    unsafe_allow_html=True)
        st.button('Keluar', key='logout', on_click=st.logout, width='stretch')
    return st.session_state.page


class LogWriter(io.TextIOBase):
    """Tampung print() dari fungsi tulis: tampil live di kotak kode, dan tetap diteruskan ke log server
    (baris '[APPLY] ...' dipakai sebagai jejak siapa mengimpor apa)."""

    def __init__(self, box):
        self.box, self.buf, self.t, self.tee = box, '', 0.0, sys.stdout

    def write(self, s):
        self.buf += s
        self.tee.write(s)
        if time.time() - self.t > 0.3:
            self.flush()
        return len(s)

    def flush(self):
        self.box.code(self.buf[-30000:] or ' ', language=None)
        self.t = time.time()


@contextlib.contextmanager
def capture(key, label, append=False):
    """Jalankan blok di kotak status dengan log live. Log disimpan per `key` supaya tetap tampil setelah rerun.
    Error Google Sheets ditulis ke log lalu dilempar lagi (pemanggil menampilkan st.error)."""
    store = st.session_state.setdefault('runlog', {})
    with st.status(label, expanded=True) as status:
        log = LogWriter(st.empty())
        if append:
            log.buf = store.get(key, '')
        try:
            with contextlib.redirect_stdout(log):
                yield log
        except (HttpError, SystemExit) as e:
            log.write(f'\nERROR: {explain(e, "menulis ke Google Sheets")}\n')
            status.update(label='Gagal, lihat log', state='error', expanded=True)
            raise
        else:
            status.update(label='Selesai', state='complete')
        finally:
            log.flush()
            store[key] = log.buf


def show_result(key):
    """Pesan hasil import terakhir + lognya (kalau ada) untuk file/tujuan ini."""
    done = st.session_state.get('done', (None, ''))
    if done[0] == key:
        st.success(done[1])
    log = st.session_state.get('runlog', {}).get(key)
    if log:
        st.caption('Log import')
        st.code(log[-30000:], language=None)


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


def comb_summary(csid, ckey, base, source):
    """Info baris tujuan + peringatan tanggal yang sudah ada di sheet gabungan. Tidak ada sheet -> dilewati."""
    if not csid:
        return
    try:
        first, _, out, seen = plan_comb(csid, ckey, base)
    except (HttpError, SystemExit) as e:
        st.error(explain(e, 'membaca sheet gabungan'))
        return
    if out:
        st.info(f'Sheet gabungan (tab **{ic.COMB_TAB}**): {n(len(out))} baris Source {source} akan ditambahkan di '
                f'baris **{n(first)} - {n(first + len(out) - 1)}**.')


def comb_write(csid, base, email, name, key):
    """Tulis ke sheet gabungan -> pesan hasil. Kegagalan disimpan supaya bisa dicoba lagi tanpa menulis ulang sheet utama."""
    if not csid:
        return ''
    try:
        with st.spinner('Menulis ke sheet gabungan...'):
            svc = ia.get_service(True, sa_info())
            first, _, out, _ = ic.plan_rows(svc, base, csid)  # hitung ulang tepat sebelum menulis
            n_rows = ic.write_rows(svc, out, first, csid)
    except (HttpError, SystemExit) as e:
        st.session_state['comb_fail'] = (key, csid, base, explain(e, 'menulis ke sheet gabungan'))
        return ''
    st.session_state.pop('comb_fail', None)
    plan_comb.clear()
    print(f'[APPLY GABUNGAN] {email} | {name} | {n_rows} baris di {first}')
    return f' Sheet gabungan: {n(n_rows)} baris ditulis mulai baris {first}.'


def comb_retry(key, email, name, csid=None):
    """csid = link sheet gabungan yang SEKARANG ada di kolom isian (kalau link salah diganti, retry pakai yang baru)."""
    fail = st.session_state.get('comb_fail')
    if fail and fail[0] == key:
        st.error(f'Import ke sheet tujuan sudah selesai, tapi {fail[3]}')
        if st.button('Coba lagi update sheet gabungan', key='retry_comb'):
            with capture(key, 'Menulis ke sheet gabungan...', append=True):
                msg = comb_write(csid or fail[1], fail[2], email, name, key)
            if msg:
                st.session_state['done'] = (key, msg.strip())
            st.rerun()


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


def flow(sid, csid, name, data, email):
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
    show_result(key)
    comb_retry(key, email, name, csid)
    comb_base = ic.aff_rows(rows, mapping)

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
    comb_summary(csid, (key, filled), comb_base, 'SC')
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
            with capture(key, 'Menulis ke Google Sheets...'):
                svc = ia.get_service(True, sa_info())
                # hitung ulang tepat sebelum menulis, supaya aman kalau ada yang menulis di antaranya
                _, first, _, out = ia.plan_rows(svc, rows, mapping, sid=sid)
                print(f'Import {name}: {n(len(out))} baris ke tab {ia.TARGET_TAB} mulai baris {first}, {len(new_ids)} ID baru.')
                n_ids = ia.write_new_ids(svc, new_ids)
                n_rows = ia.write_rows(svc, out, first, sid)
                print(f'[APPLY] {email} | {name} | {n_rows} baris di {first}, {n_ids} ID baru')
                extra = comb_write(csid, comb_base, email, name, key)
        except (HttpError, SystemExit) as e:
            st.error(explain(e, 'menulis ke Google Sheets'))
        else:
            st.session_state['done'] = (key, f'Selesai: {n(n_rows)} baris ditulis mulai baris {first}, '
                                              f'{n_ids} ID baru ke List Produk.{extra}')
            plan.clear()
            brand_data.clear()
            st.rerun()


def flow_tap(sid, csid, name, data, email):
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
    show_result(key)
    comb_retry(key, email, name, csid)
    comb_base = ic.tap_rows(rows, mapping)

    last = first + len(out) - 1
    in_file = collections.Counter(r['Date'] for r in rows)
    gmv ={k: sum(float(ia.num(r[c]) or 0) for r in rows) for k, c in
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
    comb_summary(csid, (key, filled), comb_base, 'TAP')
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
            with capture(key, 'Menulis ke Google Sheets...'):
                svc = ia.get_service(True, sa_info())
                first, _, out, _ = it.plan_rows(svc, rows, mapping, sid)  # hitung ulang tepat sebelum menulis
                print(f'Import {name}: {n(len(out))} baris ke tab {it.TARGET_TAB} mulai baris {first}, {len(new_ids)} ID baru.')
                n_ids = ia.write_new_ids(svc, new_ids)
                n_rows = it.write_rows(svc, out, first, sid)
                print(f'[APPLY TAP] {email} | {name} | {n_rows} baris di {first}, {n_ids} ID baru')
                extra = comb_write(csid, comb_base, email, name, key)
        except (HttpError, SystemExit) as e:
            st.error(explain(e, 'menulis ke Google Sheets'))
        else:
            st.session_state['done'] = (key, f'Selesai: {n(n_rows)} baris ditulis mulai baris {first}, '
                                              f'{n_ids} ID baru ke List Produk.{extra}')
            plan_tap.clear()
            brand_data.clear()
            st.rerun()


def sheet_link(default_id, tab, key):
    link = st.text_input(f'Link Google Sheet tujuan (data masuk ke tab {tab})', key=key,
                         value=f'https://docs.google.com/spreadsheets/d/{default_id}/edit',
                         help='Sheet harus sudah dibagikan (Editor) ke service account.')
    try:
        return ia.sheet_id_from(link)
    except ValueError as e:
        st.error(str(e))
        st.stop()


def comb_link(key):
    link = st.text_input('Link sheet gabungan AFF - TAP (ikut diupdate; kosongkan untuk melewati)', key=key,
                         value=f'https://docs.google.com/spreadsheets/d/{ic.COMB_ID}/edit',
                         help=f'Data ditambahkan ke tab {ic.COMB_TAB}. Sheet harus dibagikan (Editor) ke service account.')
    if not link.strip():
        return None
    try:
        return ia.sheet_id_from(link)
    except ValueError as e:
        st.error(str(e))
        st.stop()


def main():
    st.set_page_config(page_title='Import Affiliate TikTok · WEI', layout='wide', initial_sidebar_state='expanded')
    st.markdown(CSS, unsafe_allow_html=True)
    if not st.user.is_logged_in:
        login_page()
        st.stop()
    email = st.user.get('email')
    if not allowed(email, st.user.get('email_verified'), st.secrets.get('allowed_emails', [])):
        login_page(f'Akun {email} tidak punya akses. Pakai akun @{DOMAIN}.', can_logout=True)
        st.stop()

    st.session_state.setdefault('page', 'AFF')
    page = sidebar(email)
    if page == 'TAP':
        header('Import TAP GMV', 'Upload laporan TAP GMV (xlsx), isi brand yang belum ada, cek ringkasan, lalu '
                                 'Jalankan Import. Hanya baris dengan GMV selain 0 yang dibawa.')
        with st.container(key='form'):
            sid = sheet_link(it.TARGET_ID, it.TARGET_TAB, 'link_tap')
            csid = comb_link('link_comb_tap')
            up = st.file_uploader('File TAP GMV (Excel)', type=['xlsx', 'xlsm'], key='up_tap')
        if up:
            with st.container(key='summary'):
                flow_tap(sid, csid, up.name, up.getvalue(), email)
        return
    header('Import Raw Affiliate', 'Satu file per kali: upload file, isi brand yang belum ada, cek ringkasan, '
                                   'lalu Jalankan Import.')
    with st.container(key='form'):
        sid = sheet_link(ia.TARGET_ID, ia.TARGET_TAB, 'link_aff')
        csid = comb_link('link_comb_aff')
        up = st.file_uploader('File raw AFF (CSV / Excel)', type=['csv', 'xlsx', 'xlsm'], key='up_aff')
    if up:
        with st.container(key='summary'):
            flow(sid, csid, up.name, up.getvalue(), email)


if __name__ == '__main__':
    main()
