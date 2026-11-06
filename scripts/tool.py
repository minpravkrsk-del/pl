# -*- coding: utf-8 -*-
"""
Инструмент автообновления недельной формы (v7.28).

v7.28 (06.11.2026): форматы — судит ИИ, правила-угадайки убраны. По требованию
  пользователя: «программа „X“» (с уточнением ТВ/радио или без), «статья в…»,
  «интервью … для …» — содержание события, а НЕ формат; в форматы ничего не
  пишем. Удалён инференс broadcast_formats («программа» → ТВ), из
  normalize_formats убраны эфир/съемка/репортаж/сюжет, «интервью», «статья»
  и дефолт «пресс-релиз, соцсети» при пустом описании. FORMATS_PROMPT
  переписан: только стандартные форматы, явно названные как форматы;
  названия СМИ/каналов тоже не форматы; если форматов нет — ответ «НЕТ»
  (парсер возвращает [] и ОЧИЩАЕТ правиловые форматы события). Правила
  остаются только фолбэком при сбое ИИ-запроса.

v7.25 (06.11.2026): новая схема ИИ-текста — один запрос на событие по промту
  «1) сократи, сохранив факты; 2) сравни с заголовком; 3) убери повторы».
  Перезапросы, правиловый фолбэк, стоп-листы штампов и проверка новизны убраны.
  Осталось: отсечка предложений-повторов (пересказ: доля слов предложения,
  покрытие заголовка, дословное вхождение заголовка), пустышек вида
  «Мероприятие.», проверка чисел против источника (чужое число — предложение
  опускается), лимит 350 знаков; при сбое запроса — ячейка из одного заголовка.
  Путь без ИИ-ключа прежний (заголовок + полное описание).

v7.27 (06.11.2026): промт переведён на единый стандарт ячейки по требованию
  пользователя («всякое разноформатное по смыслу и объёму приводить к понятному
  краткому виду»): 1–2 предложения до ~200 знаков, перечисления сворачиваются
  («в пяти муниципальных округах края»), даты недели опускаются, будущие даты и
  цифры/суммы/названия в кавычках сохраняются, зачин не с пересказа заголовка.
  Лимит 350 знаков остаётся страховкой. Пример «Нордраме» сохранён.

v7.26 (06.11.2026): промт усилен по итогам боевого fill — модель слишком широко
  применяла шаг 3 (выкидывала новые факты той же темы: «Театр вечной теплоты»)
  и отвечала пустотой при богатых описаниях (ТРУД-нацпроект, медики ККБ).
  Добавлены: правило сохранять имена/должности/цифры/даты/названия в кавычках,
  запрет отвечать пустотой при наличии фактов и few-shot пример «Нордраме - 85!».
  Страховка: срезание префикса «Верный ответ:»/«Ответ:» в начале ответа.

v7.25a (06.11.2026): фикс падения fill — при вырезке блока потерялись
  FORMATS_PROMPT, _parse_llm_formats, _fmt_canon и FMT_CANON (нужны
  _formats_one); зависимости вырезанного блока восстанавливаются автоматически.

v7.7 (06.11.2026): слитный текст события — заголовок и краткое продолжение
  склеиваются в один абзац; продолжение строится и для обновлённых событий в sync.
v7.23 (06.11.2026): по логу fill v7.22: только 6 из 28 событий получили текст —
  проверка новизны браковала «штатный PR-язык» (приняли участие, состоялось,
  представили результаты) как выдумку. Фикс: 1) GENERIC_STEMS — стоп-лист общих
  глаголов-штампов и служебных слов: они не считаются выдумкой (реальные факты —
  «тонны», «выбросов», «диагностика» — по-прежнему бракуются); 2) порог пересказа
  пересказ теперь меряется долей слов САМОГО продолжения, которые лишь повторяют
  заголовок (>=50%) — «министр культуры снова побывал на севере» ловится, а
  «министр посетил Норильск и Дудинку» (новая фактура) — не считается пересказом.
  v7.21 (06.11.2026): подсказка ИИ усилена: продолжение обязано СОХРАНЯТЬ даты,
  цифры и конкретику описания (кто, где, когда, сколько) — выкидывать можно только
  «воду» и пересказ заголовка. Причина: ИИ вместе с пересказом выкидывал ценное
  (Анонс Дня урожая потерял «2–3 декабря», МИНФИН — место, Поставка — 6/4/1).
  v7.20 (06.11.2026): 1) РАЗГАДКА «Посты в.» — clean_desc из описания «релиз, посты в
  соцсети» вычищал «релиз» и «соцсети», но не «посты» (регэксп на единственное число)
  — огрызок «посты в» попадал в ячейку. Фикс: результат clean_desc прогоняется через
  обрезку незавершённого хвоста (_trim_dangling_tail) — огрызок исчезает в корне;
  2) форматы ИИ не ЗАМЕНЯЮТ правиловые, а ДОПОЛНЯЮТ: до fill терялись «СМИ»/«соцсети»/
  «пресс-релиз» из описаний (МИНЭК, МИНФИН, МИНСЕЛЬХОЗ, МИНЭКОЛОГИИ) — теперь объединение
  правиловых + ИИ-форматов без дублей.
  v7.19 (06.11.2026): обрубки неполного ответа ИИ («Посты в.») — детектор
  незавершённого хвоста: последняя фраза, обрывающаяся на служебном слове,
  вырезается целиком (в т.ч. с добавленной точкой); пустое продолжение ->
  ячейка из одной строки заголовка. Точка добавляется ПОСЛЕ обрезки.
  v7.18 (06.11.2026): целостность ДАТ при пересказе: месяц+числа проверяются ПАРОЙ
  и ТОЧНО — диапазон («с 9 по 11 ноября», «2–3 декабря») либо воспроизводится
  целиком, либо продолжение уходит на перезапрос, при повторе — на правила
  (полное описание с дословными датами). Выдуманный месяц в продолжении тоже
  ловится. Цифры (без месяца) как и раньше: каждая цифра обязана быть в источнике.
  v7.17 (06.11.2026): 1) форматы освещения — КАЖДЫЙ С НОВОЙ СТРОКИ
  (в ячейках органов власти и губернатора); 2) страховка «ничего не придумывать»:
  продолжение может опираться только на слова заголовка и описания — при двух
  и более значимых словах вне источника перезапрос, при повторе — без продолжения.
  v7.16 (06.11.2026): исправлена коллизия имён TYPO_FIXES — словарь правки
  опечаток переименован в TITLE_TYPO_FIXES (canon_org использует исходный
  список пар; после v7.13 fill падал на canon_org с ValueError).
  v7.15 (06.11.2026): отказ модели («Я не могу обсуждать эту тему») теперь НЕ теряет
  описание, а переводит событие на правиловый путь — полное описание пишется
  обычным кодом, как при любом сбое ИИ. v7.14 (06.11.2026, итоговая после ревизии
  ВСЕХ ячеек формы 09.11):
  1) отказы модели («Я не могу обсуждать эту тему» — было в двух ячейках!) —
  распознаются и отбрасываются, ячейка = заголовок + форматы;
  2) пересказ заголовка: вместо выброса всего продолжения — ОДИН перезапрос
  с черновиком и инструкцией «только новое», повторный пересказ = без продолжения;
  3) TYPO_FIXES расширен (прдвели->подвели, обструкци->обструкции,
  «поведение итогов»->«подведение итогов»), замена по границам слов;
  4) в polish_text: прямые кавычки -> ёлочки, «??»->«?», «!!»->«!»,
  автозакрытие незакрытой « перед знаком препинания. v7.13 (06.11.2026): 1) автоотсечка пересказа заголовка учитывает словоформы:
  сравнение по 5-буквенным основам («министр/министра», «депутами/депутатами» —
  теперь это одно слово; кейс МИНЭКОЛОГИИ «Поездка министра...» отсекается);
  2) TYPO_FIXES в polish_text: известные опечатки заголовков из календаря
  исправляются при записи («депутами»→«депутатами»); sync-сопоставление
  устойчиво (порог 60% слов). v7.12 (06.11.2026): борьба с дублированием «заголовок + продолжение»:
  1) в подсказке продолжения запрещено повторять перечисления организаций,
  даты, имена из заголовка — упоминать их один раз; пересказ заголовка другими
  словами = ПУСТО; 2) автоотсечка: если продолжение повторяет >=50% значимых
  слов заголовка — продолжение отбрасывается (ячейка = заголовок + форматы).
  v7.11 (06.11.2026): 1) ИИ-подсказка форматов ужесточена — только форматы и названия
  СМИ/каналов, прямо указанные в тексте; названия передач/программ/мероприятий
  запрещены («программа „Наше здоровье“» в форматах); 2) парсер форматов отсекает
  токены с кавычками и длиннее двух слов; 3) между текстом и форматами — пустая
  строка (отдельный абзац) в орг- и губ-ячейках. v7.10 (06.11.2026): два коротких запроса на событие (продолжение отдельно — схема
  v7.7, работала 17/17; форматы отдельно) — yandexgpt-lite не умеет в структурированный
  ответ из двух полей («нет строки ПРОДОЛЖЕНИЕ» на всех 27 событиях в v7.9);
  текст ячейки пишется ОТДЕЛЬНЫМИ АБЗАЦАМИ (переносы внутри абзаца схлопываются
  в редакторе пользователя — «края.пресс-релиз»). v7.9 (06.11.2026): форматы освещения — ОТДЕЛЬНОЙ строкой под текстом (не в хвосте);
  ИИ снова пишет только ПРОДОЛЖЕНИЕ (yandexgpt-lite пересказывал заголовок и проваливал
  валидацию 26/27 событий в v7.8), плюс тем же запросом возвращает форматы; при отказе
  ИИ в лог печатается причина. v7.8 (06.11.2026): слитная ячейка с форматами через пробел; форматы от ИИ
  (медианазвания «8 канал», «дела.ру» — как отдельные пункты); полировка ячеек удалена.
v7.6 (06.11.2026): полировка ячеек с маркером «участия Губернатора» и
  нацпроектными строками — спецстроки вырезаются перед ИИ и восстанавливаются
  при записи (раньше такие ячейки всегда отклонялись защитой).
v7.4 (05.11.2026): ИИ-краткие смыслы орг-событий (YC_API_KEY), полировка губернаторских
ячеек через ИИ, распознавание теле/радио-выходов без указанных форматов, чистка
дублей форматов из описаний.
v7.3 (05.11.2026): события губернатора — из заголовка убираются имена помощников
(«Люда - …», «Андрей, Люда - …»); из описания берутся ТОЛЬКО форматы освещения,
остальное описание (имидж, смыслы, вопросы) не импортируется; если форматы в
описании не указаны — дефолт соцсети, пресс-релиз, СМИ.

v7.2 (05.11.2026): фикс падения fill при событиях губернатора, если строк в разделе
ГУБЕРНАТОР меньше 7 (IndexError body[day]); подписи ячеек (sig) теперь считаются
по реальной ячейке события (ранг внутри дня), а не по body[day] — sync больше не
показывает ложное «не тронуто».

Режимы:
  prep  — очистить заполненные ячейки между разделами, обновить даты недели.
  fill  — заполнить ОРГАНЫ ВЛАСТИ из основного календаря и ГУБЕРНАТОР
          из календаря «График ММК» (ссылка экспорта, без авторизации),
          сохранить снапшот.
  sync  — сверка с обоими календарями: добавить новые, удалить пропавшие;
          ручные правки не перезаписывает.

Примеры:
  python tool.py prep --monday 2026-10-19 --out form.docx
  python tool.py fill --monday 2026-10-19 --src form.docx --out form_filled.docx --state state.json
  python tool.py sync --monday 2026-10-19 --src form_filled.docx --out form_synced.docx --state state.json
"""
import sys, os, re, json, base64, argparse, difflib, urllib.request, urllib.parse
from datetime import datetime, timedelta
from copy import deepcopy

