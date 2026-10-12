.PHONY: all setup test regressions native native-source frontend matrix static proofs foundations foundations-native reproduce check maintainer-check verify manifest release clean

all: setup

setup:
	./scripts/setup.sh

regressions: setup
	./scripts/test.sh

foundations-native: setup
	./scripts/test_foundations.sh

frontend: setup
	./tests/selfhost/full/test_full_frontend.sh

native: setup
	AEGIS_NATIVE_MODE=shipped ./tests/native/test_native.sh

native-source: setup
	AEGIS_NATIVE_MODE=source ./tests/native/test_native.sh

reproduce: setup
	./scripts/reproduce_toolchain.sh

foundations: foundations-native frontend

matrix: setup
	./scripts/test_loop_matrix.sh

static: setup
	./scripts/static_check.sh

proofs: matrix
	cd proofs/loops && sha256sum -c SHA256SUMS.txt

test: regressions native matrix

verify: setup
	./scripts/verify_release.sh

manifest:
	./scripts/update_manifest.sh

check: test static verify

maintainer-check: check native-source foundations reproduce

release: maintainer-check
	./scripts/package_release.sh

clean:
	rm -rf build dist
