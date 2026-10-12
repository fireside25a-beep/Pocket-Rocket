import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from neuro_inverse.host_preflight import (
    ARITHMETIC_AVX2_VERIFIED,
    ARITHMETIC_INTEGER_ORACLE,
    ARITHMETIC_X87_VERIFIED,
    ArithmeticModeCertificate,
    HostPreflight,
    classify_x86_64,
    inspect_host,
    parse_cpu_flags,
    require_cpu_host,
)


V3_FLAGS = "cmov cx8 fpu fxsr mmx sse sse2 cx16 lahf_lm popcnt pni ssse3 sse4_1 sse4_2 avx avx2 bmi1 bmi2 f16c fma abm movbe xsave"


class HostPreflightTests(unittest.TestCase):
    def test_flag_aliases_and_v3_classification(self):
        flags = parse_cpu_flags("flags : " + V3_FLAGS)
        self.assertIn("sse3", flags)
        self.assertIn("lzcnt", flags)
        self.assertEqual(classify_x86_64("AMD64", flags), (True, True, ()))

    def test_non_x86_and_incomplete_baseline_fail_closed(self):
        self.assertFalse(classify_x86_64("aarch64", V3_FLAGS.split())[0])
        baseline, v3, missing = classify_x86_64("x86_64", {"sse2"})
        self.assertFalse(baseline)
        self.assertFalse(v3)
        self.assertIn("fpu", missing)

    def test_read_only_report_disables_gpu_and_privileged_tuning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cpuinfo = root / "cpuinfo"
            cpuinfo.write_text("flags : " + V3_FLAGS + "\n", encoding="utf-8")
            thp = root / "kernel/mm/transparent_hugepage"
            thp.mkdir(parents=True)
            (thp / "enabled").write_text("always [madvise] never\n", encoding="utf-8")
            with patch("neuro_inverse.host_preflight.platform.machine", return_value="x86_64"), \
                 patch("neuro_inverse.host_preflight.platform.system", return_value="Linux"):
                report = inspect_host(cpuinfo_path=cpuinfo, sys_root=root)
        self.assertTrue(report.x86_64_v3)
        self.assertEqual(report.gpu_backend, "disabled")
        self.assertFalse(report.privileged_tuning_performed)
        self.assertEqual(report.transparent_hugepage_mode, "madvise")
        self.assertEqual(report.default_arithmetic_mode, ARITHMETIC_INTEGER_ORACLE)
        self.assertTrue(any("MADV_HUGEPAGE" in item for item in report.user_space_advice))
        self.assertEqual(len(report.certificate_sha256), 64)
        require_cpu_host(report)

    def test_accelerated_arithmetic_requires_matching_oracle_digest(self):
        digest = "a" * 64
        certificate = ArithmeticModeCertificate(
            ARITHMETIC_AVX2_VERIFIED, digest, digest, "b" * 64, True
        )
        self.assertEqual(len(certificate.certificate_sha256), 64)
        with self.assertRaises(ValueError):
            ArithmeticModeCertificate(
                ARITHMETIC_AVX2_VERIFIED, digest, "c" * 64, "b" * 64, False
            )

    def test_x87_requires_matching_oracle_digest_and_integer_is_default(self):
        digest = "d" * 64
        certificate = ArithmeticModeCertificate(
            ARITHMETIC_X87_VERIFIED, digest, digest, "e" * 64, True
        )
        self.assertEqual(certificate.mode, "x87_verified")
        with self.assertRaises(ValueError):
            ArithmeticModeCertificate(
                ARITHMETIC_X87_VERIFIED, digest, "f" * 64, "e" * 64, False
            )

    def test_require_rejects_non_linux_or_gpu_state(self):
        base = dict(
            architecture="x86_64", linux=False, x86_64_v1=True, x86_64_v3=False,
            avx2=False, fma=False, cpu_count=1, allowed_cpus=(0,), affinity_available=True,
            transparent_hugepage_mode="unknown", privileged_tuning_performed=False,
            gpu_backend="disabled", default_arithmetic_mode=ARITHMETIC_INTEGER_ORACLE,
            user_space_advice=(),
            missing_v1_flags=(), missing_v3_flags=(),
        )
        with self.assertRaises(RuntimeError):
            require_cpu_host(HostPreflight(**base))
        base["linux"] = True
        base["gpu_backend"] = "cuda"
        with self.assertRaises(RuntimeError):
            require_cpu_host(HostPreflight(**base))


if __name__ == "__main__":
    unittest.main()
