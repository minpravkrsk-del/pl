#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Раннер: скачивает форму с Диска, запускает tool.py в нужном режиме,
загружает результат и снапшот обратно.

v2.6 (06.11.2026) — режим из аргументов обрезается от пробелов
  ("fill " из поля ручного запуска больше не валит прогон с argparse-error).
v2.5 (06.11.2026) — 404 при скачивании снапшота не ретраится
  (после prep снапшота нет и это норма; экономит ~40 с на прогон).
v2.4 (06.11.2026) — prep сам удаляет снапшот недели после успешной заливки
  формы: иначе следующий fill видит снапшот, переключается на sync и
  отказывается (ловушка «пустая таблица + снапшот»). Удаление идёт в Корзину
  Диска, повторяется с ретраями; при неудаче прогон помечается ошибкой.
v2.3 (05.11.2026) — v2.2 + штатная отмена не помечается ошибкой:
  * перед перезаписью формы старая версия сохраняется на Диск (form_prev.docx);
  * после загрузки файл скачивается обратно и сверяется по md5;
  * при расхождении — повтор загрузки, при неудаче — откат на бэкап;
  * если файл открыт в редакторе Яндекс Диска (залочен) — терпеливые повторы
    и понятное сообщение вместо красной тишины;
  * штатный отказ tool.py (защита данных, код выхода 3) — прогон зелёный
    со статусом "skipped", а не красный;
  - каждая сетевая операция Диска повторяется до 3 раз с паузой 20 с;
  - честный код выхода: любой незавершённый режим (ошибка tool.py, сбой сети,
    отмена загрузки из-за правки формы) завершает прогон кодом 1 — в GitHub
    Actions он становится КРАСНЫМ и шлёт уведомление, вместо тихо пустого плана.
  - в логе прямо виден пройденный этап: скачивание формы -> снапшот -> tool ->
    загрузка снапшота -> загрузка формы.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tool  # noqa: E402

FORM_PUBLIC_URL = os.environ.get("FORM_URL", "").strip()
FORM_NAME_IN_FOLDER = os.environ.get("FORM_NAME", "").strip()
FORM_DISK_PATH = os.environ.get("FORM_PATH", "").strip()
STATE_PATH = os.environ.get("STATE_PATH", "disk:/_auto/state.json").strip()
FORM_BACKUP_PATH = os.environ.get("FORM_BACKUP_PATH", "disk:/_auto/form_prev.docx")
TOKEN = os.environ.get("YADISK_TOKEN", "").strip()
if not (FORM_PUBLIC_URL and FORM_NAME_IN_FOLDER and FORM_DISK_PATH):
    sys.exit("FORM_URL / FORM_NAME / FORM_PATH not set")
API = "https://cloud-api.yandex.net/v1/disk"
UA = {"User-Agent": "auto-runner"}

RETRIES = 3        # попыток на сетевую операцию
RETRY_DELAY = 20   # секунд между попытками


class _StateNotFound(Exception):
    """Снапшот недели отсутствует на Диске (404) — норма после prep,
    не ретраится."""


def _req(url, token=None):
    h = dict(UA)
    if token:
        h["Authorization"] = "OAuth " + token
    return urllib.request.Request(url, headers=h)


def retry_call(fn, label, tries=RETRIES, delay=RETRY_DELAY):
    """Выполнить сетевую операцию с повторами; на последней попытке — исключение наружу."""
    for i in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:
            if i == tries or isinstance(e, _StateNotFound):
                raise
            print(f"[runner] {label}: попытка {i}/{tries} не удалась ({e}); повтор через {delay} c")
            time.sleep(delay)


def disk_info():
    """(прямая ссылка, изменён, размер) файла формы на Диске."""
    url = (f"{API}/resources?path={urllib.parse.quote(FORM_DISK_PATH)}"
           "&fields=file,modified,size")
    with urllib.request.urlopen(_req(url, TOKEN), timeout=30) as r:
        info = json.load(r)
    return info.get("file"), info.get("modified"), info.get("size")


