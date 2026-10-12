CC ?= gcc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -Wformat=2
BIN := build/bin/aegis-c2r

.PHONY: all clean check test aegis-check analyzer sanitizer clang-check demo
all: $(BIN)

$(BIN): src/aegis_c2r.c include/aegis_c2r.h
	mkdir -p build/bin
	$(CC) $(CFLAGS) -Iinclude src/aegis_c2r.c -o $(BIN)

check:
	python3 tools/generate_semantic_vectors.py
	python3 tools/release_gate.py

analyzer:
	mkdir -p build
	gcc -std=c11 -O0 -Wall -Wextra -Wpedantic -Werror -fanalyzer -Iinclude -c src/aegis_c2r.c -o build/aegis_c2r.analyzer.o

clang-check:
	mkdir -p build/bin
	clang $(CFLAGS) -Iinclude src/aegis_c2r.c -o build/bin/aegis-c2r-clang

sanitizer:
	mkdir -p build/bin
	gcc -std=c11 -O1 -g -Wall -Wextra -Wpedantic -Werror -Wformat=2 -fsanitize=address,undefined -fno-omit-frame-pointer -Iinclude src/aegis_c2r.c -o build/bin/aegis-c2r-san

# Rebuild and run the exact clean Aegis 2.4.0 source-bootstrap gate.
aegis-check:
	$(MAKE) -C vendor/aegis-2.4.0 check

demo: $(BIN)
	mkdir -p build/demo
	$(BIN) translate tests/positive/basic.c -o build/demo/basic.rs --ast build/demo/basic.ast --proof build/demo/basic.json --aegis-prefix build/demo/basic

clean:
	rm -rf build
	$(MAKE) -C vendor/aegis-2.4.0 clean || true
