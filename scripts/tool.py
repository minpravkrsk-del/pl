# -*- coding: utf-8 -*-
"""
Инструмент автообновления недельной формы.

Режимы:
  prep  — четверг 10:00: очистить заполненные ячейки между разделами,
          обновить даты в первой строке (даты следующей недели).
  fill  — заполнить основной раздел формы из календаря,
          сохранить снапшот внесённых мероприятий.
  sync  — утро 9:30 / 10:00 / 10:50 / 11:30: сверка с календарём:
          добавить новые, удалить пропавшие; ручные правки не перезаписывает.

Примеры:
  python mediaplan_tool.py prep --monday 2026-10-12 --out form.docx
  python mediaplan_tool.py fill --monday 2026-10-12 --src form.docx --out form_filled.docx --state state.json
  python mediaplan_tool.py sync --monday 2026-10-12 --src form_filled.docx --out form_synced.docx --state state.json
"""
import sys, os, re, json, argparse, difflib, urllib.request, urllib.parse
from datetime import datetime, timedelta
from copy import deepcopy

CAL_TOKEN = os.environ.get("CAL_TOKEN", "").strip()
if not CAL_TOKEN:
    sys.exit("CAL_TOKEN not set")

CALENDAR_URL = ("https://calendar.yandex.ru/export/html.xml"
                f"?private_token={CAL_TOKEN}"
                "&tz_id=Asia/Krasnoyarsk&limit=300")
# форма: публичная ссылка на папку + имя файла внутри (только из переменных окружения)
FOLDER_PUBLIC_URL = os.environ.get("FORM_URL", "").strip()
FORM_NAME_IN_FOLDER = os.environ.get("FORM_NAME", "").strip()
TEMPLATE_PUBLIC_URL = os.environ.get("FORM_URL_FALLBACK", "").strip()