CAL_TOKEN = os.environ.get("CAL_TOKEN", "").strip()
if not CAL_TOKEN:
    sys.exit("CAL_TOKEN not set")

CALENDAR_URL = ("https://calendar.yandex.ru/export/html.xml"
                f"?private_token={CAL_TOKEN}"
                "&tz_id=Asia/Krasnoyarsk&limit=300")

# календарь графика губернатора: ссылка экспорта/подписки (без авторизации).
# Не задан — раздел ГУБЕРНАТОР не трогаем.
GOV_CAL_URL = os.environ.get("GOV_CAL_URL", "").strip()

# форма: публичная ссылка на папку + имя файла внутри (только из переменных окружения)
FOLDER_PUBLIC_URL = os.environ.get("FORM_URL", "").strip()
FORM_NAME_IN_FOLDER = os.environ.get("FORM_NAME", "").strip()
TEMPLATE_PUBLIC_URL = os.environ.get("FORM_URL_FALLBACK", "").strip()

MONTHS = {1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
          7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'}

# ------------------------------------------------------------------ органы ---
ORDER = ['МИНЗДРАВ', 'МИНОБР', 'МИНСТРОЙ', 'МСП', 'МИНФИН', 'МИНЭК', 'МИНТРАНС',
         'ТУРИЗМ', 'МИНСЕЛЬХОЗ', 'МИНЦИФРЫ', 'ТРУД И ЗАНЯТОСТЬ', 'МИНСОЦ',
         'МИНКУЛЬТ', 'КМНС', 'МИНСПОРТ', 'МОЛОДЕЖКА', 'МИНЭКОЛОГИИ',
         'МИНПРИРОДЫ', 'МИНПРОМ', 'МИНТАРИФ']


def _root(canon):
    w = canon[3:].lower()
    return w[:-1] if w and w[-1] in 'аеёиоуыэюя' else w


MIN_ROOTS = sorted(
    {(_root(c), c) for c in ORDER if c.startswith('МИН') and len(c) > 3},
    key=lambda x: -len(x[0]))

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


TYPO_FIXES = [
    (r'на приме\s*-', 'на приёме —'),
    (r'\(\s*уточняется', '(уточняется'),
    (r'пресс-рели\b', 'пресс-релиз'),
    (r'пресс-срелиз', 'пресс-релиз'),
]

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
GOV_MARKER = os.environ.get("GOV_MARKER", "").strip()


# --------------------------------------------------------------- календарь ---
def fetch_calendar():
    req = urllib.request.Request(CALENDAR_URL, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=60).read().decode('utf-8')


def fetch_gov_calendar():
    """Скачать календарь губернатора по ссылке экспорта (без авторизации).
    Ссылка может быть webcal:// — переводим в https://."""
    url = GOV_CAL_URL
    if url.lower().startswith('webcal://'):
        url = 'https://' + url[len('webcal://'):]
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'replace')


