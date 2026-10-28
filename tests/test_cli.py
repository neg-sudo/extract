import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from helpers import (ROOT, files_under, home_dir, make_tar, make_zip, run,
                     tempdir)

sys.path.insert(0, str(ROOT / "lib"))
import extract as ex  # noqa: E402
import safeops as so  # noqa: E402


class SanitizeTests(unittest.TestCase):
    def test_traversal(self):
        for name in ("../x", "a/../../x", "a/../b", "..\\x"):
            with self.subTest(name=name):
                self.assertRaises(so.SecurityError, so.sanitize_member_name, name)

    def test_absolute(self):
        for name in ("/etc/passwd", "\\\\server\\share\\x", "C:/x", "c:\\x"):
            with self.subTest(name=name):
                self.assertRaises(so.SecurityError, so.sanitize_member_name, name)

    def test_reserved(self):
        for name in ("CON", "con.txt", "NUL", "COM1.log", "LPT9"):
            with self.subTest(name=name):
                self.assertRaises(so.SecurityError, so.sanitize_member_name, name)

    def test_ads_and_trailing(self):
        for name in ("a:b", "trail.", "trail ", "trail. "):
            with self.subTest(name=name):
                self.assertRaises(so.SecurityError, so.sanitize_member_name, name)

    def test_bidi_and_controls(self):
        for name in ("a\u202eb", "a\u2066b", "a\x07b", "a\x00b"):
            with self.subTest(name=name):
                self.assertRaises(so.SecurityError, so.sanitize_member_name, name)

    def test_normalization(self):
        self.assertEqual(so.sanitize_member_name("./a//b/./c"), "a/b/c")
        self.assertEqual(so.sanitize_member_name("世界/é.txt"), "世界/é.txt")

    def test_parse_size(self):
        self.assertEqual(so.parse_size("10G"), 10 * 1024 ** 3)
        self.assertEqual(so.parse_size("1.5M"), int(1.5 * 1024 ** 2))
        self.assertEqual(so.parse_size("2GiB"), 2 * 1024 ** 3)
        self.assertEqual(so.parse_size("1024"), 1024)
        self.assertRaises(ValueError, so.parse_size, "nope")

    def test_limits(self):
        limits = so.Limits(max_files=2, max_total=10, max_file=10,
                           max_ratio=1000)
        with self.assertRaises(so.SecurityError):
            limits.check_archive(3, 5, 100, 2)
        with self.assertRaises(so.SecurityError):
            limits.check_archive(1, 11, 100, 2)
        with self.assertRaises(so.SecurityError):
            limits.check_archive(1, 5, 100, 11)
        limits.check_archive(1, 5, 100, 5)


