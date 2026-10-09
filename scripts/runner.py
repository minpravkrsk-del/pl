#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mediaplan_tool  # noqa: E402

FORM_PUBLIC_URL = os.environ.get("FORM_PUBLIC_URL",
                                 "https://disk.yandex.ru/d/gslE0kfCxbZXtQ")
FORM_NAME_IN_FOLDER = os.environ.get(
    "FORM_NAME_IN_FOLDER", "/Контент-план губернатора и правительства.docx")
FORM_DISK_PATH = os.environ.get(
    "FORM_DISK_PATH", "disk:/Контент-план/Контент-план губернатора и правительства.docx")
STATE_DIR = os.environ.get("STATE_DIR",
                           os.path.join(os.path.dirname(HERE), "state"))
TOKEN = os.environ.get("YADISK_TOKEN", "").strip()
API = "https://cloud-api.yandex.net/v1/disk"
UA = {"User-Agent": "mediaplan-runner"}


def _req(url, token=None):
    h = dict(UA)
    if token:
        h["Authorization"] = "OAuth " + token
    return urllib.request.Request(url, headers=h)


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
        href, modified, size = disk_info()
        print(f"[runner] Форма на Диске: {size} байт, изменена: {modified}")
    else:
        url = ("https://cloud-api.yandex.net/v1/disk/public/resources/download"
               "?public_key=" + urllib.parse.quote(FORM_PUBLIC_URL)
               + "&path=" + urllib.parse.quote(FORM_NAME_IN_FOLDER))
        with urllib.request.urlopen(_req(url), timeout=30) as r:
            href = json.load(r)["href"]
        modified = None
        print("[runner] Скачиваю форму по публичной ссылке (без токена)")
    with urllib.request.urlopen(_req(href), timeout=120) as r:
        return r.read(), modified


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


def run_mode(mode, monday, workdir):
    src = os.path.join(workdir, "form_current.docx")
    out = os.path.join(workdir, "form_new.docx")
    state = os.path.join(STATE_DIR, f"state_{monday}.json")
    data, modified = disk_download()
    with open(src, "wb") as f:
        f.write(data)

    cmd = [sys.executable, os.path.join(HERE, "mediaplan_tool.py"), mode,
           "--monday", monday, "--src", src, "--out", out]
    if mode in ("fill", "sync"):
        cmd += ["--state", state]
    print("[runner] ЗАПУСК:", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        print(f"[runner] Режим {mode} завершился с кодом {rc} — на Диск ничего не загружено")
        return False

    with open(out, "rb") as f:
        new_data = f.read()
    if new_data == data:
        print("[runner] Файл не изменился — загрузка на Диск не нужна")
        return False
    if modified is not None:
        if disk_info()[1] != modified:
            print("[runner] ОТМЕНА ЗАГРУЗКИ: форму редактировали во время работы робота. "
                  "Ничего не перезаписано — запустите ещё раз позже.")
            return False
    return disk_upload(new_data)


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
    os.makedirs(STATE_DIR, exist_ok=True)
    workdir = "/tmp" if os.path.isdir("/tmp") else os.getcwd()
    uploaded = run_mode(mode, monday, workdir)
    print(f"[runner] Итог: {mode} за неделю {monday}; загрузка на Диск: "
          f"{'выполнена' if uploaded else 'нет'}")


if __name__ == "__main__":
    main()