def disk_download():
    """Скачать форму: с авторизацией (если есть токен) или по публичной ссылке."""
    if TOKEN:
        href, modified, size = retry_call(disk_info, "метаданные формы")
        print(f"[runner] Форма на Диске: {size} байт, изменена: {modified}")
    else:
        url = ("https://cloud-api.yandex.net/v1/disk/public/resources/download"
               "?public_key=" + urllib.parse.quote(FORM_PUBLIC_URL)
               + "&path=" + urllib.parse.quote(FORM_NAME_IN_FOLDER))
        with urllib.request.urlopen(_req(url), timeout=30) as r:
            href = json.load(r)["href"]
        modified = None
        print("[runner] Скачиваю форму по публичной ссылке (без токена)")

    def _fetch(h):
        with urllib.request.urlopen(_req(h), timeout=120) as r:
            return r.read()

    data = retry_call(lambda: _fetch(href), "скачивание формы")
    return data, modified


def disk_upload(data, prev=None):
    """Безопасно перезаписать форму на Диске.

    1. Сначала сохранить бэкап текущей версии (form_prev.docx) — best effort.
    2. Затем перезаписать форму с проверкой md5 после записи.
    3. Если форма остаётся битой — восстановить бэкап и сдаться честно."""
    if not TOKEN:
        print("[runner] YADISK_TOKEN не задан — загрузка на Диск пропущена (тестовый режим)")
        return False
    if prev:
        try:
            if safe_upload(FORM_BACKUP_PATH, prev, "бэкап формы",
                           "application/octet-stream", tries=2, delay=5):
                print("[runner] Бэкап прежней версии сохранён на Диск (form_prev.docx)")
            else:
                print("[runner] ВНИМАНИЕ: бэкап прежней версии не сохранён — "
                      "продолжаю загрузку без него")
        except Exception as e:
            print(f"[runner] ВНИМАНИЕ: бэкап не удался ({e}) — продолжаю загрузку")
    if safe_upload(FORM_DISK_PATH, data, "загрузка формы", "application/octet-stream"):
        print("[runner] Форма загружена на Диск и сверена (md5)")
        return True
    if prev:
        print("[runner] Попытка откатить форму на прежнюю версию...")
        if safe_upload(FORM_DISK_PATH, prev, "откат на бэкап",
                       "application/octet-stream", tries=3, delay=10):
            print("[runner] Откат выполнен: на Диске прежняя (рабочая) версия; "
                  "запустите прогон ещё раз позже")
            return False
        print("[runner] ВНИМАНИЕ: откат не удался — проверьте файл на Диске вручную!")
    return False


def pick_mode(now=None):
    """Режим по текущему времени UTC (с запасом на задержку запуска cron).
    Красноярск = UTC+7."""
    now = now or datetime.now(timezone.utc)
    if now.weekday() == 3:                       # четверг
        if 2 <= now.hour <= 8:
            return "prep"
        if 9 <= now.hour <= 14:
            return "fill"
    if now.weekday() == 4 and 1 <= now.hour <= 6:  # пятница, утро
        return "sync"
    return None


def next_monday(today=None):
    today = today or datetime.now(timezone.utc).date()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def state_download(monday, workdir):
    """Скачать снапшот с Диска во временный файл; вернуть путь или None."""
    if not TOKEN:
        return None
    local = os.path.join(workdir, f"state_{monday}.json")

    def _get():
        url = (f"{API}/resources/download?path=" + urllib.parse.quote(STATE_PATH))
        try:
            with urllib.request.urlopen(_req(url, TOKEN), timeout=30) as rr:
                href = json.load(rr)["href"]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise _StateNotFound()
            raise
        with urllib.request.urlopen(_req(href), timeout=60) as rr:
            data = rr.read()
        with open(local, "wb") as f:
            f.write(data)
        return local

    try:
        return retry_call(_get, "скачивание снапшота")
    except _StateNotFound:
        print("[runner] Снапшот на Диске отсутствует (после prep это норма)")
        return None
    except Exception:
        return None


