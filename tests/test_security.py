import json
import os
import shutil
import stat
import subprocess
import tarfile
import unittest
import zipfile
from pathlib import Path

from helpers import (files_under, home_dir, make_hardlink_tar, make_mode_tar,
                     make_symlink_tar, make_tar, make_zip, run, tempdir)


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempdir()
        self.base = Path(self._tmp.name)
        self.home = home_dir(self.base)

    def tearDown(self):
        self._tmp.cleanup()

    def _zip(self, name, entries):
        return make_zip(self.base / name, entries)

    def _assert_blocked(self, archive, code=3):
        out = self.base / ("out_" + Path(archive).stem)
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, code, r.stderr)
        return r, out

    def test_zip_slip_parent_traversal(self):
        archive = self._zip("slip.zip", {
            "../../evil.txt": "owned", "ok.txt": "ok"})
        r, out = self._assert_blocked(archive)
        self.assertFalse((self.base / "evil.txt").exists())
        self.assertFalse((self.base.parent / "evil.txt").exists())

    def test_zip_slip_absolute(self):
        archive = self._zip("abs.zip", {"/tmp/evil_abs.txt": "x"})
        self._assert_blocked(archive)

    def test_drive_and_unc_paths(self):
        for i, name in enumerate(["C:/evil.txt", "\\\\server\\share\\evil.txt"]):
            with self.subTest(name=name):
                archive = self._zip(f"drv{i}.zip", {name: "x"})
                self._assert_blocked(archive)

    def test_windows_reserved_names(self):
        for i, name in enumerate(["CON.txt", "NUL", "COM1.log", "LPT9.txt"]):
            with self.subTest(name=name):
                archive = self._zip(f"res{i}.zip", {name: "x"})
                self._assert_blocked(archive)

    def test_ads_and_trailing_dot_space(self):
        for i, name in enumerate(["file.txt:stream", "trailing.", "space "]):
            with self.subTest(name=name):
                archive = self._zip(f"ads{i}.zip", {name: "x"})
                self._assert_blocked(archive)

    def test_unicode_bidi_override(self):
        archive = self._zip("bidi.zip", {"invoice\u202egpj.exe": "x"})
        self._assert_blocked(archive)

    def test_unicode_format_isolate(self):
        archive = self._zip("iso.zip", {"a\u2066b\u2069.txt": "x"})
        self._assert_blocked(archive)

    def test_control_characters(self):
        archive = self._zip("ctrl.zip", {"bell\x07.txt": "x"})
        self._assert_blocked(archive)

    def test_duplicate_entries_blocked_without_force(self):
        archive = make_zip(self.base / "dup.zip", {"same.txt": "one"})
        with zipfile.ZipFile(archive, "a") as zf:
            zf.writestr("same.txt", "two")
        out = self.base / "out"
        r = run(["-C", out, archive], home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_duplicate_entries_allowed_with_force(self):
        archive = make_zip(self.base / "dup.zip", {"same.txt": "one"})
        with zipfile.ZipFile(archive, "a") as zf:
            zf.writestr("same.txt", "two")
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((out / "same.txt").read_text(), "two")

    def test_symlink_outside_blocked(self):
        archive = self.base / "sym.tar"
        make_symlink_tar(archive, "link", "../../etc/passwd")
        r = run(["-C", self.base / "out", "-f", "--allow-symlinks", archive],
                home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse((self.base / "out" / "link").exists())

    def test_symlink_skipped_by_default(self):
        archive = self.base / "sym.tar"
        make_symlink_tar(archive, "link", "target")
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(out / "link"))

    @unittest.skipIf(os.name == "nt", "symlink creation needs privilege")
    def test_symlink_inside_allowed(self):
        archive = self.base / "sym.tar"
        make_symlink_tar(archive, "sub/link", "../target.txt")
        out = self.base / "out"
        r = run(["-C", out, "-f", "--allow-symlinks", "--no-flatten", archive],
                home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.islink(out / "sub" / "link"))

    def test_symlink_strict_blocks_even_inside(self):
        archive = self.base / "sym.tar"
        make_symlink_tar(archive, "link", "target.txt")
        r = run(["-C", self.base / "out", "-f", "--strict", archive],
                home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_hardlink_skipped_by_default(self):
        archive = self.base / "hard.tar"
        make_hardlink_tar(archive, "link.txt", "base.txt")
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(files_under(out), ["base.txt"])

    def test_hardlink_strict_blocked(self):
        archive = self.base / "hard.tar"
        make_hardlink_tar(archive, "link.txt", "base.txt")
        r = run(["-C", self.base / "out", "-f", "--strict", archive],
                home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_setuid_bits_stripped(self):
        archive = self.base / "suid.tar"
        make_mode_tar(archive, "evil", 0o4755)
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        mode = (out / "evil").stat().st_mode
        self.assertFalse(mode & stat.S_ISUID)
        self.assertFalse(mode & stat.S_ISGID)

    def test_no_exec_strips_execute(self):
        archive = self.base / "exec.tar"
        make_mode_tar(archive, "script.sh", 0o755)
        out = self.base / "out"
        r = run(["-C", out, "-f", "--no-exec", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        mode = (out / "script.sh").stat().st_mode
        self.assertFalse(mode & stat.S_IXUSR)

    @unittest.skipIf(os.name == "nt", "symlink creation needs privilege")
    def test_preexisting_symlink_not_followed(self):
        archive = make_zip(self.base / "a.zip", {"link": "payload"})
        out = self.base / "out"
        out.mkdir()
        (out / "link").symlink_to(self.base / "outside.txt")
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse((self.base / "outside.txt").exists())

    def test_special_tar_file_skipped(self):
        archive = self.base / "fifo.tar"
        with tarfile.open(archive, "w") as tf:
            info = tarfile.TarInfo("fifo")
            info.type = tarfile.FIFOTYPE
            tf.addfile(info)
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(out / "fifo"))

    def test_max_files_limit(self):
        archive = make_zip(self.base / "many.zip",
                           {f"f{i}.txt": "x" for i in range(5)})
        r = run(["-C", self.base / "out", "-f", "--max-files", "2", archive],
                home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse((self.base / "out" / "f0.txt").exists())

    def test_max_size_limit(self):
        archive = make_zip(self.base / "big.zip", {"a.txt": "x" * 5000})
        r = run(["-C", self.base / "out", "-f", "--max-size", "1K", archive],
                home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_max_file_size_limit(self):
        archive = make_zip(self.base / "big.zip", {"a.txt": "x" * 5000})
        r = run(["-C", self.base / "out", "-f", "--max-file-size", "1K",
                 archive], home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_max_ratio_limit(self):
        # 65 MiB of zeros is genuinely bomb-like when compressed.
        archive = self.base / "ratio.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("zeros.bin", b"\x00" * (65 * 1024 * 1024))
        r = run(["-C", self.base / "out", "-f", "--max-ratio", "10", archive],
                home=self.home, timeout=180)
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_recursion_depth_limits_self_reference(self):
        inner = make_zip(self.base / "inner.zip", {"leaf.txt": "leaf"})
        outer = self.base / "outer.zip"
        with zipfile.ZipFile(outer, "w") as zf:
            zf.write(inner, "inner.zip")
        out = self.base / "out"
        r = run(["-C", out, "-r", "-f", "--max-depth", "1", outer],
                home=self.home)
        # depth 1 extracts outer; nested depth 2 is refused, not infinite.
        self.assertIn(r.returncode, (0, 3), r.stderr)
        self.assertTrue(out.exists())

    def test_corrupted_zip_exit_2(self):
        archive = self.base / "bad.zip"
        archive.write_bytes(b"PK\x03\x04" + b"\x00" * 40)
        r = run(["-C", self.base / "out", "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_truncated_tar_exit_2(self):
        archive = make_tar(self.base / "a.tar", {"a.txt": "a" * 1000})
        data = archive.read_bytes()
        archive.write_bytes(data[:600])
        r = run(["-C", self.base / "out", "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_unknown_format_exit_6(self):
        f = self.base / "notes.txt"
        f.write_text("not an archive")
        r = run(["-C", self.base / "out", "-f", f], home=self.home)
        self.assertEqual(r.returncode, 6, r.stderr)

    def test_missing_file_exit_1(self):
        r = run(["-C", self.base / "out", self.base / "nope.zip"],
                home=self.home)
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_checksum_mismatch_exit_4(self):
        archive = make_zip(self.base / "a.zip", {"a.txt": "a"})
        r = run(["--sha256", "0" * 64, "-f", "-C", self.base / "out",
                 archive], home=self.home)
        self.assertEqual(r.returncode, 4, r.stderr)

    def test_checksum_match(self):
        import hashlib
        archive = make_zip(self.base / "a.zip", {"a.txt": "a"})
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        r = run(["--sha256", digest, "-C", self.base / "out", "-f",
                 archive], home=self.home)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_security_json_has_exit_code(self):
        archive = self._zip("slip.zip", {"../evil.txt": "x"})
        r = run(["--json", "-C", self.base / "out", "-f", archive],
                home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["exit_code"], 3)


    def test_case_insensitive_collision_blocked(self):
        archive = self._zip("case.zip", {"README.txt": "one",
                                         "readme.txt": "two"})
        out = self.base / "out"
        r = run(["-C", out, archive], home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse(out.exists())

    def test_unicode_normalization_collision_blocked(self):
        archive = self._zip("nfc.zip", {"caf\u00e9.txt": "one",
                                        "cafe\u0301.txt": "two"})
        out = self.base / "out"
        r = run(["-C", out, archive], home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse(out.exists())

    def test_failed_extraction_cleans_partial_output(self):
        archive = make_zip(self.base / "broken.zip",
                           {"payload.bin": b"hello world" * 100})
        with zipfile.ZipFile(archive) as zf:
            info = zf.getinfo("payload.bin")
            offset = info.header_offset + 30 + len(info.filename.encode())
            offset += len(info.extra)
        data = bytearray(archive.read_bytes())
        data[offset] ^= 0xFF
        archive.write_bytes(bytes(data))
        out = self.base / "out"
        r = run(["-C", out, "-f", archive], home=self.home)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertFalse(out.exists())

    @unittest.skipUnless(shutil.which("7z"), "7z not installed")
    def test_external_import_limits_and_cleanup(self):
        src = self.base / "src"
        src.mkdir()
        (src / "big.bin").write_bytes(b"x" * 5000)
        archive = self.base / "ext.7z"
        subprocess.run(["7z", "a", str(archive), "."], cwd=src,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True)
        out = self.base / "out"
        r = run(["-C", out, "-f", "--max-size", "1K", archive],
                home=self.home)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
