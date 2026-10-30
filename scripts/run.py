#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Раннер: скачивает форму с Диска, запускает tool.py в нужном режиме,
загружает результат и снапшот обратно.

v2 (30.10.2026) — устойчивость к сбоям:
  - каждая сетевая операция Диска повторяется до 3 раз с паузой 20 с;
  - честный код выхода: любой незавершённый режим (ошибка tool.py, сбой сети,
    отмена загрузки из-за правки формы) завершает прогон кодом 1 — в GitHub
    Actions он становится КРАСНЫМ и шлёт уведомление, вместо тихо пустого плана.
  - в логе прямо виден пройденный этап: скачивание формы -> снапшот -> tool ->
    загрузка снапшота -> загрузка формы.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tool  # noqa: E402

FORM_PUBLIC_URL = os.environ.get("FORM_URL", "").strip()
FORM_NAME_IN_FOLDER = os.environ.get("FORM_NAME", "").strip()
FORM_DISK_PATH = os.environ.get("FORM_PATH", "").strip()
STATE_PATH = os.environ.get("STATE_PATH", "disk:/_auto/state.json").strip()
TOKEN = os.environ.get("YADISK_TOKEN", "").strip()
if not (FORM_PUBLIC_URL and FORM_NAME_IN_FOLDER and FORM_DISK_PATH):
    sys.exit("FORM_URL / FORM_NAME / FORM_PATH not set")
API = "https://cloud-api.yandex.net/v1/disk"
UA = {"User-Agent": "auto-runner"}

RETRIES = 3        # попыток на сетевую операцию
RETRY_DELAY = 20   # секунд между попытками


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
            if i == tries:
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


def disk_upload(data):
    if not TOKEN:
        print("[runner] YADISK_TOKEN не задан — загрузка на Диск пропущена (тестовый режим)")
        return False
    url = f"{API}/resources/upload?path={urllib.parse.quote(FORM_DISK_PATH)}&overwrite=true"
    with urllib.request.urlopen(_req(url, TOKEN), timeout=30) as r:
        href = json.load(r).get("href")
    if not href:
        raise RuntimeError("Диск не вернул ссылку для загрузки")
    req = urllib.request.Request(
        href, data=data, method="PUT",
        headers={**UA, "Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=180) as r:
        r.read()
    print("[runner] Форма загружена на Диск")
    return True


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
        with urllib.request.urlopen(_req(url, TOKEN), timeout=30) as rr:
            href = json.load(rr)["href"]
        with urllib.request.urlopen(_req(href), timeout=60) as rr:
            data = rr.read()
        with open(local, "wb") as f:
            f.write(data)
        return local

    try:
        return retry_call(_get, "скачивание снапшота")
    except Exception:
        return None


def state_upload(local):
    if not TOKEN:
        return False
    url = (f"{API}/resources/upload?path=" + urllib.parse.quote(STATE_PATH)
           + "&overwrite=true")
    with urllib.request.urlopen(_req(url, TOKEN), timeout=30) as rr:
        href = json.load(rr).get("href")
    req = urllib.request.Request(
        href, data=open(local, "rb").read(), method="PUT",
        headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as rr:
        rr.read()
    return True


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
    if rc != 0:
        print(f"[runner] Режим {mode} завершился с кодом {rc} — на Диск ничего не загружено")
        return "failed"

    print("[runner] Этап 3/5: загрузка снапшота")
    if mode in ("fill", "sync") and os.path.exists(state):
        retry_call(state_upload, "загрузка снапшота")
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
    return "uploaded" if retry_call(lambda: disk_upload(new_data), "загрузка формы") else "nochange"


def main():
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


if __name__ == "__main__":
    main()
