import os
import tempfile
import unittest

# Module imports
from backend.BlockSizeBenchmark import BlockSizeBenchmark
from backend.Command import Command
from backend.Job import Job
from backend.Tape import Tape
from backend.TapeDrive import TapeDrive

KiB: int = 1024
MiB: int = 1024 * 1024


class UT_BlockSizeBenchmark(unittest.TestCase):

    """_summary_
    The block size benchmark: the rule that picks a block size, and the run list on a fake drive
    (a regular file, rewind is a shell command that leaves a trace).
    Tests A:
        - A: the candidates, 128K first; labels
        - B: the rule: at least 90 % of the ideal rate is good enough, the smallest of those is taken
        - C: below 90 % of the ideal rate: a warning with the usable percentage, the best one is the yardstick; nothing measured: 128K
        - D: an unknown ideal rate: the best measured speed is the yardstick
        - E: the whole run list on a fake drive: rewind, test data, ..., rewind; every candidate measured
        - F: every write fails: the other steps still run, the final rewind too, 128K and the note
        - G: requests that are refused up front
        - H: the speed is that of the middle of the run, spin up and spin down do not count
        - I: 64K is measured, but only picked if nothing bigger works
    Depdencies:
    - openssl, dd
    """

    IDEAL: int = 80 * 10**6       # LTO-3

    def setUp(self) -> None:
        Job.Stop()
        Job.Flush()
        Job.limit = 2

    def tearDown(self) -> None:
        Job.Flush()
        Job.limit = Job.DEFAULT_THREADLIMIT

    def _drive(self, tmp: str, tape: str = "3800") -> TapeDrive:
        td: TapeDrive = TapeDrive(os.path.join(tmp, "fake.bin"), "", drive_override=True)
        open(td.path, "wb").close()
        td.tapeOverride(Tape(tape, td.generic_path))
        td.rewindCommand = Command("sh -c 'echo rewind >> " + os.path.join(tmp, "log") + "'")
        return td

    def _rewinds(self, tmp: str) -> int:
        try:
            with open(os.path.join(tmp, "log")) as f:
                return len(f.read().split())
        except FileNotFoundError:
            return 0

    def test_A_candidates(self) -> None:
        c = BlockSizeBenchmark.CANDIDATES
        self.assertEqual(c[0], 128 * KiB)                  # the reference and default
        self.assertEqual(BlockSizeBenchmark.DEFAULT, 128 * KiB)
        self.assertEqual(sorted(c), [n * KiB for n in (64, 128, 256, 384, 512, 1024, 4096)])
        self.assertEqual([BlockSizeBenchmark.label(bs) for bs in (256 * KiB, 384 * KiB, MiB, 4 * MiB)], ["256K", "384K", "1M", "4M"])
        print(".A_CANDIDATES")

    def test_B_rule(self) -> None:
        # LTO-3, ideal 80 MB/s = 76.3 MiB/s, limit 90 % = 68.7 MiB/s: 128K (71.2) is good enough and the smallest
        measured: dict = {128 * KiB: 71.2, 192 * KiB: 70.9, 256 * KiB: 75, 384 * KiB: 75, 512 * KiB: 72, MiB: 65.9}
        results: dict = {bs: mib * MiB for bs, mib in measured.items()}
        self.assertEqual(BlockSizeBenchmark.pick(results, self.IDEAL), (128 * KiB, ""))

        # on the same tape a worse host: only the bigger ones reach the limit, the smallest of those wins
        measured = {128 * KiB: 60, 192 * KiB: 65, 256 * KiB: 70, 384 * KiB: 75, 512 * KiB: 72, MiB: 65.9}
        results = {bs: mib * MiB for bs, mib in measured.items()}
        self.assertEqual(BlockSizeBenchmark.pick(results, self.IDEAL), (256 * KiB, ""))

        # exactly on the limit counts
        self.assertEqual(BlockSizeBenchmark.pick({512 * KiB: 72e6, MiB: 80e6}, self.IDEAL), (512 * KiB, ""))
        print(".B_RULE")

    def test_C_warningAndDefault(self) -> None:
        # the slow cartridge: 50 of 80 MB/s with every block size, 62 % usable, the smallest of the equals is taken
        results: dict = {bs: 50e6 for bs in (128 * KiB, 256 * KiB, 384 * KiB)}
        self.assertEqual(BlockSizeBenchmark.pick(results, self.IDEAL),
                         (128 * KiB, BlockSizeBenchmark.WARNING.format(percent=62)))
        # a half height LTO-8 (300 of 360 MB/s): 83 % usable; the bigger blocks are faster, the smallest within 90 % of the best wins
        results = {256 * KiB: 169e6, 512 * KiB: 170e6, MiB: 247e6, 2 * MiB: 250e6}
        self.assertEqual(BlockSizeBenchmark.pick(results, 360 * 10**6)[0], MiB)
        self.assertIn("69 %", BlockSizeBenchmark.pick(results, 360 * 10**6)[1])
        self.assertIn("half height drive or a worn tape", BlockSizeBenchmark.WARNING)

        # nothing measured: the default
        self.assertEqual(BlockSizeBenchmark.pick({}, self.IDEAL), (128 * KiB, BlockSizeBenchmark.NOTHING))
        print(".C_WARNING")

    def test_D_unknownIdeal(self) -> None:
        results: dict = {128 * KiB: 100e6, 256 * KiB: 95e6, 512 * KiB: 80e6}      # limit: 90 % of the best = 90 MB/s
        self.assertEqual(BlockSizeBenchmark.pick(results, 0), (128 * KiB, ""))
        results = {128 * KiB: 80e6, 256 * KiB: 95e6, 512 * KiB: 100e6}
        self.assertEqual(BlockSizeBenchmark.pick(results, 0), (256 * KiB, ""))
        print(".D_UNKNOWN_IDEAL")

    def test_E_wholeRunList(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            candidates: list = [256 * KiB, 64 * KiB, 4 * MiB]
            bench: BlockSizeBenchmark = BlockSizeBenchmark(td, size=64 * MiB, candidates=candidates)     # big enough that the start of openssl does not count

            self.assertEqual(bench.state, "NEW")
            bench.queue()
            self.assertTrue(all(Job.Get(e).drive == td.id for e in bench.entries))
            self.assertTrue(bench.wait(60))

            self.assertEqual(bench.state, "COMPLETED", str(bench))
            self.assertEqual(self._rewinds(tmp), 4)                         # before each candidate, and after the last one
            self.assertEqual(sorted(bench.results), sorted(candidates))     # all measured
            self.assertTrue(all(rate > 0 for rate in bench.results.values()))

            # a file is much faster than 80 MB/s, so every candidate is good enough: the smallest above the fallback wins
            self.assertEqual(bench.blocksize, "256K")
            self.assertEqual(bench.note, "")
            self.assertEqual([r["blocksize"] for r in bench._asdict()["results"]], ["256K", "64K", "4M"])

            # the fake tape holds the last test, all of it
            self.assertEqual(os.path.getsize(td.path), 64 * MiB)
            with open(td.path, "rb") as f:
                self.assertGreater(len(set(f.read(4096))), 100)             # not zeros
        print(".E_RUNLIST")

    def test_F_everyWriteFails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td: TapeDrive = self._drive(tmp)
            td.path = os.path.join(tmp, "missing", "fake.bin")              # dd cannot open it
            bench: BlockSizeBenchmark = BlockSizeBenchmark(td, size=MiB, candidates=[256 * KiB, 512 * KiB])
            bench.queue()
            self.assertTrue(bench.wait(60))

            self.assertEqual(bench.state, "COMPLETED")
            self.assertEqual(bench.results, {})
            self.assertEqual(self._rewinds(tmp), 3)                         # a failed candidate stops nothing
            self.assertEqual(bench.blocksize, "128K")
            self.assertEqual(bench.note, BlockSizeBenchmark.NOTHING)
            self.assertEqual([r["state"] for r in bench._asdict()["results"]], ["FAILED", "FAILED"])
        print(".F_FAILING")

    def test_G_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertRaises(ValueError, BlockSizeBenchmark(self._drive(tmp, "0000")).queue)        # no tape
            self.assertRaises(ValueError, BlockSizeBenchmark(self._drive(tmp, "3890")).queue)        # write protected

            bench: BlockSizeBenchmark = BlockSizeBenchmark(self._drive(tmp), size=MiB, candidates=[256 * KiB])
            bench.queue()
            self.assertRaises(RuntimeError, bench.queue)                    # only once
            bench.wait(60)
        print(".G_REFUSED")

    def test_H_middleOfTheRun(self) -> None:
        # 3 s without any data, then 80 MB/s, a slow end: the middle says 80 MB/s, the whole run much less
        def line(seconds: float, size: int) -> str:
            return f"{size} bytes (x MB, y MiB) copied, {seconds:g} s, z MB/s"
        progress: str = "\r".join(line(t, int(80e6 * max(0, t - 3))) for t in range(1, 121))
        end: list = ["9600+0 records in", "9600+0 records out", line(130.5, int(80e6 * 117))]
        rate: float = BlockSizeBenchmark.rate([progress] + end)
        self.assertAlmostEqual(rate, 80e6, delta=1e3)
        self.assertLess(80e6 * 117 / 130.5, 0.9 * rate)                        # what the whole run would have said

        self.assertEqual(BlockSizeBenchmark.rate(end), 80e6 * 117 / 130.5)      # no progress: the whole run
        self.assertEqual(BlockSizeBenchmark.rate(["\r".join([line(1, 5), line(2, 10)]), line(2.5, 12)]), 12 / 2.5)   # too short
        self.assertEqual(BlockSizeBenchmark.rate(["dd: error writing"]), 0)
        self.assertEqual(BlockSizeBenchmark.rate([]), 0)
        print(".H_MIDDLE")

    def test_I_fallback(self) -> None:
        good: float = 80e6
        self.assertEqual(BlockSizeBenchmark.pick({64 * KiB: 2 * good, 128 * KiB: good}, self.IDEAL), (128 * KiB, ""))     # never because it is faster
        self.assertEqual(BlockSizeBenchmark.pick({64 * KiB: good, 512 * KiB: good, 256 * KiB: 1e6}, self.IDEAL)[0], 512 * KiB)
        self.assertEqual(BlockSizeBenchmark.pick({64 * KiB: good}, self.IDEAL), (64 * KiB, BlockSizeBenchmark.ONLY_FALLBACK))     # nothing bigger worked
        print(".I_FALLBACK")


if __name__ == "__main__":
    unittest.main()
