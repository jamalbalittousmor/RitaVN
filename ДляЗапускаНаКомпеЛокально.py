#!/usr/bin/env python3
"""
VN Engine - Dev Server
Локальный сервер для тестирования HTML-файлов.
"""

import sys
import os

# ============================================================
# Проверка версии Python
# ============================================================
if sys.version_info < (3, 7):
    print(f"\n❌ Нужен Python 3.7 или новее.")
    print(f"   У вас: Python {sys.version}")
    print(f"   Скачать: https://www.python.org/downloads/\n")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

# ============================================================
# Проверка модулей
# ============================================================
missing = []
for module in ['http.server', 'json', 'pathlib', 'mimetypes', 'threading', 'webbrowser', 'urllib.parse']:
    try:
        __import__(module)
    except ImportError:
        missing.append(module)

if missing:
    print("\n❌ Отсутствуют необходимые модули:")
    for m in missing:
        print(f"   pip install {m}")
    print()
    input("Нажмите Enter для выхода...")
    sys.exit(1)

# ============================================================
# Импорты
# ============================================================
import http.server
import json
import threading
import webbrowser
import mimetypes
import signal
import ctypes
import socket
from pathlib import Path
from urllib.parse import urlparse, unquote

# ============================================================
# Конфиг
# ============================================================
PORT     = 4933
BASE_DIR = Path(__file__).parent

SPRITES_DIR   = BASE_DIR / "sprites"
BG_DIR        = BASE_DIR / "bg"
AUDIO_DIR     = BASE_DIR / "audio"
SCENARIOS_DIR = BASE_DIR / "scenarios"

IMG_EXTS      = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AUDIO_EXTS    = {".ogg", ".mp3", ".wav"}
SCENARIO_EXTS = {".py"}

# Глобальная ссылка на сервер — нужна для остановки
_server = None

# ============================================================
# Утилиты
# ============================================================
def scan(directory, exts):
    files = []
    if directory.exists():
        for f in directory.rglob("*"):
            if f.is_file() and f.suffix.lower() in exts:
                files.append(str(f.relative_to(directory)).replace("\\", "/"))
    return sorted(files)

def get_resources():
    return {
        "sprites":   scan(SPRITES_DIR,           IMG_EXTS),
        "bg":        scan(BG_DIR,                IMG_EXTS),
        "music":     scan(AUDIO_DIR / "music",   AUDIO_EXTS),
        "ambient":   scan(AUDIO_DIR / "ambient", AUDIO_EXTS),
        "sfx":       scan(AUDIO_DIR / "sfx",     AUDIO_EXTS),
        "scenarios": scan(SCENARIOS_DIR,          SCENARIO_EXTS),
    }

# ============================================================
# HTTP-обработчик
# ============================================================
class VNHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ('/', '/index.html'):
            self._serve_html()
        elif path == '/api/resources':
            self._send_json(get_resources())
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

    def _serve_html(self):
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
        # Только не-200 и не-304 в консоль
        if args and str(args[1]) not in ('200', '304'):
            print(f"  [{args[1]}] {args[0]}")

# ============================================================
# Сервер с таймаутом сокета — чтобы нормально реагировал
# на shutdown() и не висел вечно в accept()
# ============================================================
class VNServer(http.server.HTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Таймаут на сокете: каждые 0.5 сек сервер выходит из
        # блокирующего accept() и проверяет флаг остановки
        self.socket.settimeout(0.5)

    def serve_forever(self, poll_interval=0.5):
        self._BaseServer__is_shut_down.clear()
        try:
            import selectors
            with selectors.DefaultSelector() as sel:
                sel.register(self, selectors.EVENT_READ)
                while not self._BaseServer__shutdown_request:
                    ready = sel.select(poll_interval)
                    if self._BaseServer__shutdown_request:
                        break
                    if ready:
                        self._handle_request_noblock()
                    self.service_actions()
        finally:
            self._BaseServer__shutdown_request = False
            self._BaseServer__is_shut_down.set()

# ============================================================
# Обработка сигналов завершения
# ============================================================
def shutdown_server(signum=None, frame=None):
    global _server
    if _server:
        print("\n\n  ✓ Остановка сервера...")
        # shutdown() вызываем в отдельном потоке,
        # чтобы не дедлочить serve_forever()
        t = threading.Thread(target=_server.shutdown, daemon=True)
        t.start()

# Регистрируем обработчики сигналов
signal.signal(signal.SIGINT,  shutdown_server)  # Ctrl+C
signal.signal(signal.SIGTERM, shutdown_server)  # kill / завершение процесса

# На Windows дополнительно ловим закрытие консоли
if sys.platform == 'win32':
    try:
        HANDLER_ROUTINE = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

        @HANDLER_ROUTINE
        def _win_console_handler(event):
            # CTRL_CLOSE_EVENT = 2, CTRL_LOGOFF_EVENT = 5, CTRL_SHUTDOWN_EVENT = 6
            if event in (0, 1, 2, 5, 6):
                shutdown_server()
                # Небольшая пауза — даём серверу время закрыться
                import time
                time.sleep(1.5)
            return False

        ctypes.windll.kernel32.SetConsoleCtrlHandler(_win_console_handler, True)
    except Exception as e:
        print(f"  (предупреждение: не удалось установить обработчик консоли: {e})")

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
        print(f"\n  ✓ Найден файл: {files[0]}")
        return Path(files[0])

    print("\n  📁 Доступные HTML-файлы:\n")
    for i, name in enumerate(files, 1):
        print(f"     {i}. {name}")

    while True:
        try:
            raw = input(f"\n  Выберите файл [1–{len(files)}]: ").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(files):
                return Path(files[idx])
            print(f"  Введите число от 1 до {len(files)}")
        except ValueError:
            print("  Введите число.")
        except KeyboardInterrupt:
            print("\n\n  Отменено.")
            return None

# ============================================================
# Проверка доступности порта
# ============================================================
def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('', port))
            return True
        except OSError:
            return False

# ============================================================
# Точка входа
# ============================================================
def main():
    global _server

    print("=" * 55)
    print("  VN Engine — Dev Server")
    print("=" * 55)

    selected = select_html()
    if not selected:
        input("\n  Нажмите Enter для выхода...")
        return

    # Проверяем порт
    if not is_port_free(PORT):
        print(f"\n❌ Порт {PORT} уже занят.")
        print(f"   Закройте другой экземпляр сервера.\n")
        input("  Нажмите Enter для выхода...")
        return

    print(f"\n  Файл : {selected}")
    print(f"  URL  : http://localhost:{PORT}/")
    print(f"\n  Закройте окно или нажмите Ctrl+C для остановки")
    print("-" * 55)

    try:
        _server = VNServer(('', PORT), VNHandler)
        _server.selected_html = selected.resolve()

        # Открываем браузер через 0.6 сек в фоновом потоке
        threading.Timer(
            0.6,
            lambda: webbrowser.open(f'http://localhost:{PORT}/')
        ).start()

        # Запускаем — блокирует до вызова shutdown()
        _server.serve_forever()

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        input("\n  Нажмите Enter для выхода...")
        return

    print("  Сервер остановлен. До свидания!\n")

if __name__ == '__main__':
    main()