MONTHS = {1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
          7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'}

# ------------------------------------------------------------------ органы ---
# канонич. имя: список псевдонимов (lower, е вместо ё). Порядок не важен:
# выбирается самое длинное совпадение.
# ------------------------------------------------------------------ органы ---
# Фиксированный перечень органов — сокращённые названия строго как в форме.
# Сопоставление записей календаря: у министерств после приставки «МИН» идёт
# корень названия (МИНКУЛЬТ → «культ»), по нему запись сводится к канону.
# Корни вычисляются из самих сокращений; отдельно — агентства и редкие полные
# названия. Нераспознанное попадает в отчёт «НЕРАСПОЗНАННЫЕ ОРГАНЫ».
ORDER = ['МИНЗДРАВ', 'МИНОБР', 'МИНСТРОЙ', 'МСП', 'МИНФИН', 'МИНЭК', 'МИНТРАНС',
         'ТУРИЗМ', 'МИНСЕЛЬХОЗ', 'МИНЦИФРЫ', 'ТРУД И ЗАНЯТОСТЬ', 'МИНСОЦ',
         'МИНКУЛЬТ', 'КМНС', 'МИНСПОРТ', 'МОЛОДЕЖКА', 'МИНЭКОЛОГИИ',
         'МИНПРИРОДЫ', 'МИНПРОМ', 'МИНТАРИФ']


def _root(canon):
    w = canon[3:].lower()
    return w[:-1] if w and w[-1] in 'аеёиоуыэюя' else w


# корни министерств: длиннейший совпавший корень выигрывает («экологии» →
# МИНЭКОЛОГИИ, а не МИНЭК)
MIN_ROOTS = sorted(
    {(_root(c), c) for c in ORDER if c.startswith('МИН') and len(c) > 3},
    key=lambda x: -len(x[0]))

# агентства и особые сокращения: работают по тому же корневому принципу —
# полные словосочетания сводятся к сокращению; короткие ключи — страховка
AGENCY_RULES = sorted([
    ('агентство по развитию северных территорий и поддержке коренных малочисленных народов', 'КМНС'),
    ('агентство развития малого и среднего предпринимательства', 'МСП'),
    ('агентство молодёжной политики и реализации программ общественного развития', 'МОЛОДЕЖКА'),
    ('агентство молодежной политики и реализации программ общественного развития', 'МОЛОДЕЖКА'),
    ('агентство труда и занятости населения', 'ТРУД И ЗАНЯТОСТЬ'),
    ('труд и занятость населения', 'ТРУД И ЗАНЯТОСТЬ'),
    ('коренные малочисленные народы севера', 'КМНС'),
    ('коренные малочисленные народы', 'КМНС'),
    ('малое и среднее предпринимательство', 'МСП'),
    ('агентство по развитию северных территорий', 'КМНС'),
    ('агентство труда и занятости', 'ТРУД И ЗАНЯТОСТЬ'),
    ('агентство молодёжной политики', 'МОЛОДЕЖКА'),
    ('агентство молодежной политики', 'МОЛОДЕЖКА'),
    ('молодежная политика', 'МОЛОДЕЖКА'),
    ('агентство по туризму', 'ТУРИЗМ'),
    ('агентство туризма', 'ТУРИЗМ'),
    ('агентство мсп', 'МСП'),
    ('агентство труда', 'ТРУД И ЗАНЯТОСТЬ'),
    ('труд и занятость', 'ТРУД И ЗАНЯТОСТЬ'),
    ('молодежка', 'МОЛОДЕЖКА'),
    ('туризм', 'ТУРИЗМ'),
    ('спорт', 'МИНСПОРТ'),
    ('кмнс', 'КМНС'),
    ('мсп', 'МСП'),
], key=lambda x: -len(x[0]))


# точечные опечатки в названиях календаря (регулярки, регистр не важен)
TYPO_FIXES = [
    (r'на приме\s*-', 'на приёме —'),
    (r'\(\s*уточняется', '(уточняется'),
    (r'пресс-рели\b', 'пресс-релиз'),
    (r'пресс-срелиз', 'пресс-релиз'),
]

# нацпроекты / госпрограммы (полные названия для поиска)
NATPROJ = [
    'Кадры', 'Молодёжь и дети', 'Продолжительная и активная жизнь', 'Семья',
    'Экологическое благополучие', 'Экономика данных и цифровая трансформация государства',
    'Эффективная и конкурентная экономика', 'Инфраструктура для жизни',
    'Туризм и гостеприимство', 'Туризм и индустрия гостеприимства',
    'Беспилотные авиационные системы', 'Транспортная мобильность',
    'Жильё и городская среда', 'Наука, технологии и инженерное образование',
    'Международная кооперация и экспорт', 'Средства производства и автоматизация',
    'Новые материалы и химия', 'Технологическое обеспечение продовольственной безопасности',
    'Модернизация оборонно-промышленного комплекса', 'Содействие занятости',
    'Демография', 'Здравоохранение', 'Образование', 'Безопасные качественные дороги',
    'Цифровая экономика', 'Малое и среднее предпринимательство',
]
GOVPROGRAMS = ['Спорт России']

GOVERNORS = [g.strip().lower() for g in os.environ.get("GOVERNORS", "").split(",") if g.strip()]


# --------------------------------------------------------------- календарь ---
def fetch_calendar():
    req = urllib.request.Request(CALENDAR_URL, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=60).read().decode('utf-8')


def fetch_template(path):
    """Скачать форму: по публичной ссылке на папку (+ путь внутри),
    при недоступности — по старой ссылке на файл."""
    api = ("https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key="
           + urllib.parse.quote(FOLDER_PUBLIC_URL)
           + "&path=" + urllib.parse.quote(FORM_NAME_IN_FOLDER))
    req = urllib.request.Request(api, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    try:
        href = json.loads(urllib.request.urlopen(req, timeout=30).read())['href']
    except Exception:
        # запасной путь — старая публичная ссылка на сам файл
        api = ("https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key="
               + urllib.parse.quote(TEMPLATE_PUBLIC_URL))
        req = urllib.request.Request(api, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
        href = json.loads(urllib.request.urlopen(req, timeout=30).read())['href']
    req2 = urllib.request.Request(href, headers={'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'})
    data = urllib.request.urlopen(req2, timeout=60).read()
    with open(path, 'wb') as f:
        f.write(data)
    return len(data)


def decode_html(s):
    return (s.replace('&laquo;', '«').replace('&raquo;', '»').replace('&mdash;', '—')
             .replace('&ndash;', '–').replace('&quot;', '"').replace('&amp;', '&'))


def parse_calendar(html):
    chunks = html.split('<div class="b-content-event">')
    out = []
    for chunk in chunks[1:]:
        title_m = re.search(r'<h1>(.*?)</h1>', chunk)
        time_m = re.findall(r'<span>(.*?)</span>', chunk)
        desc_m = re.search(r'<div class="e-description">(.*?)</div>\s*</div>', chunk)
        title = decode_html(title_m.group(1).strip()) if title_m else ''
        times = [t.strip() for t in time_m] if time_m else []
        desc = desc_m.group(1).strip() if desc_m else ''
        desc = re.sub(r'<br\s*/?>', '\n', desc)
        desc = decode_html(desc)
        out.append({'title': title, 'times': times, 'desc': desc})
    return out


MONTH_IDX = {v: k for k, v in MONTHS.items()}


def parse_cal_date(s):
    m = re.match(r'(\d+)\s+([а-яё]+)\s+(\d+)\s+(\d+):(\d+)', s)
    if m:
        return datetime(int(m.group(3)), MONTH_IDX.get(m.group(2), 0),
                        int(m.group(1)), int(m.group(4)), int(m.group(5)))
    return None


# ------------------------------------------------------------------- органы ---
def match_org(h):
    """(канон, сколько символов нормализованного заголовка занимает орган)"""
    if not h:
        return None, 0
    for key, canon in AGENCY_RULES:
        if h == key or h.startswith(key + ' ') or h.startswith(key + '.'):
            return canon, len(key)
    parts = h.split(' ', 1)
    w0, tail = parts[0], (parts[1] if len(parts) > 1 else '')
    if w0 == 'мин' and tail:  # «мин экологии»
        for root, canon in MIN_ROOTS:
            if tail.startswith(root):
                return canon, len(w0) + 1 + len(tail.split(' ')[0])
        return None, 0
    if w0.startswith('мин') and len(w0) > 3:
        body = w0[3:]
        for root, canon in MIN_ROOTS:
            if body.startswith(root):
                return canon, len(w0)
        # опечатки в корне: близость написания, только корни от 4 символов
        best, best_r = None, 0.0
        for root, canon in MIN_ROOTS:
            if len(root) < 4:
                continue
            r = difflib.SequenceMatcher(None, body, root).ratio()
            if r > best_r:
                best, best_r = canon, r
        if best and best_r >= 0.65:
            return best, len(w0)
    return None, 0


def canon_org(title):
    """(канонич. орган, остаток заголовка)"""
    t = title.strip().lstrip('?').lstrip('!').strip()
    m = re.match(r'^([^:]{1,80}?)[.:]\s+', t + ' ')
    header = (m.group(1) if m else t.split(':')[0]).strip()
    h = re.sub(r'\s+', ' ', header.lower().replace('ё', 'е'))
    canon, cut = match_org(h)
    if canon:
        rest = t[cut:].lstrip(' :.·–—-').strip()
        # дублированный префикс органа ("МИНСТРОЙ: МИНСТРОЙ: ...")
        rest = re.sub(rf'^(?:{re.escape(canon)}\s*[:.·]\s*)+', '', rest, flags=re.I).strip()
        for a, b in TYPO_FIXES:
            rest = re.sub(a, b, rest, flags=re.I)
        rest = rest.rstrip(':').strip()
        return canon, rest
    return header.upper(), t.strip()


def order_index(canon):
    return ORDER.index(canon) if canon in ORDER else 99


# ------------------------------------------------------------- форматы/нацпроекты ---
def normalize_formats(desc):
    d = (desc or '').lower().replace('ё', 'е')
    fmt = []
    if re.search(r'пресс-релиз|пресс релиз|\bрелиз', d):
        fmt.append('пресс-релиз')
    if re.search(r'соцсет|соц сет|соцсеть|\bпост\b|пост,', d):
        fmt.append('соцсети')
    if re.search(r'\bтв\b|\btv\b|\bтв-|телевидени|телеканал|\bсюжет|в эфир|\bэфир|съемк|репортаж', d):
        fmt.append('ТВ')
    if re.search(r'\bрадио', d):
        fmt.append('радио')
    if re.search(r'интернет-сми|сетевое издание|\bна сайте\b|\bна портале\b|\bсайт\b', d):
        fmt.append('интернет СМИ')
    if re.search(r'\bсми\b', d):
        fmt.append('СМИ')
    if re.search(r'\bинтервью', d):
        fmt.append('интервью')
    if re.search(r'\bстать[юия]\b|\bстатьи\b', d):
        fmt.append('статья')
    if not fmt:
        fmt = ['пресс-релиз', 'соцсети']
    return fmt


def find_natproj(text):
    """Список строк: 'Нацпроект «X»' / 'Госпрограмма «X»'."""
    t = text or ''
    low = t.lower().replace('ё', 'е')
    found = []

    def add(kind, name):
        label = f'{kind} «{re.sub(chr(92)+"s+", " ", name.strip())}»'
        if label not in found:
            found.append(label)

    for x in re.findall(r'[Нн]ацпроект[а-яё]*\s*«([^»]+)»', t):
        add('Нацпроект', x)
    for x in re.findall(r'[Нн]ацпроект[а-яё]*\s*"([^"]+)"', t):
        add('Нацпроект', x)
    for x in re.findall(r'[Гг]оспрограмм[аы]\s*«([^»]+)»', t):
        add('Госпрограмма', x)
    for x in re.findall(r'[Гг]оспрограмм[аы]\s*"([^"]+)"', t):
        add('Госпрограмма', x)
    for name in NATPROJ:
        nl = name.lower().replace('ё', 'е')
        if f'«{name}»' in t or f'"{name}"' in t or f'“{name}”' in t or f'"{name}"' in t.replace('"', '"'):
            if ('нацпроект' in low or 'госпрограмм' in low or True) and nl not in low.replace(f'«{nl}»', ''):
                pass
            add('Нацпроект', name)
        elif nl in low and ('нацпроект' in low or 'госпрограмм' in low):
            add('Нацпроект', name)
    for name in GOVPROGRAMS:
        nl = name.lower().replace('ё', 'е')
        if f'«{name}»' in t or f'"{name}"' in t or f'“{name}”' in t or nl in low:
            add('Госпрограмма', name)
    return found


def is_governor(text):
    low = (text or '').lower().replace('ё', 'е')
    return any(g in low for g in GOVERNORS)


FMT_TOKENS = {'пресс-релиз', 'пресс-срелиз', 'пресс', 'релиз', 'соцсети', 'соц', 'сети',
              'сеть', 'пост', 'тв', 'сми', 'интернет-сми', 'интернет', 'радио',
              'статья', 'статьи', 'интервью', 'сюжет', 'сюжеты', 'съемка', 'эфир',
              'телеканал', 'формат', 'и', 'а'}


def line_is_format_only(line):
    s = re.sub(r'[«»"“”' + "'" + r',.;:!()\-—–\s]+', ' ', line.lower().replace('ё', 'е'))
    words = [w for w in s.split() if w]
    return bool(words) and all(w in FMT_TOKENS for w in words)


def clean_desc(desc):
    """Убрать из описания чисто-форматные строки и хвост-перечень форматов."""
    if not desc:
        return ''
    lines = [l for l in (x.strip() for x in desc.split('\n')) if l]
    kept = [l for l in lines if not line_is_format_only(l)]
    out = '\n'.join(kept)
    # хвост из перечисления форматов в конце текста
    out = re.sub(
        r'[,.;:\s]*(?:пресс-релиз|релиз|соцсети|соц\.\s*сети|пост|тв|сми|радио)'
        r'(?:[,.;:\s]+(?:пресс-релиз|релиз|соцсети|пост|тв|сми|радио))*[.,]?\s*$',
        '', out, flags=re.I).strip()
    for a, b in TYPO_FIXES:
        out = re.sub(a, b, out, flags=re.I)
    return re.sub(r'\s+', ' ', out).strip()


# -------------------------------------------------------------------- DOCX ---
from docx import Document  # noqa: E402
from docx.shared import Pt  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

SECTION_NAMES = [s.strip() for s in os.environ.get("SECTIONS", "").split(",") if s.strip()]


def require_sections(sections, tag):
    missing = [n for n in SECTION_NAMES if n not in sections]
    if missing:
        print(f"[{tag}] В форме не найдены разделы: {', '.join(missing)} — проверьте строки-заголовки разделов")
        sys.exit(2)


def find_sections(table):
    starts = []
    for ri, row in enumerate(table.rows):
        t = row.cells[0].text.strip()
        if t in SECTION_NAMES:
            starts.append((t, ri))
    sections = {}
    for i, (n, ri) in enumerate(starts):
        end = starts[i + 1][1] - 1 if i + 1 < len(starts) else len(table.rows) - 1
        sections[n] = {'header': ri, 'body': list(range(ri + 1, end + 1))}
    return sections


def clear_cell(cell):
    ps = cell.paragraphs
    if ps:
        first = ps[0]
        for r in list(first.runs):
            r._r.getparent().remove(r._r)
        for p in ps[1:]:
            p._p.getparent().remove(p._p)
    else:
        cell.add_paragraph()


def set_run(run, size=10, name='Times New Roman', bold=None):
    run.font.size = Pt(size)
    run.font.name = name
    if bold is not None:
        run.bold = bold


def add_lines(paragraph, lines, size=10):
    """Строки в одном абзаце через перенос строки (как в шаблоне)."""
    for i, ln in enumerate(lines):
        r = paragraph.add_run(ln)
        set_run(r, size=size)
        if i < len(lines) - 1:
            r.add_break()


def polish_text(text):
    """Редакторская нормализация текста события (орфография/грамматика):
    - первый символ после «ОРГАН:» — заглавная;
    - точка в конце текста (если нет .!?…» и т.п.);
    - пробел перед точкой/запятой убирается, двойные пробелы сжимаются;
    - « т.д.", « т.п.» — нормализация не делается (не лезем в стиль).
    """
    if not text or not text.strip():
        return text
    t = re.sub(r'[ \t]+', ' ', text.strip())
    t = re.sub(r'\s+([.,;:!?])', r'\1', t)
    # пробел после , . ; : !? между словами (если его нет)
    t = re.sub(r'([а-яёa-z][,;:.!?])(?=[а-яёА-ЯЁA-Z])', r'\1 ', t)
    # капитализация после «ОРГАН:»
    m = re.match(r'^([А-ЯЁ]{2,}(?: [А-ЯЁ]{2,})?):\s*(.*)$', t, flags=re.S)
    if m and m.group(2):
        head, rest = m.group(1), m.group(2)
        rest = rest[0].upper() + rest[1:]
        t = f"{head}: {rest}"
    elif t and t[0].isalpha() and t[0].islower():
        # первое слово текста (описание) — с заглавной
        t = t[0].upper() + t[1:]
    # точка в конце (если нет завершающей пунктуации)
    if t and t[-1] not in '.!?…»)"]':
        t += '.'
    return t


def write_event(cell, ev):
    """Записать мероприятие в ячейку: нацпроект(ы) жирным, пустая строка,
    ОРГАН: заголовок, пустая строка, описание, пустая строка, форматы."""
    clear_cell(cell)
    if ev.get('nats'):
        for n in ev['nats']:
            p = cell.add_paragraph()
            r = p.add_run(n)
            set_run(r, 10, bold=True)
        cell.add_paragraph()
    p = cell.add_paragraph()
    lines = [f"{ev['canon']}: {polish_text(ev['title'])}"]
    if ev.get('desc'):
        lines += ['', polish_text(ev['desc'])]
    lines += [''] + [polish_text(f) if not re.fullmatch(r'[А-ЯЁа-яё /\-]+', f) else f for f in ev['formats']]
    add_lines(p, lines, size=10)


def cell_text_norm(cell):
    return re.sub(r'\s+', ' ', cell.text).strip().lower()


def title_norm(t):
    return re.sub(r'\s+', ' ', (t or '')).strip().lower()


def cell_contains_title(cell, title):
    """Похоже ли событие уже стоит в ячейке (сравнение по значимым словам)."""
    ct = cell_text_norm(cell)
    tn = title_norm(title)
    if not ct or not tn:
        return False
    t_words = [w for w in re.split(r'\W+', tn) if len(w) > 3]
    if not t_words:
        return False
    hit = sum(1 for w in t_words if w in ct)
    return hit / len(t_words) >= 0.6


# -------------------------------------------------------------------- режимы ---
def collect_week_events(monday):
    """События недели из календаря: [{'day', 'canon', 'title', 'desc', 'start', 'formats', 'nats', 'gov'}]"""
    html = fetch_calendar()
    events = parse_calendar(html)
    target_start = datetime(monday.year, monday.month, monday.day)
    target_end = target_start + timedelta(days=7)
    week = []
    skipped_gov = []
    for ev in events:
        if not ev['times']:
            continue
        start = parse_cal_date(ev['times'][0])
        if not (start and target_start <= start < target_end):
            continue
        canon, rest = canon_org(ev['title'])
        text_all = ev['title'] + '\n' + ev['desc']
        if is_governor(text_all):
            skipped_gov.append({'start': start, 'title': ev['title'], 'desc': ev['desc']})
            continue
        week.append({
            'day': (start - target_start).days,
            'canon': canon,
            'title': rest,
            'desc': clean_desc(ev['desc']),
            'start': start.strftime('%Y-%m-%d %H:%M'),
            'formats': normalize_formats(ev['desc']),
            'nats': find_natproj(text_all),
        })
    # дедупликация одинаковых
    seen = set()
    dedup = []
    for e in week:
        key = (e['day'], e['canon'], title_norm(e['title']), e['start'])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(e)
    return dedup, skipped_gov, len(events)


def cmd_prep(args):
    if not args.src:
        n = fetch_template('/tmp/_template.docx')
        args.src = '/tmp/_template.docx'
        print(f"Шаблон скачан с Диска: {n} байт")
    doc = Document(args.src)
    table = doc.tables[0]
    sections = find_sections(table)
    monday = datetime.strptime(args.monday, '%Y-%m-%d').date()
    # очистка заполненных ячеек между разделами
    cleared = 0
    for name, sec in sections.items():
        if name == 'СПЕЦПРОЕКТЫ' and args.keep_spec:
            continue
        for ri in sec['body']:
            for ci in range(7):
                c = table.cell(ri, ci)
                if c.text.strip():
                    cleared += 1
                clear_cell(c)
    # даты следующей недели
    for ci in range(7):
        cell = table.cell(0, ci)
        d = monday + timedelta(days=ci)
        text = f"{d.day} {MONTHS[d.month]}"
        p = cell.paragraphs[0]
        if p.runs:
            p.runs[0].text = text
            for r in p.runs[1:]:
                r._r.getparent().remove(r._r)
        else:
            r = p.add_run(text)
            r.bold = True
    # строка праздников (вторая строка): очистить все дни
    holidays_cleared = 0
    for ci in range(7):
        c = table.cell(1, ci)
        if c.text.strip():
            holidays_cleared += 1
        clear_cell(c)
    doc.save(args.out)
    print(f"[prep] Неделя: {monday.strftime('%d.%m.%Y')}–{(monday + timedelta(days=6)).strftime('%d.%m.%Y')}")
    print(f"[prep] Очищено ячеек: {cleared}; разделы: {', '.join(sections)}")
    if args.keep_spec:
        print("[prep] СПЕЦПРОЕКТЫ не тронут (--keep-spec)")
    if holidays_cleared:
        print(f"[prep] Строка праздников очищена (в {holidays_cleared} дн. был текст) — заполнит редактор.")
    else:
        print("[prep] Строка праздников пуста.")


def ensure_org_rows(table, sections, needed):
    org_body = sections['ОРГАНЫ ВЛАСТИ']['body']
    max_len = max(needed) if needed else 1
    if max_len > len(org_body):
        tbl = table._tbl
        last_tr = table.rows[org_body[-1]]._tr
        for _ in range(max_len - len(org_body)):
            new_tr = deepcopy(last_tr)
            tbl.append(new_tr)
        # очистить только добавленные строки (после пересчёта секций)
        fresh_rows = find_sections(table)['ОРГАНЫ ВЛАСТИ']['body'][len(org_body):]
        for ri in fresh_rows:
            for c in table.rows[ri].cells:
                clear_cell(c)
    return find_sections(table)


def cmd_fill(args):
    if not args.src:
        fetch_template('/tmp/_template.docx')
        args.src = '/tmp/_template.docx'
    doc = Document(args.src)
    table = doc.tables[0]
    sections = find_sections(table)
    require_sections(sections, 'fill')
    org_filled = sum(1 for ri in sections['ОРГАНЫ ВЛАСТИ']['body'] for ci in range(7)
                     if table.cell(ri, ci).text.strip())
    if org_filled:
        print(f"[fill] ОТМЕНА: в разделе ОРГАНЫ ВЛАСТИ есть заполненные ячейки ({org_filled}). "
              "Это либо ручное заполнение, либо не выполнялся prep. Ручное не трогаю; "
              "если это остатки прошлой недели — сначала запустите prep.")
        sys.exit(3)
    monday = datetime.strptime(args.monday, '%Y-%m-%d').date()

    state = {}
    if args.state:
        try:
            with open(args.state, encoding='utf-8') as f:
                state = json.load(f)
            if state.get('week') == args.monday and state.get('events'):
                print("[fill] ВНИМАНИЕ: снапшот этой недели уже существует — выполняю sync вместо fill")
                return cmd_sync(args)
        except FileNotFoundError:
            pass

    events, gov, total = collect_week_events(monday)
    per_day = {}
    for e in events:
        per_day.setdefault(e['day'], []).append(e)
    for d in per_day:
        per_day[d].sort(key=lambda x: (order_index(x['canon']), x['start']))
    needed = [len(per_day.get(d, [])) for d in range(7)]
    sections = ensure_org_rows(table, sections, needed)
    org_body = sections['ОРГАНЫ ВЛАСТИ']['body']

    snapshot = []
    for d in range(7):
        for k, ev in enumerate(per_day.get(d, [])):
            cell = table.cell(org_body[k], d)
            write_event(cell, ev)
            snapshot.append({
                'day': d, 'canon': ev['canon'], 'title': ev['title'],
                'start': ev['start'],
                'sig': None,  # пересчитается после LLM-полировки
            })

    # LLM-редактура (если задан YC_API_KEY) — потом пересчитать sig
    changes = llm_polish_org_cells(doc, sections)
    for c in changes:
        print("[llm]", c)
    for s in snapshot:
        s['sig'] = cell_text_norm(table.cell(org_body[s['day']], s['day']))

    doc.save(args.out)
    if args.state:
        with open(args.state, 'w', encoding='utf-8') as f:
            json.dump({'week': args.monday, 'events': snapshot}, f, ensure_ascii=False, indent=1)

    print(f"[fill] Неделя {args.monday}: событий в календаре всего {total}, на неделю попало {len(events)} "
          f"(+{len(gov)} вне основного раздела — пропущены)")
    if gov:
        print("[fill] События вне основного раздела — вручную:")
        for g in sorted(gov, key=lambda x: x['start']):
            print(f"    {g['start']}  {g['title'][:90]}")
    print("[fill] По дням: " + ", ".join(
        f"{(monday + timedelta(days=d)).strftime('%d.%m')}={len(per_day.get(d, []))}" for d in range(7)))
    unknown = sorted({e['canon'] for e in events if e['canon'] not in ORDER})
    if unknown:
        print(f"[fill] НЕРАСПОЗНАННЫЕ ОРГАНЫ (проверить): {unknown}")
    nats = [e for e in events if e['nats']]
    if nats:
        print("[fill] Нацпроекты:")
        for e in nats:
            print(f"    {(monday + timedelta(days=e['day'])).strftime('%d.%m')} {e['canon']}: {', '.join(e['nats'])}")


def canon_of_cell(cell):
    t = cell.text.lower()
    for canon in ORDER:
        if canon.lower() + ':' in t:
            return canon
    return None


def cmd_sync(args):
    if not args.src:
        fetch_template('/tmp/_template.docx')
        args.src = '/tmp/_template.docx'
    doc = Document(args.src)
    table = doc.tables[0]
    sections = find_sections(table)
    require_sections(sections, 'sync')
    monday = datetime.strptime(args.monday, '%Y-%m-%d').date()
    org_body = sections['ОРГАНЫ ВЛАСТИ']['body']

    try:
        with open(args.state, encoding='utf-8') as f:
            state = json.load(f)
    except FileNotFoundError:
        print(f"[sync] ОТМЕНА: снапшот не найден ({args.state}). Сначала выполните fill.")
        sys.exit(3)
    if state.get('week') != args.monday:
        print(f"[sync] ОШИБКА: снапшот для недели {state.get('week')}, а запрошена {args.monday}")
        sys.exit(2)

    events, gov, total = collect_week_events(monday)
    fresh = {}
    for e in events:
        fresh[(e['day'], e['canon'], title_norm(e['title']))] = e
    snap = {}
    for s in state['events']:
        snap[(s['day'], s['canon'], title_norm(s['title']))] = s

    # защита снапшота: если раздел ОРГАНЫ ВЛАСТИ в форме полностью пуст,
    # а в снапшоте есть события — похоже, fill не выполнялся (или форму очистили);
    # синхронизацию отменяем, чтобы не «удалить» все события из снапшота
    org_filled = sum(1 for ri in org_body for ci in range(7)
                     if table.cell(ri, ci).text.strip())
    if not org_filled and state['events']:
        print(f"[sync] ОТМЕНА: раздел ОРГАНЫ ВЛАСТИ пуст, а в снапшоте "
              f"{len(state['events'])} событий. Похоже, fill не выполнялся. Сначала fill.")
        sys.exit(3)

    # --- поиск добавлений и удалений ---
    to_add, to_remove, changed, flagged = [], [], [], []

    # совпадения по (день, орган, время) — переименования
    fresh_by_slot = {}
    for k, e in fresh.items():
        fresh_by_slot.setdefault((k[0], k[1], e['start']), []).append(k)
    snap_by_slot = {}
    for k, s in snap.items():
        snap_by_slot.setdefault((k[0], k[1], s['start']), []).append(k)

    for k, e in fresh.items():
        if k in snap:
            continue
        slot = (k[0], k[1], e['start'])
        matched_snap = None
        for sk in snap_by_slot.get(slot, []):
            matched_snap = sk
            break
        if matched_snap:
            changed.append((matched_snap, e))  # то же событие, изменился заголовок
        else:
            to_add.append(e)

    for k, s in snap.items():
        if k in fresh:
            continue
        slot = (k[0], k[1], s['start'])
        if slot in fresh_by_slot:
            continue  # изменился заголовок — обработано как changed
        # событие пропало или сдвинулось по времени
        same_day_org = [ek for ek in fresh if ek[0] == k[0] and ek[1] == k[1]]
        if same_day_org:
            flagged.append(('сдвиг по времени', s, [fresh[e]['start'] for e in same_day_org]))
            to_remove.append(k)
        else:
            to_remove.append(k)

    report = []

    # --- удаление пропавших ---
    for k in to_remove:
        s = snap[k]
        day = s['day']
        target = title_norm(s['title'])
        found = None
        for j, ri in enumerate(org_body):
            cell = table.cell(ri, day)
            ct = cell_text_norm(cell)
            if not ct:
                continue
            if ct == s.get('sig'):
                found = (ri, 'exact')
                break
            if target and target in ct:
                found = (ri, 'contains')
        if found:
            ri, how = found
            clear_cell(table.cell(ri, day))
            report.append(f"  УДАЛЕНО {day_names_l(monday)[day]}: {s['canon']}: {s['title'][:70]} [{how}]")
        else:
            report.append(f"  ! НЕ НАЙДЕНО для удаления {day_names_l(monday)[day]}: {s['canon']}: {s['title'][:70]} — проверьте вручную")

    # --- перезапись изменившихся (только если ячейка не отредактирована вручную) ---
    for sk, e in changed:
        s = snap[sk]
        day = s['day']
        rewritten = False
        for ri in org_body:
            cell = table.cell(ri, day)
            ct = cell_text_norm(cell)
            if ct and ct == s.get('sig'):
                write_event(cell, e)
                snap[sk] = {'day': day, 'canon': e['canon'], 'title': e['title'],
                            'start': e['start'],
                            'sig': cell_text_norm(cell)}
                report.append(f"  ОБНОВЛЕНО {day_names_l(monday)[day]}: {e['canon']}: {e['title'][:60]}")
                rewritten = True
                break
        if not rewritten:
            report.append(f"  ! ИЗМЕНИЛОСЬ, но ячейка отредактирована вручную — не тронуто: "
                          f"{day_names_l(monday)[day]} {s['canon']}: {s['title'][:60]}")

    # --- добавление новых ---
    for e in to_add:
        day = e['day']
        # защита от дубля: событие может уже стоять в отредактированной вручную ячейке
        dup_row = None
        for ri in org_body:
            if cell_contains_title(table.cell(ri, day), e['title']):
                dup_row = ri
                break
        if dup_row is not None:
            report.append(f"  ? ПОХОЖЕ УЖЕ ЕСТЬ {day_names_l(monday)[day]}: {e['canon']}: {e['title'][:70]} — не добавлял, проверьте")
            continue
        while True:
            cells = [(ri, table.cell(ri, day)) for ri in org_body]
            empty = [(j, ri) for j, (ri, c) in enumerate(cells) if not c.text.strip()]
            if empty:
                break
            ensure_org_rows(table, sections, [len(org_body) + 1] * 7)
            sections = find_sections(table)
            org_body = sections['ОРГАНЫ ВЛАСТИ']['body']
        j0 = empty[0][1]
        chosen = None
        for j, ri in empty:
            if j > 0 and canon_of_cell(cells[j - 1][1]) == e['canon']:
                chosen = ri
                break
        if chosen is None:
            chosen = j0
        cell = table.cell(chosen, day)
        write_event(cell, e)
        snap[(day, e['canon'], title_norm(e['title']))] = {
            'day': day, 'canon': e['canon'], 'title': e['title'], 'start': e['start'],
            'sig': cell_text_norm(cell)}
        report.append(f"  ДОБАВЛЕНО {day_names_l(monday)[day]}: {e['canon']}: {e['title'][:70]}")

    # --- сохранение ---
    state['events'] = list(snap.values())
    changes = llm_polish_org_cells(doc, sections)
    if changes:
        print("[llm]", *changes, sep='\n')
        # обновить sig в снапшоте под изменённые ячейки
        for s in state['events']:
            day = s['day']
            for ri in org_body:
                ct = cell_text_norm(table.cell(ri, day))
                if ct and s['title'].lower() in ct:
                    s['sig'] = ct
                    break
    doc.save(args.out)
    with open(args.state, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)

    print(f"[sync] Календарь: всего {total}, на неделе {len(events)} (+{len(gov)} вне раздела)")
    print(f"[sync] Добавлено: {len(to_add)}, удалено: {len(to_remove)}, обновлено: {len(changed)}")
    for r in report:
        print(r)
    if gov:
        print("[sync] События вне основного раздела (для ручного переноса):")
        for g in sorted(gov, key=lambda x: x['start']):
            print(f"    {g['start']}  {g['title'][:90]}")
    unknown = sorted({e['canon'] for e in events if e['canon'] not in ORDER})
    if unknown:
        print(f"[sync] НЕРАСПОЗНАННЫЕ ОРГАНЫ: {unknown}")


def day_names_l(monday):
    return [(monday + timedelta(days=d)).strftime('%d.%m') for d in range(7)]




# ---------- LLM-редактура (опционально) ----------
LLM_API_KEY = os.environ.get("YC_API_KEY", "").strip()
LLM_FOLDER_ID = os.environ.get("YC_FOLDER_ID", "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "yandexgpt-lite")


def llm_available():
    return bool(LLM_API_KEY and LLM_FOLDER_ID)


def llm_polish_texts(texts):
    """Пакетная редактура текстов через YandexGPT. Возвращает список той же длины.
    При любой ошибке — исходные тексты (fallback на правила)."""
    if not texts or not llm_available():
        return texts
    SEP = "\n===\n"
    payload = SEP.join(texts)
    prompt = (
        "Ты редактор официального текстового плана. "
        "Исправь орфографию, грамматику и пунктуацию в каждом фрагменте. "
        "Правила: не меняй смысл, названия, даты, числа и аббревиатуры "
        "(МО, КМНС и т.п.); сохраняй кавычки «»; не добавляй новых предложений; "
        "верни РОВНО столько же фрагментов, разделив их строкой '==='; "
        "без пояснений и кавычек вокруг ответа.")
    body = json.dumps({
        "modelUri": f"gpt://{LLM_FOLDER_ID}/{LLM_MODEL}",
        "completionOptions": {"temperature": 0.1, "maxTokens": "8000"},
        "messages": [{"role": "user", "text": prompt + "\n\n" + payload}],
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        data=body,
        headers={"Authorization": "Api-Key " + LLM_API_KEY,
                 "Content-Type": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.load(r)
            out = resp['result']['alternatives'][0]['message']['text']
            parts = re.split(r'\n===\n', out.strip())
            if len(parts) != len(texts):
                raise ValueError(f"фрагментов {len(parts)} != {len(texts)}")
            return [p.strip() for p in parts]
        except Exception as e:
            if attempt == 0:
                import time as _t
                _t.sleep(3)
                continue
            print(f"[llm] редактура не выполнена ({e}); остался правиловый polish_text")
            return texts
    return texts


def llm_polish_org_cells(doc, sections):
    """Прогнать заполненные ячейки ОРГАНОВ ВЛАСТИ через LLM (один пакет).
    Возвращает список описаний правок для отчёта."""
    if not llm_available():
        return []
    table = doc.tables[0]
    body = sections['ОРГАНЫ ВЛАСТИ']['body']
    cells, texts = [], []
    for ri in body:
        for ci in range(7):
            cell = table.cell(ri, ci)
            lines = [l for l in cell.text.split('\n') if l.strip()]
            fmt = []
            while lines and lines[-1].strip().lower() in (
                    'пресс-релиз', 'соцсети', 'тв', 'радио', 'интернет сми'):
                fmt.insert(0, lines.pop())
            content = '\n'.join(lines).strip()
            if content:
                cells.append((cell, content, fmt))
                texts.append(content)
    if not texts:
        return []
    fixed = llm_polish_texts(texts)
    changes = []
    for (cell, old, fmt), new in zip(cells, fixed):
        if new and new.strip() != old.strip():
            if not re.match(r'^[А-ЯЁ]{2,}', new) \
                    or len(new) < len(old) * 0.5 or len(new) > len(old) * 2.0:
                changes.append(f"  ? LLM-ответ отклонён (структура): {old[:50]}...")
                continue
            lines = new.split('\n') + fmt
            clear_cell(cell)
            p = cell.add_paragraph()
            add_lines(p, lines, size=10)
            changes.append(f"  ✎ LLM: {old[:40]}... → {new[:40]}...")
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['prep', 'fill', 'sync'])
    ap.add_argument('--monday', required=True, help='YYYY-MM-DD понедельник недели')
    ap.add_argument('--src', help='исходный docx (для prep можно опустить — скачает шаблон)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--state', help='json-файл снапшота')
    ap.add_argument('--keep-spec', action='store_true', help='не очищать СПЕЦПРОЕКТЫ')
    args = ap.parse_args()
    {'prep': cmd_prep, 'fill': cmd_fill, 'sync': cmd_sync}[args.mode](args)


if __name__ == '__main__':
    main()