def _md5(b):
    return hashlib.md5(b).hexdigest()


def _put_resource(path, data, ctype):
    """Перезаписать ресурс на Диске одним PUT (overwrite=true)."""
    url = (f"{API}/resources/upload?path=" + urllib.parse.quote(path)
           + "&overwrite=true")
    with urllib.request.urlopen(_req(url, TOKEN), timeout=30) as rr:
        href = json.load(rr).get("href")
    if not href:
        raise RuntimeError("Диск не вернул ссылку для загрузки")
    req = urllib.request.Request(
        href, data=data, method="PUT",
        headers={**UA, "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=180) as rr:
        rr.read()


def _fetch_resource(path):
    """Скачать ресурс с Диска целиком."""
    url = (f"{API}/resources/download?path=" + urllib.parse.quote(path))
    with urllib.request.urlopen(_req(url, TOKEN), timeout=30) as rr:
        href = json.load(rr).get("href")
    with urllib.request.urlopen(urllib.request.Request(
            href, headers={**UA}), timeout=120) as rr:
        return rr.read()


def _is_lock_error(e):
    s = str(e).lower()
    return ("lock" in s or "409" in s or "conflict" in s)


def safe_upload(path, data, label, ctype, tries=5, delay=30):
    """Загрузить данные на Диск с проверкой после записи.

    Каждый шаг: PUT (overwrite=true) -> скачать обратно -> сверить md5.
    Если файл залочен (открыт в редакторе) — повторить позже.
    Если после записи файл оказался битым — повторить загрузку.
    Вернуть True/False."""
    want = _md5(data)
    for i in range(1, tries + 1):
        try:
            _put_resource(path, data, ctype)
        except Exception as e:
            if _is_lock_error(e):
                print(f"[runner] {label}: файл на Диске открыт в редакторе "
                      f"(залочен); подождите и он освободится. Повтор {i}/{tries} через {delay} c")
            else:
                print(f"[runner] {label}: запись не удалась ({e}); повтор {i}/{tries} через {delay} c")
            if i < tries:
                time.sleep(delay)
            continue
        try:
            got = _fetch_resource(path)
            if _md5(got) == want:
                return True
            print(f"[runner] {label}: запись сверяется неверно (md5 расходится) — повтор {i}/{tries}")
        except Exception as e:
            print(f"[runner] {label}: не удалось проверить запись ({e}) — повтор {i}/{tries}")
        if i < tries:
            time.sleep(delay)
    return False


def state_upload(local):
    if not TOKEN:
        return False
    with open(local, "rb") as f:
        data = f.read()
    ok = safe_upload(STATE_PATH, data, "загрузка снапшота",
                     "application/json", tries=3, delay=20)
    if ok:
        print("[runner] Снапшот загружен и сверён (md5)")
    return ok


def state_delete(tries=3, delay=10):
    """Удалить снапшот недели с Диска (перемещается в Корзину). Вернуть True/False."""
    if not TOKEN:
        print("[runner] TOKEN не задан — удаление снапшота пропущено (тестовый режим)")
        return True
    url = f"{API}/resources?path=" + urllib.parse.quote(STATE_PATH)
    for i in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={**UA, "Authorization": "OAuth " + TOKEN},
                                         method="DELETE")
            with urllib.request.urlopen(req, timeout=30) as rr:
                rr.read()
            print("[runner] Снапшот недели удалён с Диска (state.json) — "
                  "следующий fill сможет запуститься заново")
            return True
        except Exception as e:
            if "404" in str(e):
                print("[runner] Снапшот на Диске отсутствует — удалять нечего")
                return True
            print(f"[runner] удаление снапшота: попытка {i}/{tries} не удалась ({e})"
                  + (f"; повтор через {delay} c" if i < tries else ""))
            if i < tries:
                time.sleep(delay)
    print(f"[runner] ВНИМАНИЕ: снапшот НЕ удалён — следующий fill не пройдёт! "
          f"Удалите {STATE_PATH} с Диска вручную")
    return False


def run_mode(mode, monday, workdir):
    """Вернуть статус: 'uploaded' | 'nochange' | 'failed'."""
    src = os.path.join(workdir, "form_current.docx")
    out = os.path.join(workdir, "form_new.docx")
    state = None
    if mode in ("fill", "sync"):
        state = state_download(monday, workdir)
        if state is None:
            state = os.path.join(workdir, f"state_{monday}.json")
            if mode == "sync":
                print("[runner] ОТМЕНА: снапшот недели не найден на Диске. Сначала fill.")
                return "failed"
    print("[runner] Этап 1/5: скачивание формы")
    data, modified = retry_call(disk_download, "скачивание формы")
    with open(src, "wb") as f:
        f.write(data)

    cmd = [sys.executable, os.path.join(HERE, "tool.py"), mode,
           "--monday", monday, "--src", src, "--out", out]
    if mode in ("fill", "sync"):
        cmd += ["--state", state]
    print("[runner] Этап 2/5: ЗАПУСК:", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc == 3:
        print("[runner] ШТАТНАЯ ОТМЕНА (защита данных): условия не подходят для этой операции. "
              "Это не сбой — данные в целости, прогон завершён без изменений")
        return "skipped"
    if rc != 0:
        print(f"[runner] Режим {mode} завершился с кодом {rc} — на Диск ничего не загружено")
        return "failed"

    print("[runner] Этап 3/5: загрузка снапшота")
    if mode in ("fill", "sync") and os.path.exists(state):
        if not retry_call(lambda: state_upload(state), "загрузка снапшота"):
            raise RuntimeError("снапшот не загружен на Диск")
    with open(out, "rb") as f:
        new_data = f.read()
    if new_data == data:
        print("[runner] Файл не изменился — загрузка на Диск не нужна")
        return "nochange"
    print("[runner] Этап 4/5: проверка, что форму не правили во время работы")
    if modified is not None:
        current = retry_call(lambda: disk_info()[1], "метаданные формы")
        if current != modified:
            print("[runner] ОТМЕНА ЗАГРУЗКИ: форму редактировали во время работы робота. "
                  "Ничего не перезаписано — запустите ещё раз позже.")
            return "failed"
    print("[runner] Этап 5/5: загрузка формы")
    ok = disk_upload(new_data, data)
    if ok and mode == "prep":
        # Prep затёр таблицу — снапшот недели устарел и блокирует следующий fill.
        if not state_delete():
            print("[runner] prep загрузил форму, но снапшот не удалён — "
                  "прогон помечен как упавший, чтобы обратить внимание")
            return "failed"
    return "uploaded" if ok else "failed"


def main():
    if len(sys.argv) > 1:  # обрезать случайные пробелы у режима ("fill " и т.п.)
        sys.argv[1] = sys.argv[1].strip()
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", choices=["prep", "fill", "sync"],
                    help="режим; без указания — определяется по времени UTC")
    ap.add_argument("--monday", help="YYYY-MM-DD понедельник недели "
                                     "(по умолчанию — ближайший следующий)")
    args = ap.parse_args()

    mode = args.mode or pick_mode()
    if mode is None:
        print("[runner] Сейчас вне окон расписания; укажите режим явно: prep|fill|sync")
        return
    monday = args.monday or str(next_monday())
    workdir = "/tmp" if os.path.isdir("/tmp") else os.getcwd()
    try:
        status = run_mode(mode, monday, workdir)
    except Exception:
        print("[runner] СБОЙ раннера:")
        traceback.print_exc()
        status = "failed"
    print(f"[runner] Итог: {mode} за неделю {monday}; загрузка на Диск: "
          f"{'выполнена' if status == 'uploaded' else 'нет'}")
    if status == "failed":
        print("[runner] ЗАВЕРШЕНО С ОШИБКОЙ — прогон помечен как упавший; "
              "изменения на Диск могли не попасть, запустите режим ещё раз")
        sys.exit(1)
    if status == "skipped":
        print("[runner] Прогон штатно отменён защитой данных — ошибки нет")


if __name__ == "__main__":
    main()