class CLITests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempdir()
        self.base = Path(self._tmp.name)
        self.home = home_dir(self.base)

    def tearDown(self):
        self._tmp.cleanup()

    def test_version(self):
        r = run(["--version"], home=self.home)
        self.assertEqual(r.returncode, 0)
        self.assertIn("3.0.0", r.stdout)

    def test_help_exit_codes_documented(self):
        r = run(["--help"], home=self.home)
        self.assertEqual(r.returncode, 0)
        self.assertIn("exit codes", r.stdout)
        self.assertIn("security violation", r.stdout)

    def test_completions(self):
        for shell in ("bash", "zsh", "fish", "powershell", "nushell"):
            with self.subTest(shell=shell):
                r = run(["--completion", shell], home=self.home)
                self.assertEqual(r.returncode, 0)
                self.assertTrue(r.stdout.strip())

    def test_verify_install(self):
        r = run(["--verify-install"], home=self.home)
        self.assertEqual(r.returncode, 0)
        self.assertIn("security core: ok", r.stdout)

    def test_overwrite_directory_requires_force(self):
        archive = make_zip(self.base / "a.zip", {"a.txt": "a"})
        out = self.base / "out"
        out.mkdir()
        r = run(["-C", out, archive], home=self.home)
        self.assertEqual(r.returncode, 1, r.stderr)
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_flatten(self):
        archive = make_zip(self.base / "a.zip", {"dir/a.txt": "a"})
        out = self.base / "out"
        r = run(["-C", out, "-f", "--no-flatten", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files_under(out), ["dir/a.txt"])

    def test_keep_junk(self):
        archive = make_zip(self.base / "a.zip", {
            "a.txt": "a", "__MACOSX/x": "junk", ".DS_Store": "junk"})
        out = self.base / "out"
        r = run(["-C", out, "-f", "--keep-junk", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("__MACOSX/x", files_under(out))
        self.assertIn(".DS_Store", files_under(out))

    def test_history_written(self):
        archive = make_zip(self.base / "a.zip", {"a.txt": "a"})
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        hist = self.home / ".local" / "state" / "extract" / "history.json"
        self.assertTrue(hist.exists())
        entries = json.loads(hist.read_text())
        self.assertEqual(entries[-1]["status"], "ok")

    def test_diff(self):
        a = make_zip(self.base / "a.zip", {"same.txt": "a", "only_a.txt": "a"})
        b = make_zip(self.base / "b.zip", {"same.txt": "b", "only_b.txt": "b"})
        r = run(["--diff", a, b], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("only_a.txt", r.stdout)
        self.assertIn("only_b.txt", r.stdout)

    def test_parallel_two_archives(self):
        a = make_zip(self.base / "a.zip", {"a.txt": "a"})
        b = make_zip(self.base / "b.zip", {"b.txt": "b"})
        r = run(["-f", "-j", "2", a, b], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless(shutil.which("zip"), "zip CLI not available")
    def test_encrypted_zip_password(self):
        src = self.base / "secret.txt"
        src.write_text("secret")
        archive = self.base / "enc.zip"
        subprocess.run(["zip", "-q", "-P", "hunter2", str(archive),
                        src.name], check=True, cwd=self.base)
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 5, r.stderr)
        self.assertNotIn("hunter2", r.stderr)
        r = run(["-C", out, "-f", "-p", "hunter2", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((out / "secret.txt").read_text(), "secret")
        r = run(["-C", self.base / "out2", "-f", "-p", "wrong", archive],
                home=self.home)
        self.assertEqual(r.returncode, 5, r.stderr)

    @unittest.skipUnless(shutil.which("7z"), "7z not available")
    def test_7z_external_safe_path(self):
        src = self.base / "hello.txt"
        src.write_text("seven")
        archive = self.base / "a.7z"
        subprocess.run(["7z", "a", "-bd", str(archive), str(src)],
                       check=True, cwd=self.base,
                       stdout=subprocess.DEVNULL)
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files_under(out), ["hello.txt"])

    @unittest.skipUnless(shutil.which("7z"), "7z not available")
    def test_sandbox_refuses_external_helper(self):
        src = self.base / "hello.txt"
        src.write_text("seven")
        archive = self.base / "a.7z"
        subprocess.run(["7z", "a", "-bd", str(archive), str(src)],
                       check=True, cwd=self.base,
                       stdout=subprocess.DEVNULL)
        out = self.base / "out"
        r = run(["--sandbox", "-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 6, r.stderr)
        self.assertFalse(out.exists())

    def test_sandbox_allows_native(self):
        archive = make_zip(self.base / "a.zip", {"a.txt": "native"})
        out = self.base / "out"
        r = run(["--sandbox", "-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((out / "a.txt").read_text(), "native")

    @unittest.skipUnless(shutil.which("zstd") and shutil.which("tar"),
                         "zstd/tar not available")
    def test_tar_zst_external(self):
        src = self.base / "src"
        src.mkdir()
        (src / "z.txt").write_text("zstd")
        archive = self.base / "a.tar.zst"
        r = subprocess.run(["tar", "--zstd", "-cf", str(archive), "src"],
                           cwd=self.base, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        if r.returncode != 0:
            self.skipTest("tar --zstd unsupported")
        out = self.base / "out"
        res = run(["-C", out, "-f", "--no-flatten", archive], home=self.home)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(files_under(out), ["src/z.txt"])

    def test_environment_limits(self):
        archive = make_zip(self.base / "a.zip", {"a.txt": "a", "b.txt": "b"})
        r = run(["-C", self.base / "out", "-f", archive], home=self.home,
                extra_env={"EXTRACT_MAX_FILES": "1"})
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_download_filename_is_sanitized(self):
        self.assertEqual(ex.safe_download_name("http://x/archive.zip"),
                         "archive.zip")
        for url in ("http://x/..", "http://x/", "http://x/CON.zip",
                    "http://x/a%00b.zip", "http://x/%2e%2e"):
            with self.subTest(url=url):
                self.assertEqual(ex.safe_download_name(url), "download")

    def test_url_download_and_extract(self):
        make_zip(self.base / "remote.zip", {"net.txt": "over http"})

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        handler = functools.partial(QuietHandler, directory=str(self.base))
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/remote.zip"
            out = self.base / "out"
            r = run(["-C", out, "-f", url], home=self.home)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(files_under(out), ["net.txt"])
            self.assertEqual((out / "net.txt").read_text(), "over http")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