def parse_gov_calendar(text):
    """Определить формат выгрузки (iCal или HTML Яндекс Календаря)
    и вернуть события [{title, desc, start(Datetime)}]."""
    if 'BEGIN:VCALENDAR' in text.upper():
        return parse_ics(text)
    events = []
    for ev in parse_calendar(text):
        if not ev['times']:
            continue
        start = parse_cal_date(ev['times'][0])
        if not start:
            continue
        events.append({'title': ev['title'], 'desc': ev['desc'], 'start': start})
    return events


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
        month = MONTH_IDX.get(m.group(2), 0)
        if not month:
            return None
        return datetime(int(m.group(3)), month,
                        int(m.group(1)), int(m.group(4)), int(m.group(5)))
    # событие на весь день: "26 октября 2026" или "26 октября"
    m = re.search(r'(\d+)\s+([а-яё]+)(?:\s+(\d{4}))?\s*$', s.strip())
    if m:
        month = MONTH_IDX.get(m.group(2), 0)
        if not month:
            return None
        year = int(m.group(3)) if m.group(3) else datetime.now().year
        return datetime(year, month, int(m.group(1)))
    return None


# --------------------------------------------------------------- ICS (ММК) ---
def _ics_unfold(text):
    return re.sub(r'\n[ \t]', '', text.replace('\r\n', '\n'))


def _ics_unesc(s):
    return (s.replace('\\n', '\n').replace('\\N', '\n')
             .replace('\\,', ',').replace('\\;', ';').replace('\\\\', '\\'))


def parse_ics(text):
    text = _ics_unfold(text)
    events = []
    for block in re.split(r'BEGIN:VEVENT', text)[1:]:
        block = block.split('END:VEVENT')[0]
        if re.search(r'^STATUS\s*:\s*CANCELLED', block, flags=re.M | re.I):
            continue

        def prop(name):
            m = re.search(rf'^{name}[^:\n]*:(.*)$', block, flags=re.M)
            return _ics_unesc(m.group(1).strip()) if m else ''

        summary = prop('SUMMARY')
        ds = re.search(r'^DTSTART[^:\n]*:(\S+)', block, flags=re.M)
        if not ds or not summary:
            continue
        v = ds.group(1)
        try:
            if len(v) == 8:  # событие на весь день
                start = datetime(int(v[:4]), int(v[4:6]), int(v[6:8]))
            elif v.endswith('Z'):
                start = datetime.strptime(v, '%Y%m%dT%H%M%SZ') + timedelta(hours=7)
            else:
                start = datetime.strptime(v, '%Y%m%dT%H%M%S')
        except ValueError:
            continue
        events.append({'title': summary.strip(), 'desc': prop('DESCRIPTION'), 'start': start})
    return events


# ------------------------------------------------------------------- органы ---
def match_org(h):
    if not h:
        return None, 0
    for key, canon in AGENCY_RULES:
        if h == key or h.startswith(key + ' ') or h.startswith(key + '.'):
            return canon, len(key)
    parts = h.split(' ', 1)
    w0, tail = parts[0], (parts[1] if len(parts) > 1 else '')
    if w0 == 'мин' and tail:
        for root, canon in MIN_ROOTS:
            if tail.startswith(root):
                return canon, len(w0) + 1 + len(tail.split(' ')[0])
        return None, 0
    if w0.startswith('мин') and len(w0) > 3:
        body = w0[3:]
        for root, canon in MIN_ROOTS:
            if body.startswith(root):
                return canon, len(w0)
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
    t = title.strip().lstrip('?').lstrip('!').strip()
    m = re.match(r'^([^:]{1,80}?)[.:]\s+', t + ' ')
    header = (m.group(1) if m else t.split(':')[0]).strip()
    h = re.sub(r'\s+', ' ', header.lower().replace('ё', 'е'))
    canon, cut = match_org(h)
    if canon:
        rest = t[cut:].lstrip(' :.·–—-').strip()
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
    """Форматы, ЯВНО указанные в описании (v7.28). Только стандартные форматы;
    упоминания «в программе …», «эфир», «интервью для …», «статья в …» —
    это содержание события, а не форматы — в форматы ничего не пишем.
    Возврат может быть пустым списком: форматов нет — так и пишем."""
    d = (desc or '').lower().replace('ё', 'е')
    fmt = []
    if re.search(r'пресс-релиз|пресс релиз|\bрелиз', d):
        fmt.append('пресс-релиз')
    if re.search(r'соцсет|соц сет|соцсеть|\bпост\b|пост,', d):
        fmt.append('соцсети')
    if re.search(r'\bтв\b|\btv\b|\bтв-|телевидени|телеканал', d):
        fmt.append('ТВ')
    if re.search(r'\bрадио\b', d):
        fmt.append('радио')
    if re.search(r'интернет-сми|сетевое издание|\bна сайте\b|\bна портале\b|\bсайт\b', d):
        fmt.append('интернет СМИ')
    if re.search(r'\bсми\b', d):
        fmt.append('СМИ')
    return fmt


def find_natproj(text):
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


_FMT_ALT = (r'пресс-релизы?|релизы?|соцсети|соц\.\s*сетях|социальных\s+сетях|сми|тв|радио|'
            r'сюжеты?|посты?(?:\s*в\s*соц(?:иальный|иальных|\.?\s*сетях|сетях))?')
EXT_FMT = r'\b(?:%s)\b' % _FMT_ALT


def strip_format_segments(text):
    """Убрать из текста упоминания форматов освещения (дубль блока форматов):
    отдельные строки «Формат: …», завершающие скобки «(релиз + соцсети)» и
    хвостовые перечисления форматов после точки/строки-разделителя."""
    t = text
    t = re.sub(r'(?m)^\s*Формат(?:ы)?(?:\s*освещения)?\s*[:\-]?\s*[^\n]{0,160}\s*[.?!]?\s*$',
               ' ', t, flags=re.I)
    t = re.sub(r'(?<=[.;!?])\s*Формат(?:ы)?(?:\s*освещения)?\s*[:\-]?\s*[^.\n]{0,160}\s*\.?\s*$',
               ' ', t, flags=re.I)
    t = re.sub(r'\s*\((?:[^()]*(?:%s)[^()]*)\)\s*\.?\s*$' % EXT_FMT, ' ', t, flags=re.I)
    t = re.sub(r'(?<=[.;!?])\s*(?:%s)(?:[\s,+/и]*%s)*\s*[.?!]?\s*$' % (EXT_FMT, EXT_FMT),
               ' ', t, flags=re.I)
    return t.strip()


