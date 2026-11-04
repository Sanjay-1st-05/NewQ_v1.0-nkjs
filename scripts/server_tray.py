"""NewQ Stage 8b — system-tray controller for the NewQ backend.

Runs the FastAPI server (backend.main:app) inside this process while a
pystray icon lives in the Windows notification area. Launched with
pythonw.exe (no console window), typically via the autostart VBS written
by scripts/install_autostart.py — but it also runs fine manually:

    .venv\\Scripts\\python.exe scripts\\server_tray.py

Environment/paths: the script chdirs to the repository root so the
engines' load_dotenv() calls pick up .env and the Firebase service
account JSON resolves relative to the repo, exactly like manual runs.
"""

import os
import sys
import threading
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 8000


def ensure_sys_path():
    """Scripts run via `python scripts\\server_tray.py` get scripts/ as
    sys.path[0] — add the repo root so `backend` imports resolve."""
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.chdir(root)


def repo_root():
    return str(REPO_ROOT)


def resolve_port(env=None):
    """Port the server listens on (NEWQ_PORT env, else 8000)."""
    env = env if env is not None else os.environ
    try:
        return int(env.get('NEWQ_PORT', DEFAULT_PORT))
    except (TypeError, ValueError):
        return DEFAULT_PORT


def port_in_use(port):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def build_icon_image(rgb, size=64):
    """Draw the NewQ tray glyph: rounded square + 'N'. Pure Pillow so the
    icon is generated at runtime (no binary asset to ship)."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    radius = size // 5
    draw.rounded_rectangle(
        [0, 0, size - 1, size - 1],
        radius=radius,
        fill=rgb,
    )

    # 'N' drawn as a simple two-post + diagonal glyph in near-white.
    fg = (255, 255, 255, 240)
    post = max(3, size // 12)
    left, right = size * 0.24, size * 0.70
    top, bottom = size * 0.26, size * 0.74
    draw.rectangle([left, top, left + post, bottom], fill=fg)
    draw.rectangle([right, top, right + post, bottom], fill=fg)

    steps = 18
    dx = (right - left) / steps
    dy = (bottom - top) / steps
    bar = max(2, size // 14)
    for i in range(steps):
        x = left + i * dx
        y = bottom - i * dy
        draw.rectangle(
            [x, y - bar, x + bar, y + bar],
            fill=fg,
        )

    return image


def start_server(port):
    """Run uvicorn in a daemon thread; return the Server handle so the tray
    can shut it down cleanly (server.should_exit = True)."""
    import uvicorn

    config = uvicorn.Config(
        'backend.main:app',
        host='0.0.0.0',
        port=port,
        log_level='info',
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server


def run_tray():
    import pystray

    port = resolve_port()
    ensure_sys_path()

    already_running = port_in_use(port)
    server = None
    if not already_running:
        server = start_server(port)

    running_color = (16, 163, 74)       # green — serving
    external_color = (217, 119, 6)      # amber — port taken externally
    stopped_color = (100, 116, 139)     # grey — quitting

    if already_running:
        color, note = external_color, f'already running on port {port}'
    else:
        color, note = running_color, f'serving on port {port}'

    def on_quit(icon, item):
        if server is not None:
            server.should_exit = True
        icon.stop()

    icon = pystray.Icon(
        'NewQ',
        icon=build_icon_image(color),
        title=f'NewQ server · {note}',
        menu=pystray.Menu(
            pystray.MenuItem(
                lambda item: f'Port {port} — {note}',
                action=None,
                enabled=False,
            ),
            pystray.MenuItem(
                'Open health check',
                lambda: webbrowser.open(f'http://127.0.0.1:{port}/health'),
                enabled=lambda item: not already_running,
            ),
            pystray.MenuItem(
                'Quit',
                on_quit,
            ),
        ),
    )

    icon.run(setup=lambda ic: ic.notify('NewQ server started', 'NewQ'))


if __name__ == '__main__':
    try:
        run_tray()
    except Exception as error:  # keep pythonw.exe from dying silently
        Path(sys.argv[0]).with_name('server_tray_error.log').write_text(
            f'{type(error).__name__}: {error}\n',
            encoding='utf-8',
        )
        raise
