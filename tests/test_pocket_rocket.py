import unittest

from neuro_inverse.pocket_rocket import (
    DEEPSEEK_V4_FLASH,
    DEEPSEEK_V4_FLASH_GEOMETRY,
    GIB,
    ModelGeometry,
    estimate_deepseek_v4_flash,
    strict_16gb_admission,
    ds4_flash_cpu_context_memory,
    quantized_payload_bytes,
    scale_metadata_bytes,
)


class PocketRocketFeasibilityTests(unittest.TestCase):
    def test_deepseek_geometry_and_provenance_are_explicit(self):
        self.assertEqual(DEEPSEEK_V4_FLASH.model_id, "deepseek-ai/DeepSeek-V4-Flash")
        self.assertEqual(DEEPSEEK_V4_FLASH.weight_repository, "antirez/deepseek-v4-gguf")
        self.assertEqual(DEEPSEEK_V4_FLASH.weight_size_bytes, 86_720_111_488)
        self.assertEqual((DEEPSEEK_V4_FLASH_GEOMETRY.expert_count,
                          DEEPSEEK_V4_FLASH_GEOMETRY.active_experts,
                          DEEPSEEK_V4_FLASH_GEOMETRY.layers), (256, 6, 43))
        self.assertIsNone(DEEPSEEK_V4_FLASH_GEOMETRY.total_params)
        self.assertEqual((DEEPSEEK_V4_FLASH_GEOMETRY.hidden_size,
                          DEEPSEEK_V4_FLASH_GEOMETRY.kv_heads,
                          DEEPSEEK_V4_FLASH_GEOMETRY.head_dim), (4096, 1, 512))

    def test_storage_and_active_ram_are_separate(self):
        estimate = estimate_deepseek_v4_flash(cache_budget_bytes=1 * GIB, context_tokens=512)
        self.assertEqual(estimate.full_ssd_bytes, DEEPSEEK_V4_FLASH.weight_size_bytes)
        self.assertEqual(estimate.full_weight_scale_metadata_bytes, 0)
        self.assertEqual(estimate.active_ram_basis, "ROUTED_GGUF_BYTE_PROXY; NOT A PARAMETER COUNT")
        self.assertGreater(estimate.active_weight_ram_bytes, 0)
        self.assertGreater(estimate.kv_cache_bytes, 0)
        self.assertEqual(estimate.context_memory_basis, "PINNED_DS4_FLASH_CPU_COMPRESSED_KV_V1")
        self.assertEqual(estimate.working_set_ram_bytes,
                         estimate.active_weight_ram_bytes + estimate.context_buffer_bytes + 1 * GIB)

    def test_exact_ds4_context_ladder_is_nonzero_and_monotonic(self):
        expected = {
            512: 18_508_434,
            2048: 39_647_250,
            4096: 67_832_338,
            8192: 124_202_514,
        }
        previous = 0
        for context, total in expected.items():
            memory = ds4_flash_cpu_context_memory(context)
            self.assertEqual(memory.total_bytes, total)
            self.assertEqual(memory.raw_rows, 128)
            self.assertGreater(memory.total_bytes, previous)
            previous = memory.total_bytes

    def test_product_context_accounting_costs_about_118_mib(self):
        estimate = estimate_deepseek_v4_flash(cache_budget_bytes=1 * GIB,
                                              context_tokens=8192)
        self.assertEqual(estimate.context_buffer_bytes, 124_202_514)
        self.assertEqual(estimate.kv_bytes_per_element, 4)
        self.assertGreater(estimate.kv_cache_bytes, 0)
        self.assertTrue(strict_16gb_admission(estimate)["admitted"])

    def test_budget_scenarios_are_byte_accounted(self):
        geometry = ModelGeometry(total_params=25_000_000_000, active_params=20_000_000_000,
                                 source_bytes=None, hidden_size=64, kv_heads=1, head_dim=64)
        estimate = estimate_deepseek_v4_flash(
            geometry, bits_per_param=8, cache_budget_bytes=4 * GIB, context_tokens=32768,
            resident_common_params=1_000_000,
        )
        by_budget = {item.budget_gib: item for item in estimate.budgets}
        self.assertFalse(by_budget[16].fits)
        self.assertFalse(by_budget[20].fits)
        self.assertTrue(by_budget[32].fits)
        self.assertEqual(by_budget[16].margin_bytes, 16 * GIB - estimate.working_set_ram_bytes)

    def test_invalid_and_impossible_inputs_rejected(self):
        with self.assertRaises(ValueError):
            estimate_deepseek_v4_flash(bits_per_param=0)
        with self.assertRaises(ValueError):
            estimate_deepseek_v4_flash(block_size=0)
        with self.assertRaises(ValueError):
            estimate_deepseek_v4_flash(ModelGeometry(total_params=10, active_params=2, source_bytes=None), resident_common_params=3)
        with self.assertRaises(ValueError):
            estimate_deepseek_v4_flash(ModelGeometry(total_params=1, active_params=2, source_bytes=None))
        with self.assertRaises(ValueError):
            estimate_deepseek_v4_flash(context_tokens=-1)
        with self.assertRaises(ValueError):
            estimate_deepseek_v4_flash(kv_bytes_per_element=2)

    def test_strict_ram_admission_fails_closed(self):
        estimate = estimate_deepseek_v4_flash(cache_budget_bytes=1 * GIB, context_tokens=512)
        accepted = strict_16gb_admission(estimate)
        self.assertTrue(accepted["admitted"])
        rejected = strict_16gb_admission(estimate, available_bytes=1 * GIB)
        self.assertFalse(rejected["admitted"])
        self.assertLess(rejected["margin_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
