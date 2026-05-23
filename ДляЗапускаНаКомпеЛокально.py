#!/usr/bin/env python3
"""
VN Engine - Dev Server
Локальный сервер для тестирования. Даёт браузеру /api/resources
чтобы работал рандом и полный список сценариев.
"""

import sys
import os

# ============================================================
# Проверка версии Python — ДО всех остальных импортов
# ============================================================
if sys.version_info < (3, 7):
    print(f"\n❌ Нужен Python 3.7 или новее.")
    print(f"   У вас: Python {sys.version}")
    print(f"   Скачать: https://www.python.org/downloads/\n")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

# ============================================================
# Проверка стандартных модулей
# (все из stdlib, pip не нужен — но мало ли)
# ============================================================
REQUIRED_MODULES = [
    ('http.server', None),
    ('json',        None),
    ('pathlib',     None),
    ('mimetypes',   None),
    ('threading',   None),
    ('webbrowser',  None),
    ('urllib.parse', None),
]

missing = []
for module_name, pip_name in REQUIRED_MODULES:
    try:
        __import__(module_name)
    except ImportError:
        missing.append(pip_name or module_name)

if missing:
    print("\n❌ Отсутствуют необходимые модули:")
    for m in missing:
        print(f"   pip install {m}")
    print()
    input("Нажмите Enter для выхода...")
    sys.exit(1)

# ============================================================
# Всё ок — импортируем
# ============================================================
import http.server
import json
import threading
import webbrowser
import mimetypes
from pathlib import Path
from urllib.parse import urlparse, unquote

# ============================================================
# Конфиг
# ============================================================
PORT     = 4931
BASE_DIR = Path(__file__).parent

SPRITES_DIR   = BASE_DIR / "sprites"
BG_DIR        = BASE_DIR / "bg"
AUDIO_DIR     = BASE_DIR / "audio"
SCENARIOS_DIR = BASE_DIR / "scenarios"

IMG_EXTS      = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AUDIO_EXTS    = {".ogg", ".mp3", ".wav"}
SCENARIO_EXTS = {".py"}

# ============================================================
# Утилиты
# ============================================================
def scan(directory, exts):
    """Рекурсивно сканирует папку и возвращает список файлов."""
    files = []
    if directory.exists():
        for f in directory.rglob("*"):
            if f.is_file() and f.suffix.lower() in exts:
                files.append(str(f.relative_to(directory)).replace("\\", "/"))
    return sorted(files)

def get_resources():
    return {
        "sprites":   scan(SPRITES_DIR,          IMG_EXTS),
        "bg":        scan(BG_DIR,               IMG_EXTS),
        "music":     scan(AUDIO_DIR / "music",  AUDIO_EXTS),
        "ambient":   scan(AUDIO_DIR / "ambient",AUDIO_EXTS),
        "sfx":       scan(AUDIO_DIR / "sfx",    AUDIO_EXTS),
        "scenarios": scan(SCENARIOS_DIR,         SCENARIO_EXTS),
    }

# ============================================================
# HTTP-обработчик
# ============================================================
class VNHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        path = urlparse(self.path).path

        # Главная страница
        if path in ('/', '/index.html'):
            self._serve_html()

        # API: список ресурсов для рандома и меню сценариев
        elif path == '/api/resources':
            self._send_json(get_resources())

        # Статические ресурсы
        elif path.startswith('/sprites/'):
            self._serve_file(SPRITES_DIR / unquote(path[9:]))
        elif path.startswith('/bg/'):
            self._serve_file(BG_DIR / unquote(path[4:]))
        elif path.startswith('/audio/'):
            self._serve_file(AUDIO_DIR / unquote(path[7:]))
        elif path.startswith('/scenarios/'):
            self._serve_file(SCENARIOS_DIR / unquote(path[11:]))

        else:
            self.send_error(404, "Not found")

    # ----------------------------------------------------------
    def _serve_html(self):
        """Раздаёт выбранный HTML-файл."""
        html_path = getattr(self.server, 'selected_html', None)
        if not html_path or not html_path.exists():
            self.send_error(404, "HTML file not found")
            return
        data = html_path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filepath):
        filepath = Path(filepath).resolve()
        if not filepath.exists() or not filepath.is_file():
            self.send_error(404, "File not found")
            return
        mime, _ = mimetypes.guess_type(str(filepath))
        data = filepath.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime or 'application/octet-stream')
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        # Только ошибки в консоль
        if args and str(args[1]) not in ('200', '304'):
            print(f"  [{args[1]}] {args[0]}")

# ============================================================
# Выбор HTML-файла
# ============================================================
def find_html_files():
    return sorted([f for f in os.listdir('.') if f.lower().endswith('.html')])

def select_html():
    files = find_html_files()

    if not files:
        print("\n❌ HTML-файлы не найдены в текущей папке.")
        print(f"   Папка: {Path('.').resolve()}\n")
        return None

    if len(files) == 1:
        print(f"\n✓ Найден файл: {files[0]}")
        return Path(files[0])

    print("\n📁 Доступные HTML-файлы:\n")
    for i, name in enumerate(files, 1):
        print(f"   {i}. {name}")

    while True:
        try:
            raw = input(f"\nВыберите файл [1–{len(files)}]: ").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(files):
                return Path(files[idx])
            print(f"   Введите число от 1 до {len(files)}")
        except ValueError:
            print("   Введите число.")
        except KeyboardInterrupt:
            print("\n\n  Отменено.")
            return None

# ============================================================
# Точка входа
# ============================================================
def main():
    print("=" * 55)
    print("  VN Engine — Dev Server")
    print("=" * 55)

    selected = select_html()
    if not selected:
        input("\nНажмите Enter для выхода...")
        return

    print(f"\n  Файл : {selected}")
    print(f"  URL  : http://localhost:{PORT}/")
    print(f"\n  Ctrl+C — остановить сервер\n")
    print("-" * 55)

    try:
        with http.server.HTTPServer(('', PORT), VNHandler) as httpd:
            # Прокидываем выбранный файл в обработчик
            httpd.selected_html = selected.resolve()

            # Открываем браузер чуть позже
            threading.Timer(0.6, lambda: webbrowser.open(f'http://localhost:{PORT}/')).start()

            httpd.serve_forever()

    except OSError as e:
        if e.errno == 98 or e.errno == 10048:  # Порт уже занят
            print(f"\n❌ Порт {PORT} уже занят.")
            print(f"   Закройте другой сервер или смените PORT в скрипте.\n")
        else:
            print(f"\n❌ Ошибка запуска сервера: {e}\n")
        input("Нажмите Enter для выхода...")

    except KeyboardInterrupt:
        print("\n\n  ✓ Сервер остановлен.\n")

    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()
        input("\nНажмите Enter для выхода...")

if __name__ == '__main__':
    main()