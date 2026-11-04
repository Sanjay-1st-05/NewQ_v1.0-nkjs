"""Unit tests for the Stage 8b tray server glue (pure helpers only)."""

import io
import py_compile
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

import server_tray  # noqa: E402


class CompileScripts(unittest.TestCase):
    def test_both_scripts_compile(self):
        import tempfile

        for name in ('server_tray.py', 'install_autostart.py'):
            with self.subTest(script=name):
                with tempfile.TemporaryDirectory() as tmp:
                    py_compile.compile(
                        str(REPO / 'scripts' / name),
                        cfile=str(Path(tmp) / 'c.pyc'),
                        doraise=True,
                    )


class TestResolvePort(unittest.TestCase):
    def test_default_port(self):
        self.assertEqual(server_tray.resolve_port({}), 8000)

    def test_env_port(self):
        self.assertEqual(server_tray.resolve_port({'NEWQ_PORT': '8123'}), 8123)

    def test_invalid_env_falls_back(self):
        self.assertEqual(server_tray.resolve_port({'NEWQ_PORT': 'abc'}), 8000)


class TestRepoRoot(unittest.TestCase):
    def test_repo_root_contains_backend_package(self):
        root = server_tray.repo_root()
        self.assertTrue((Path(root) / 'backend' / 'main.py').is_file())


class TestPortInUse(unittest.TestCase):
    def test_closed_port_not_in_use(self):
        self.assertFalse(server_tray.port_in_use(1))  # nobody listens on :1

    def test_open_port_detected(self):
        import socket
        import threading

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind(('127.0.0.1', 0))
            srv.listen(1)
            port = srv.getsockname()[1]
            self.assertTrue(server_tray.port_in_use(port))


class TestBuildIconImage(unittest.TestCase):
    def test_returns_rgba_image(self):
        image = server_tray.build_icon_image((16, 163, 74), size=64)
        self.assertEqual(image.size, (64, 64))
        self.assertEqual(image.mode, 'RGBA')
        # Rounded-square fill present left of the 'N' glyph.
        self.assertEqual(image.getpixel((8, 32))[:3], (16, 163, 74))
        # Corners stay transparent (rounded).
        self.assertEqual(image.getpixel((0, 0))[3], 0)


class TestInstallAutostart(unittest.TestCase):
    def test_vbs_launcher_rendering(self):
        import install_autostart as installer

        with mock.patch.object(
            installer, 'startup_dir', return_value=Path('C:/fake/startup'),
        ):
            vbs = installer.render_vbs()
            self.assertIn('pythonw.exe', vbs)
            self.assertIn('server_tray.py', vbs)
            # WScript.Shell run hidden flag present.
            self.assertIn(', 0', vbs)

    def test_startup_dir_shape(self):
        import install_autostart as installer

        self.assertTrue(
            str(installer.startup_dir()).endswith(
                'Start Menu\\Programs\\Startup',
            ),
        )


if __name__ == '__main__':
    unittest.main()