def clean_desc(desc):
    if not desc:
        return ''
    lines = [l for l in (x.strip() for x in desc.split('\n')) if l]
    kept = [l for l in lines if not line_is_format_only(l)]
    out = '\n'.join(kept)
    out = re.sub(
        r'[,.;:\s]*\b(?:пресс-релиз|релиз|соцсети|соц\.\s*сети|пост|тв|сми|радио)\b'
        r'(?:\s+(?:министра|главы|руководителя|замминстра|замминстра|губернатора))?'
        r'(?:[,.;:\s]+\b(?:пресс-релиз|релиз|соцсети|соц\.\s*сети|пост|тв|сми|радио)\b'
        r'(?:\s+(?:министра|главы|руководителя|замминстра|замминстра|губернатора))?)*[.,]?\s*',
        ' ', out, flags=re.I)
    out = out.strip()
    out = strip_format_segments(out)
    for a, b in TYPO_FIXES:
        out = re.sub(a, b, out, flags=re.I)
    return _trim_dangling_tail(re.sub(r'\s+', ' ', out).strip())

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
    for i, ln in enumerate(lines):
        r = paragraph.add_run(ln)
        set_run(r, size=size)
        if i < len(lines) - 1:
            r.add_break()


TITLE_TYPO_FIXES = {
    'депутами': 'депутатами',
    'прдвели': 'подвели',
    'обструкци': 'обструкции',
    'поведение итогов': 'подведение итогов',
}


def polish_text(text):
    if not text or not text.strip():
        return text
    t = re.sub(r'[ \t]+', ' ', text.strip())
    for bad, good in TITLE_TYPO_FIXES.items():
        pat = r'\b' + re.escape(bad) + r'\b'
        if re.search(pat, t, flags=re.I):
            t = re.sub(pat, good, t, flags=re.I)
    # прямые кавычки -> ёлочки; повторные знаки -> одинарные
    t = re.sub(r'"([^"]*)"', r'«\1»', t)
    t = re.sub(r'\?{2,}', '?', t)
    t = re.sub(r'!{2,}', '!', t)
    # незакрытая «: закрыть перед конечным знаком препинания
    if t.count('«') > t.count('»'):
        if t[-1] in '.,;:!?…':
            t = t[:-1] + '»' + t[-1]
        else:
            t += '»' 
    t = re.sub(r'\s+([.,;:!?])', r'\1', t)
    t = re.sub(r'([а-яёa-z][,;:.!?])(?=[а-яёА-ЯЁA-Z])', r'\1 ', t)
    m = re.match(r'^([А-ЯЁ]{2,}(?: [А-ЯЁ]{2,})?):\s*(.*)$', t, flags=re.S)
    if m and m.group(2):
        head, rest = m.group(1), m.group(2)
        rest = rest[0].upper() + rest[1:]
        t = f"{head}: {rest}"
    elif t and t[0].isalpha() and t[0].islower():
        t = t[0].upper() + t[1:]
    if t and t[-1] not in '.!?…»)"]':
        t += '.'
    return t


def write_event(cell, ev):
    """Событие в ячейку ОРГАНОВ ВЛАСТИ."""
    clear_cell(cell)
    if ev.get('gov_marker') and GOV_MARKER:
        p = cell.add_paragraph()
        r = p.add_run(GOV_MARKER)
        set_run(r, 10, bold=True)
        cell.add_paragraph()
    if ev.get('nats'):
        for n in ev['nats']:
            p = cell.add_paragraph()
            r = p.add_run(n)
            set_run(r, 10, bold=True)
        cell.add_paragraph()
    p = cell.add_paragraph()
    body = polish_text(ev['title'])
    cont = (ev['llm_cont'] or '').strip() if 'llm_cont' in ev else None
    if cont is not None:
        if cont:
            body = f"{body} {cont}"
    else:
        desc = (ev.get('desc') or '').strip()
        if desc:
            body = f"{body} {polish_text(desc)}"
    fmts = [f for f in (ev.get('formats') or []) if f]
    p.text = ''  # абзац создан выше — используем его для строки текста
    r = p.add_run(f"{ev['canon']}: {body}")
    set_run(r, 10)
    if fmts:
        cell.add_paragraph()  # пустая строка — визуальный зазор перед форматами
        for f in fmts:  # каждый формат — с новой строки
            fp = cell.add_paragraph()
            r = fp.add_run(f)
            set_run(r, 10)


def write_event_gov(cell, ev):
    """Событие графика губернатора в ячейку ГУБЕРНАТОР: название, описание,
    форматы (по умолчанию соцсети, пресс-релиз, СМИ)."""
    clear_cell(cell)
    body = polish_text(ev['title'])
    desc = (ev.get('desc') or '').strip()
    if desc:
        body = f"{body} {polish_text(desc)}"
    fmts = [polish_text(f) if not re.fullmatch(r'[А-ЯЁа-яё /\-]+', f) else f
            for f in ev.get('formats', []) if f]
    p = cell.add_paragraph()
    r = p.add_run(body)
    set_run(r, 10)
    if fmts:
        cell.add_paragraph()  # пустая строка — визуальный зазор перед форматами
        for f in fmts:  # каждый формат — с новой строки
            fp = cell.add_paragraph()
            r = fp.add_run(f)
            set_run(r, 10)


def cell_text_norm(cell):
    return re.sub(r'\s+', ' ', cell.text).strip().lower()


def title_norm(t):
    return re.sub(r'\s+', ' ', (t or '')).strip().lower()


def cell_contains_title(cell, title):
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
# v7.28: инференс форматов из упоминаний программ/эфиров (broadcast_formats)
# удалён — «в программе „X“…», «эфир», «интервью для…» — это содержание события,
# а не формат. Судит ИИ (FORMATS_PROMPT), правила — только явные форматы.


def collect_week_events(monday):
    """События недели основного календаря (раздел ОРГАНЫ ВЛАСТИ)."""
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
        gov_hit = is_governor(text_all)
        if gov_hit and canon not in ORDER:
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
            'gov_marker': bool(gov_hit and GOV_MARKER),
        })
    seen = set()
    dedup = []
    for e in week:
        key = (e['day'], e['canon'], title_norm(e['title']), e['start'])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(e)
    return dedup, skipped_gov, len(events)


GOV_NAMES = {'андрей', 'люда', 'лилия', 'лиля', 'даша', 'катя', 'власта', 'влада'}


def strip_gov_names(title):
    """Убрать из заголовка события графика имена помощников:
    "Люда - Вручение наград" -> "Вручение наград",
    "Андрей, Люда - Президиум" -> "Президиум". Остальные заголовки не трогаем."""
    t = (title or '').strip()
    m = re.match(r'^([^—\u2013-]{1,60}?)[—\u2013-]\s*(.+)$', t)
    if not m:
        return t
    head = re.sub(r'[,;]', ' и ', m.group(1).strip().lower().replace('ё', 'е'))
    toks = [x.strip() for x in head.split(' и ') if x.strip()]
    if toks and all(x in GOV_NAMES for x in toks):
        return m.group(2).strip()
    return t


