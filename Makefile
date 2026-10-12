.PHONY: test ui-test proof benchmark agent-fabric-benchmark ternary-benchmark pocket-benchmark page-codec-benchmark pocket-estimate native-test doctor archive-check surface-audit release ds4-install gate-16gb gate-context-ladder

test:
	PYTHONPATH=src python -m unittest discover -s tests -v
	python ui/test_workspace_source.py -v
	sh -n scripts/run_user_daemon.sh
	python scripts/runtime_surface_audit.py

ui-test:
	python ui/test_workspace_source.py -v

proof:
	PYTHONPATH=src python experiments/synthetic_breakthrough.py

benchmark:
	PYTHONPATH=src python benchmarks/router_bench.py --experts 10000 --queries 100

agent-fabric-benchmark:
	PYTHONPATH=src python benchmarks/agent_fabric_bench.py --queries 1000

ternary-benchmark:
	PYTHONPATH=src python benchmarks/ternary_bench.py --pairs 10000 --repeats 7

pocket-benchmark:
	PYTHONPATH=src python benchmarks/pocket_pack_bench.py --megabytes 2 --random

page-codec-benchmark:
	PYTHONPATH=src python benchmarks/page_codec_bench.py --megabytes 2 --repeats 2

pocket-estimate:
	PYTHONPATH=src python scripts/pocket_rocket_estimate.py --bits-per-param 4

native-test:
	$(MAKE) -C native clean
	$(MAKE) -C native test test-asan test-ubsan
	$(MAKE) -C native clean

doctor:
	PYTHONPATH=src python -m neuro_inverse doctor

archive-check:
	python scripts/archive_check.py .

surface-audit:
	python scripts/runtime_surface_audit.py

release:
	python scripts/build_release.py

ds4-install:
	python scripts/install_ds4.py

gate-16gb:
	python scripts/run_16gb_gate.py

gate-context-ladder:
	python scripts/run_context_ladder.py

.PHONY: restore-toolchain-modes aegis-test aegis-suite-check aegis-full-test c2r-test qualification

restore-toolchain-modes:
	python scripts/restore_toolchain_modes.py

aegis-test: restore-toolchain-modes
	PYTHONPATH=src python -m unittest tests.test_aegis_runtime tests.test_aegis_c2r_live -v

aegis-suite-check: restore-toolchain-modes
	$(MAKE) -C toolchains/aegis-language-suite-2.4.3 check

aegis-full-test: aegis-test aegis-suite-check
	$(MAKE) -C toolchains/aegis-language-suite-2.4.3 maintainer-check

c2r-test: restore-toolchain-modes
	$(MAKE) -C toolchains/aegis-c2r-0.1.0 check

qualification: restore-toolchain-modes test native-test aegis-test aegis-suite-check c2r-test
