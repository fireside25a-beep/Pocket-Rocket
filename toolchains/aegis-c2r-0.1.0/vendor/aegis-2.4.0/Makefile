.PHONY: bootstrap toolchain test check clean release

bootstrap:
	./scripts/bootstrap.sh

toolchain: bootstrap
	./scripts/build_toolchain.sh

test: toolchain
	./scripts/test.sh

check: test
	./scripts/verify_no_legacy_brand.sh

release: check
	./scripts/package_release.sh

clean:
	rm -rf build