def gov_format_lines(desc):
    """Вернуть из описания события только строки с форматами освещения.
    Строка считается строкой форматов, если: (а) целиком состоит из токенов
    форматов, либо (б) начинается с токена формата. Уточнения в скобках
    («пост (видео)») и добавки («сюжет на Енисей») допускаются."""
    if not desc:
        return ''
    kept = []
    for raw in desc.split('\n'):
        line = raw.strip()
        if not line:
            continue
        s = line.lower().replace('ё', 'е')
        core = re.sub(r'\([^)]*\)', ' ', s)
        words = [w for w in re.sub(r'[«»"“”\'.,;:!()\-\u2013\u2014\s]+', ' ', core).split() if w]
        if not words:
            continue
        has_fmt = re.search(r'пресс-релиз|релиз|соцсет|пост|тв|сми|радио|сюжет|эфир'
                            r'|интервью|статьи|телеканал|съемка', core)
        if line_is_format_only(line) or (has_fmt and words[0] in FMT_TOKENS
                                         and words[0] not in ('и', 'а')):
            kept.append(line)
    return '\n'.join(kept)


def gov_formats(desc):
    """Форматы для мероприятий губернатора: если в описании форматы указаны —
    берём их (normalize_formats), иначе по умолчанию: соцсети, пресс-релиз, СМИ."""
    lines = gov_format_lines(desc)
    if not lines:
        return ['соцсети', 'пресс-релиз', 'СМИ']
    return normalize_formats(lines)


def collect_gov_week_events(monday):
    """События недели календаря губернатора. Возвращает (события, всего, настроен ли)."""
    if not GOV_CAL_URL:
        return [], 0, False
    events = parse_gov_calendar(fetch_gov_calendar())
    target_start = datetime(monday.year, monday.month, monday.day)
    target_end = target_start + timedelta(days=7)
    week = []
    for ev in events:
        s = ev['start']
        if not (target_start <= s < target_end):
            continue
        week.append({
            'day': (s - target_start).days,
            'canon': 'ГУБЕРНАТОР',
            'title': strip_gov_names(ev['title']),
            'desc': '',
            'start': s.strftime('%Y-%m-%d %H:%M'),
            'formats': gov_formats(ev['desc']),
        })
    seen, dedup = set(), []
    for e in week:
        key = (e['day'], title_norm(e['title']), e['start'])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(e)
    return dedup, len(events), True


def cmd_prep(args):
    if not args.src:
        n = fetch_template('/tmp/_template.docx')
        args.src = '/tmp/_template.docx'
        print(f"Шаблон скачан с Диска: {n} байт")
    doc = Document(args.src)
    table = doc.tables[0]
    sections = find_sections(table)
    monday = datetime.strptime(args.monday, '%Y-%m-%d').date()
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


