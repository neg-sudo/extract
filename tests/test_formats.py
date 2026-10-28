import bz2
import gzip
import json
import lzma
import tarfile
import unittest
import zipfile
from pathlib import Path

from helpers import (files_under, home_dir, make_tar, make_zip, run, tempdir)


class FormatTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempdir()
        self.base = Path(self._tmp.name)
        self.home = home_dir(self.base)

    def tearDown(self):
        self._tmp.cleanup()

    def test_zip_roundtrip(self):
        archive = make_zip(self.base / "a.zip", {
            "dir/one.txt": "one", "dir/two.txt": "two"})
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files_under(out), ["one.txt", "two.txt"])

    def test_tar_plain(self):
        archive = make_tar(self.base / "a.tar", {"x.txt": "x"})
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files_under(out), ["x.txt"])

    def test_tar_gz_bz2_xz(self):
        for mode, name in (("w:gz", "a.tar.gz"), ("w:bz2", "a.tar.bz2"),
                           ("w:xz", "a.tar.xz")):
            with self.subTest(name=name):
                archive = make_tar(self.base / name, {"x.txt": name}, mode=mode)
                out = self.base / ("out_" + name.replace(".", "_"))
                r = run(["-C", out, "-f", archive], home=self.home)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual((out / "x.txt").read_text(), name)

    def test_single_streams(self):
        payload = b"stream payload\n"
        cases = [
            ("a.gz", gzip.compress(payload)),
            ("a.bz2", bz2.compress(payload)),
            ("a.xz", lzma.compress(payload)),
        ]
        for name, data in cases:
            with self.subTest(name=name):
                archive = self.base / name
                archive.write_bytes(data)
                out = self.base / ("out_" + name.replace(".", "_"))
                r = run(["-C", out, "-f", archive], home=self.home)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(files_under(out), ["a"])

    def test_empty_zip(self):
        archive = make_zip(self.base / "e.zip", {})
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files_under(out), [])

    def test_renamed_archive_detected_by_magic(self):
        payload = make_zip(self.base / "real.zip", {"inside.txt": "magic"})
        disguised = self.base / "image.jpg"
        disguised.write_bytes(payload.read_bytes())
        out = self.base / "out"
        r = run(["-C", out, "-f", disguised], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files_under(out), ["inside.txt"])

    def test_json_output_shape(self):
        archive = make_zip(self.base / "a.zip", {"a.txt": "a", "b.txt": "bb"})
        out = self.base / "out"
        r = run(["--json", "-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["format"], "zip")
        self.assertEqual(data["files"], 2)
        self.assertEqual(data["bytes_written"], 3)
        self.assertEqual(data["exit_code"], 0)
        self.assertIn("duration_ms", data)
        self.assertIn("output", data)

    def test_info_json(self):
        archive = make_zip(self.base / "a.zip", {"a.txt": "hello"})
        r = run(["--json", "-i", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["files"], 1)
        self.assertEqual(data["uncompressed_bytes"], 5)
        self.assertFalse(data["encrypted"])

    def test_list_json(self):
        archive = make_zip(self.base / "a.zip", {"a.txt": "a"})
        r = run(["--json", "-l", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["entries"][0]["name"], "a.txt")

    def test_check_ok_and_bad(self):
        good = make_zip(self.base / "good.zip", {"a.txt": "a"})
        r = run(["--check", good], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        bad = self.base / "bad.zip"
        bad.write_bytes(b"PK\x03\x04not really a zip")
        r = run(["--check", bad], home=self.home)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_include_selective(self):
        archive = make_zip(self.base / "a.zip", {
            "src/a.txt": "a", "src/b.txt": "b", "docs/c.txt": "c"})
        out = self.base / "out"
        r = run(["-C", out, "-f", "--include", "src/a.txt", archive],
                home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files_under(out), ["a.txt"])

    def test_search_and_grep(self):
        archive = make_zip(self.base / "a.zip", {
            "config/app.json": '{"password": "x"}',
            "docs/setup.md": "set a password\n",
            "bin/data.bin": b"\x00\x01password\x00"})
        r = run(["--search", "*.md", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("docs/setup.md", r.stdout)
        self.assertNotIn("app.json", r.stdout)

        r = run(["--grep", "password", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("config/app.json", r.stdout)
        self.assertIn("docs/setup.md", r.stdout)

    def test_unicode_names_preserved(self):
        archive = make_zip(self.base / "u.zip", {"héllo/世界.txt": "ok"})
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files_under(out), ["世界.txt"])

    def test_pack_zip_roundtrip(self):
        src = self.base / "src"
        src.mkdir()
        (src / "a.txt").write_text("a")
        out_zip = self.base / "packed.zip"
        r = run(["--pack", src, out_zip], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        with zipfile.ZipFile(out_zip) as zf:
            self.assertIn("src/a.txt", zf.namelist())


if __name__ == "__main__":
    unittest.main()