def ensure_section_rows(table, sections, name, needed):
    """Довести число строк раздела до max(needed): новые строки вставляются
    сразу ПОСЛЕ последней строки раздела (не в конец таблицы)."""
    body = sections[name]['body']
    max_len = max(needed) if needed else 1
    if max_len > len(body):
        anchor = table.rows[body[-1]]._tr
        for _ in range(max_len - len(body)):
            new_tr = deepcopy(anchor)
            anchor.addnext(new_tr)
            anchor = new_tr
        fresh = find_sections(table)[name]['body'][len(body):]
        for ri in fresh:
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
    monday = datetime.strptime(args.monday, '%Y-%m-%d').date()

    org_filled = sum(1 for ri in sections['ОРГАНЫ ВЛАСТИ']['body'] for ci in range(7)
                     if table.cell(ri, ci).text.strip())
    gov_filled = sum(1 for ri in sections['ГУБЕРНАТОР']['body'] for ci in range(7)
                     if table.cell(ri, ci).text.strip())
    if org_filled or gov_filled:
        print(f"[fill] ОТМЕНА: есть заполненные ячейки (ОРГАНЫ ВЛАСТИ: {org_filled}, "
              f"ГУБЕРНАТОР: {gov_filled}). Это либо ручное заполнение, либо не выполнялся prep. "
              "Ручное не трогаю; если это остатки прошлой недели — сначала запустите prep.")
        sys.exit(3)

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
    n_sum = llm_org_polish(events)
    if llm_available():
        print(f"[llm] тексты и форматы: {n_sum} из {len(events)} событий недели")
    per_day = {}
    for e in events:
        per_day.setdefault(e['day'], []).append(e)
    for d in per_day:
        per_day[d].sort(key=lambda x: (order_index(x['canon']), x['start']))
    needed = [len(per_day.get(d, [])) for d in range(7)]
    sections = ensure_section_rows(table, sections, 'ОРГАНЫ ВЛАСТИ', needed)
    org_body = sections['ОРГАНЫ ВЛАСТИ']['body']

    snapshot = []
    for d in range(7):
        for k, ev in enumerate(per_day.get(d, [])):
            cell = table.cell(org_body[k], d)
            write_event(cell, ev)
            snapshot.append({
                'sec': 'org', 'day': d, 'k': k, 'canon': ev['canon'], 'title': ev['title'],
                'start': ev['start'], 'gov_marker': ev.get('gov_marker', False),
                'sig': None,
            })

    # --- календарь губернатора (График ММК) ---
    gov_body = sections['ГУБЕРНАТОР']['body']
    gov_events, gov_total, gov_ok = [], 0, False
    try:
        gov_events, gov_total, gov_ok = collect_gov_week_events(monday)
    except Exception as e:
        print(f"[fill] ГУБЕРНАТОР: календарь недоступен ({e}) — раздел не заполнен")
    if gov_ok:
        g_per_day = {}
        for e in gov_events:
            g_per_day.setdefault(e['day'], []).append(e)
        for d in g_per_day:
            g_per_day[d].sort(key=lambda x: x['start'])
        gneed = [len(g_per_day.get(d, [])) for d in range(7)]
        sections = ensure_section_rows(table, sections, 'ГУБЕРНАТОР', gneed)
        gov_body = sections['ГУБЕРНАТОР']['body']
        for d in range(7):
            for k, ev in enumerate(g_per_day.get(d, [])):
                cell = table.cell(gov_body[k], d)
                write_event_gov(cell, ev)
                snapshot.append({
                    'sec': 'gov', 'day': d, 'k': k, 'canon': 'ГУБЕРНАТОР', 'title': ev['title'],
                    'start': ev['start'], 'sig': None,
                })
        print(f"[fill] ГУБЕРНАТОР: событий в календаре всего {gov_total}, на неделю попало {len(gov_events)}")
        print("[fill] ГУБ по дням: " + ", ".join(
            f"{(monday + timedelta(days=d)).strftime('%d.%m')}={len(g_per_day.get(d, []))}" for d in range(7)))
    else:
        print("[fill] ГУБЕРНАТОР: календарь не настроен (секрет GOV_CAL_URL не задан) — пропускаю")

    # пересчитать индексы строк (вставки могли сдвинуть разделы)
    sections = find_sections(table)
    org_body = sections['ОРГАНЫ ВЛАСТИ']['body']
    gov_body = sections['ГУБЕРНАТОР']['body']

    # сигнатуры после вставок строк
    for s in snapshot:
        body = gov_body if s.get('sec') == 'gov' else org_body
        s['sig'] = cell_text_norm(table.cell(body[s['k']], s['day']))

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
    marked = [e for e in events if e.get('gov_marker')]
    if marked:
        print("[fill] Помечено участием (проверьте):")
        for e in marked:
            print(f"    {(monday + timedelta(days=e['day'])).strftime('%d.%m')} {e['canon']}: {e['title'][:70]}")
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
    gov_body = sections['ГУБЕРНАТОР']['body']

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
    try:
        gov_events, gov_total, gov_ok = collect_gov_week_events(monday)
    except Exception as e:
        print(f"[sync] ГУБЕРНАТОР: календарь недоступен ({e}) — этот раздел пропускаю")
        gov_events, gov_total, gov_ok = [], 0, False

    fresh = {}
    for e in events:
        fresh[(e['day'], 'org', e['canon'], title_norm(e['title']))] = e
    for e in gov_events:
        fresh[(e['day'], 'gov', 'ГУБЕРНАТОР', title_norm(e['title']))] = e
    snap = {}
    for s in state['events']:
        sec = s.get('sec', 'org')
        snap[(s['day'], sec, s['canon'], title_norm(s['title']))] = s

    def body_of(sec):
        return gov_body if sec == 'gov' else org_body

    # защита снапшота: если раздел пуст, а в снапшоте есть его события —
    # похоже, fill не выполнялся; синхронизацию отменяем
    org_filled = sum(1 for ri in org_body for ci in range(7)
                     if table.cell(ri, ci).text.strip())
    gov_filled = sum(1 for ri in gov_body for ci in range(7)
                     if table.cell(ri, ci).text.strip())
    snap_org = [s for s in state['events'] if s.get('sec', 'org') == 'org']
    snap_gov = [s for s in state['events'] if s.get('sec') == 'gov']
    if not org_filled and snap_org:
        print(f"[sync] ОТМЕНА: раздел ОРГАНЫ ВЛАСТИ пуст, а в снапшоте "
              f"{len(snap_org)} событий. Похоже, fill не выполнялся. Сначала fill.")
        sys.exit(3)
    if gov_ok and not gov_filled and snap_gov:
        print(f"[sync] ОТМЕНА: раздел ГУБЕРНАТОР пуст, а в снапшоте "
              f"{len(snap_gov)} событий. Похоже, fill не выполнялся. Сначала fill.")
        sys.exit(3)

    to_add, to_remove, changed = [], [], []

    fresh_by_slot = {}
    for k, e in fresh.items():
        fresh_by_slot.setdefault((k[0], k[1], k[2], e['start']), []).append(k)
    snap_by_slot = {}
    for k, s in snap.items():
        snap_by_slot.setdefault((k[0], k[1], k[2], s['start']), []).append(k)

    for k, e in fresh.items():
        if k in snap:
            continue
        slot = (k[0], k[1], k[2], e['start'])
        matched = None
        for sk in snap_by_slot.get(slot, []):
            matched = sk
            break
        if matched:
            changed.append((matched, e))
        else:
            to_add.append(k)

    for k, s in snap.items():
        if k in fresh:
            continue
        slot = (k[0], k[1], k[2], s['start'])
        if slot in fresh_by_slot:
            continue
        to_remove.append(k)

    report = []

    # --- удаление пропавших ---
    for k in to_remove:
        s = snap[k]
        day, sec = s['day'], s.get('sec', 'org')
        if sec == 'gov' and not gov_ok:
            continue  # календарь губернатора недоступен — не удаляем
        target = title_norm(s['title'])
        found = None
        for ri in body_of(sec):
            cell = table.cell(ri, day)
            ct = cell_text_norm(cell)
            if not ct:
                continue
            if ct == s.get('sig'):
                found = (ri, 'exact')
                break
            if target and (target in ct
                           or cell_contains_title(table.cell(ri, day), s['title'])):
                found = (ri, 'contains')
        if found:
            ri, how = found
            clear_cell(table.cell(ri, day))
            report.append(f"  УДАЛЕНО {day_names_l(monday)[day]} ({'ГУБ' if sec == 'gov' else 'ОРГ'}): "
                          f"{s['canon']}: {s['title'][:70]} [{how}]")
        else:
            report.append(f"  ! НЕ НАЙДЕНО для удаления {day_names_l(monday)[day]} "
                          f"({'ГУБ' if sec == 'gov' else 'ОРГ'}): {s['canon']}: {s['title'][:70]} — проверьте вручную")

    # --- перезапись изменившихся ---
    changed_org = [e for sk, e in changed if snap[sk].get('sec', 'org') == 'org']
    if changed_org:
        llm_org_polish(changed_org)
    for sk, e in changed:
        s = snap[sk]
        day, sec = s['day'], s.get('sec', 'org')
        rewritten = False
        for ri in body_of(sec):
            cell = table.cell(ri, day)
            ct = cell_text_norm(cell)
            if ct and ct == s.get('sig'):
                if sec == 'gov':
                    write_event_gov(cell, e)
                else:
                    write_event(cell, e)
                snap[sk] = dict(s, day=day, canon=e['canon'], title=e['title'],
                                start=e['start'], sig=cell_text_norm(cell))
                report.append(f"  ОБНОВЛЕНО {day_names_l(monday)[day]} ({'ГУБ' if sec == 'gov' else 'ОРГ'}): "
                              f"{e['canon']}: {e['title'][:60]}")
                rewritten = True
                break
        if not rewritten:
            report.append(f"  ! ИЗМЕНИЛОСЬ, но ячейка отредактирована вручную — не тронуто: "
                          f"{day_names_l(monday)[day]} {s['canon']}: {s['title'][:60]}")

    # --- добавление новых ---
    org_to_add = [fresh[k] for k in to_add if k[1] == 'org']
    llm_org_polish(org_to_add)
    for k in to_add:
        e = fresh[k]
        day, sec = k[0], k[1]
        body = body_of(sec)
        dup_row = None
        for ri in body:
            if cell_contains_title(table.cell(ri, day), e['title']):
                dup_row = ri
                break
        if dup_row is not None:
            report.append(f"  ? ПОХОЖЕ УЖЕ ЕСТЬ {day_names_l(monday)[day]} ({'ГУБ' if sec == 'gov' else 'ОРГ'}): "
                          f"{e['canon']}: {e['title'][:70]} — не добавлял, проверьте")
            continue
        while True:
            cells = [(ri, table.cell(ri, day)) for ri in body]
            empty = [(j, ri) for j, (ri, c) in enumerate(cells) if not c.text.strip()]
            if empty:
                break
            sections = ensure_section_rows(table, sections,
                                           'ГУБЕРНАТОР' if sec == 'gov' else 'ОРГАНЫ ВЛАСТИ',
                                           [len(body) + 1] * 7)
            org_body = sections['ОРГАНЫ ВЛАСТИ']['body']
            gov_body = sections['ГУБЕРНАТОР']['body']
            body = body_of(sec)
        chosen = None
        if sec == 'org':
            j0 = empty[0][1]
            for j, ri in empty:
                if j > 0 and canon_of_cell(cells[j - 1][1]) == e['canon']:
                    chosen = ri
                    break
            if chosen is None:
                chosen = j0
        else:
            chosen = empty[0][1]
        cell = table.cell(chosen, day)
        if sec == 'gov':
            write_event_gov(cell, e)
        else:
            write_event(cell, e)
        snap[k] = {
            'sec': sec, 'day': day, 'canon': e['canon'], 'title': e['title'],
            'start': e['start'], 'sig': cell_text_norm(cell)}
        report.append(f"  ДОБАВЛЕНО {day_names_l(monday)[day]} ({'ГУБ' if sec == 'gov' else 'ОРГ'}): "
                      f"{e['canon']}: {e['title'][:70]}")

    # --- сохранение ---
    state['events'] = list(snap.values())
    doc.save(args.out)
    with open(args.state, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)

    print(f"[sync] Календарь: всего {total}, на неделе {len(events)} (+{len(gov)} вне раздела)")
    if gov_ok:
        print(f"[sync] ГУБЕРНАТОР: всего {gov_total}, на неделе {len(gov_events)}")
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


def llm_call(prompt):
    """Один запрос к YandexGPT. Возвращает текст ответа или None при сбое."""
    body = json.dumps({
        "modelUri": f"gpt://{LLM_FOLDER_ID}/{LLM_MODEL}",
        "completionOptions": {"temperature": 0.1, "maxTokens": "8000"},
        "messages": [{"role": "user", "text": prompt}],
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        data=body,
        headers={"Authorization": "Api-Key " + LLM_API_KEY,
                 "Content-Type": "application/json"})
    import time as _t
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.load(r)
            return resp['result']['alternatives'][0]['message']['text']
        except Exception as e:
            if attempt == 0:
                _t.sleep(3)
                continue
            print(f"[llm] запрос не удался ({e})")
            return None
    return None


SHORTEN_PROMPT = (
    "Ты редактор официального недельного плана освещения событий органов власти.\n\n"
    "Текст:\n{TEXT}\n\n"
    "Заголовок:\n{TITLE}\n\n"
    "1. Сократи этот текст до одного-двух коротких предложений (примерно до "
    "200 знаков): о чём событие и главное по сути.\n"
    "2. Сравни свой текст с заголовком.\n"
    "3. Убери всё, что дословно или по смыслу повторяет заголовок, — но не "
    "выбрасывай новые факты, даже если тема совпадает.\n\n"
    "Правила:\n"
    "- Длинные перечисления (округа, города, организации, ведомства, участников) "
    "сворачивай в краткую форму: «в пяти муниципальных округах края», «в трёх "
    "городах», «с участием агробизнеса края и зарубежных партнёров».\n"
    "- Сохраняй ключевые цифры, суммы, объёмы и названия в кавычках — их нельзя "
    "убирать, даже если тема совпадает с заголовком.\n"
    "- Даты внутри текущей недели и дни недели опускай; даты будущих событий "
    "(когда состоится) и возрастные ограничения оставляй.\n"
    "- Не начинай с пересказа заголовка и полного титула — сразу к сути.\n"
    "- Если в тексте есть хоть один факт, пиши его — не отвечай пустотой.\n\n"
    "Пример.\n"
    "Заголовок: «Нордраме - 85!»\n"
    "Текст: Юбилейный вечер Норильского заполярного театра драмы в честь "
    "85-летия «Театр вечной теплоты».\n"
    "Верный ответ: Юбилейный вечер Норильского заполярного театра драмы в "
    "честь 85-летия «Театр вечной теплоты».\n"
    "(Название вечера в кавычках — новый факт, не повтор заголовка; слово «85» "
    "не повод убирать предложение.)\n\n"
    "Не упоминай форматы освещения (пресс-релиз, соцсети, ТВ, радио). "
    "Ответ — только итоговый текст, без кавычек, пояснений и разметки.")

SHORTEN_MAX_CHARS = 350

REFUSAL_RE = re.compile(
    r'не могу (обсуждать|обсудить|помочь|ответить|составить|написать)'
    r'|не имею возможности|поговорим о ч|не в моей компетенции|давайте поговорим', re.I)


FMT_CANON = {
    'пресс-релиз': 'пресс-релиз', 'пресс релиз': 'пресс-релиз', 'релиз': 'пресс-релиз',
    'соцсети': 'соцсети', 'соц сети': 'соцсети', 'соц. сети': 'соцсети',
    'социальные сети': 'соцсети', 'пост': 'соцсети',
    'тв': 'ТВ', 'телевидение': 'ТВ', 'телеканал': 'ТВ', 'сюжет': 'ТВ', 'эфир': 'ТВ',
    'радио': 'радио',
    'сми': 'СМИ',
    'интернет сми': 'интернет СМИ', 'интернет-сми': 'интернет СМИ',
    'сетевое издание': 'интернет СМИ', 'сайт': 'интернет СМИ', 'сайте': 'интернет СМИ',
    'на сайте': 'интернет СМИ', 'портал': 'интернет СМИ',
    'интервью': 'интервью',
    'статья': 'статья',
}


FORMATS_PROMPT = (
    "Определи, какие форматы освещения события ПРЯМО указаны в его заголовке и описании.\n"
    "Форматы освещения — только стандартные: пресс-релиз, соцсети, СМИ, ТВ, радио,\n"
    "интернет-СМИ (сайт, портал).\n"
    "Это НЕ форматы, их перечислять НЕЛЬЗЯ:\n"
    "- упоминания программ и передач («программа „Наше здоровье“», «телепроект»,\n"
    "  «прямой эфир») — даже с уточнением «на ТВ» или «на радио»;\n"
    "- статьи и публикации в изданиях («статья в „Красноярском рабочем“»);\n"
    "- интервью с указанием собеседника или издания («интервью главы агентства\n"
    "  радио „Комсомольская правда“»);\n"
    "- названия СМИ, каналов и изданий («8 канал», «радио Россия», «дела.ру»).\n"
    "Перечисляй форматы только если они названы в тексте как форматы освещения\n"
    "(например «пресс-релиз, соцсети», «(ТВ)», «освещение: СМИ, соцсети»).\n"
    "Если форматов в тексте нет — ответь ровно словом: НЕТ\n"
    "Ответ — только список форматов через запятую или НЕТ, без пояснений и разметки.")


def _fmt_canon(tok):
    t = re.sub(r'\s+', ' ', (tok or '').strip().strip('.,;:!«»"\'').strip())
    if not t:
        return None
    low = t.lower().replace('ё', 'е')
    return FMT_CANON.get(low, t)


def _parse_llm_formats(raw):
    """Разобрать список форматов из ответа ИИ. Список строк или None (сбой).
    «НЕТ» — форматов в тексте нет: пустой список (не сбой). Токены с кавычками
    и длиннее двух слов отсекаются — это названия передач и болтовня."""
    if not raw:
        return None
    low = re.sub(r'\s+', ' ', raw.strip().lower().replace('ё', 'е'))
    if re.match(r'^(?:форматов?\s*)?(?:освещени\w*\s*)?нет\b', low) and len(low.split()) <= 3:
        return []
    toks = [x for x in re.split(r'[;,]|\bи\b', raw.strip().strip('.?!'), flags=re.I) if x.strip()]
    fmts, seen = [], set()
    for t in toks:
        if re.search(r'[«»"]', t) or len(t.split()) > 2:
            continue
        c = _fmt_canon(t)
        if not c or len(c) > 40:
            return None
        k = c.lower().replace('ё', 'е')
        if k in seen:
            continue
        seen.add(k)
        fmts.append(c)
    return fmts[:8] if fmts else None

def _split_sentences(s):
    parts = re.split(r'(?<=[.!?…])\s+', s.strip())
    return [p.strip() for p in parts if p.strip()]


def _stems5(text):
    return {w[:5] for w in re.split(r'\W+', (text or '').lower().replace('ё', 'е')) if len(w) > 3}


def _norm_phrase(s):
    return re.sub(r'\s+', ' ', re.sub(r'[«»".,!?();:\-—–]+', ' ', (s or '').lower().replace('ё', 'е'))).strip()


def _title_stem_overlap(sent, title):
    """Доля основ слов предложения, совпадающих с заголовком (0..1)."""
    q = _stems5(sent)
    t = _stems5(title)
    if not q:
        return 0.0
    return len(q & t) / len(q)


FUNC_TAIL = {'в', 'во', 'на', 'о', 'об', 'обо', 'к', 'ко', 'с', 'со', 'для', 'по', 'про',
             'из', 'от', 'до', 'у', 'за', 'при', 'и', 'а', 'но', 'или', 'что', 'как',
             'это', 'же', 'не', 'ни', 'без', 'над', 'под', 'их'}


def _trim_dangling_tail(s):
    """Обрезать незавершённый хвост: последняя фраза обрывается на служебном слове
    (модель вернула неполный ответ, например «Посты в», в т.ч. с добавленной точкой)."""
    s = (s or '').strip()
    m0 = re.match(r'^(.*?)([.!?…]+)$', s, flags=re.S)
    core, punct = (m0.group(1), m0.group(2)) if m0 else (s, '')
    while True:
        m = re.match(r'^(.*?[.!?…])\s*(.*)$', core, flags=re.S)
        tail = m.group(2).strip() if m else core
        words = [w for w in re.split(r'\W+', tail.lower()) if w]
        if words and words[-1] in FUNC_TAIL:
            tail_pos = core.rfind(tail)
            core = core[:tail_pos].rstrip(' .,;:-—–«»()')
            continue
        break
    out = (core + punct).strip()
    return out


def _summary_one(event, draft=None):
    """Сокращение описания одним запросом ИИ (схема «сократи — сравни — убери повторы»).
    Возвращает итоговый текст продолжения или '' (нечего добавить / сбой запроса).
    Никаких перезапросов и правилового фолбэка: заголовок важнее, остальное опускаем."""
    desc = (event.get('desc') or '').strip()
    text = event['title'] + (('. ' + desc) if desc else '')
    prompt = SHORTEN_PROMPT.replace('{TEXT}', text).replace('{TITLE}', event['title'])
    out = llm_call(prompt)
    if out is None:
        return ''
    s = strip_format_segments(out.strip())
    s = re.sub(r'^(?:верный\s+ответ|итог(?:овый)?\s*(?:текст)?|ответ)\s*:\s*',
               '', s, flags=re.I)
    s = re.sub(r'^[\s"«»\'`*_#-]+', '', s).strip()
    s = re.sub(r'[\s`*_#]+$', '', s).strip()
    s = re.sub(r'\s+', ' ', s).strip()
    s = _trim_dangling_tail(s)
    if not s or re.fullmatch(r'пусто', s.rstrip('.'), flags=re.I):
        return ''
    if REFUSAL_RE.search(s):
        return ''
    t_stems = _stems5(event['title'])
    norm_title = _norm_phrase(event['title'])
    nums = {int(x) for x in re.findall(r'\d+', event['title'] + ' ' + desc)}
    kept, cut_dupes, cut_nums = [], 0, 0
    for sent in _split_sentences(s):
        q_stems = _stems5(sent)
        if len(q_stems) < 2:
            cut_dupes += 1
            continue
        if t_stems and q_stems:
            share = len(q_stems & t_stems) / len(q_stems)
            cover = len(q_stems & t_stems) / len(t_stems)
        else:
            share, cover = 0.0, 0.0
        verbatim = len(norm_title) > 8 and norm_title in _norm_phrase(sent)
        if share > 0.5 or (cover >= 0.9 and len(q_stems - t_stems) <= 5) or verbatim:
            cut_dupes += 1
            continue
        got = {int(x) for x in re.findall(r'\d+', sent)}
        if not got.issubset(nums):
            extra = sorted(got - nums)
            print("[llm] %s (%s...): числа вне источника (%s) — предложение опущено"
                  % (event.get('canon', '?'), event['title'][:40], ', '.join(map(str, extra[:4]))))
            cut_nums += 1
            continue
        kept.append(sent)
    if not kept:
        return ''
    total = ' '.join(kept)
    if total and total[-1] not in '.!?…':
        total += '.'
    if len(total) > SHORTEN_MAX_CHARS:
        acc = ''
        for sent in kept:
            if acc and len(acc) + 1 + len(sent) > SHORTEN_MAX_CHARS:
                break
            acc = (acc + ' ' + sent).strip()
        total = acc
        if total and total[-1] not in '.!?…':
            total += '.'
    if cut_dupes or cut_nums:
        print("[llm] %s (%s...): убрано пустых и повторов: %d, с чужими числами: %d"
              % (event.get('canon', '?'), event['title'][:40], cut_dupes, cut_nums))
    return total

def _formats_one(event):
    """Форматы освещения одного события отдельным запросом ИИ. Список или None."""
    prompt = (FORMATS_PROMPT + "\n\n"
              f"ЗАГОЛОВОК: {event['title']}\n"
              f"ОПИСАНИЕ: {(event['desc'] or '').strip() or '(нет)'}")
    out = llm_call(prompt)
    if out is None:
        return None
    out = out.strip()
    m = re.match(r'^[^:,;]{1,40}:', out)  # срезать префикс вида «Форматы:», «Ответ:»
    if m:
        out = out[m.end():].strip()
    fmts = _parse_llm_formats(out)
    if fmts is None:
        print(f"[llm] {event.get('canon', '?')} ({(event['title'] or '')[:40]}...): форматы не распознаны — правила")
    return fmts


def llm_org_polish(events):
    """Сокращённые тексты и форматы орг-событий через ИИ: два коротких запроса
    на событие (схема «сократи — сравни — убери повторы»).
    Заполняет ev['llm_cont'] (всегда: строка или '') и ev['formats'] (если распознаны).
    Без ключа ИИ события не трогаются. Возвращает число событий с готовым текстом."""
    if not events or not llm_available():
        return 0
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        conts = list(pool.map(_summary_one, events))
        fmts = list(pool.map(_formats_one, events))
    n = 0
    for e, cont, fmt in zip(events, conts, fmts):
        e['llm_cont'] = cont or ''
        if cont:
            n += 1
        if fmt is not None:
            if fmt:
                base = list(dict.fromkeys(e.get('formats') or []))
                e['formats'] = base + [f for f in fmt if f not in base]
            else:
                # «НЕТ»: ИИ уверен, что форматов в тексте нет — верим ему и
                # чистим правила (v7.28), они могли наврать на «программе…»
                if e.get('formats'):
                    print(f"[llm] {e.get('canon', '?')} ({(e['title'] or '')[:40]}...): "
                          "форматы очищены (ИИ: в тексте их нет)")
                e['formats'] = []
    print("[llm] тексты и форматы: %d из %d (схема: сократи/убери повторы)" % (n, len(events)))
    return n


# -------------------------------------------------------------------- DOCX ---
from docx import Document  # noqa: E402
from docx.shared import Pt  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

SECTION_NAMES = [s.strip() for s in os.environ.get("SECTIONS", "").split(",") if s.strip()]



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
