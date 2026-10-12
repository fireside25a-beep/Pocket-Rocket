CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Werror
CPPFLAGS ?= -I.
LDLIBS ?= -lm

ifneq ($(wildcard /usr/include/zlib.h),)
POCKET_CPPFLAGS += -DNR_HAVE_ZLIB=1
POCKET_LDLIBS += -lz
else
$(info zlib headers unavailable: raw Pocket Rocket tests only)
endif

CORE_SOURCES = nprq.c
ENVELOPE_SOURCES = nprq.c envelope.c
TEST_BIN = test_native
ENVELOPE_TEST_BIN = test_envelope
POCKET_TEST_BIN = test_pocket_rocket
FLAT32_TEST_BIN = test_flat32
FLAT32_DICT_TEST_BIN = test_flat32_dict
BINARY32_TEST_BIN = test_binary32
T39_LBIT_TEST_BIN = test_t39_lbit
TERNARY_TEST_BIN = test_ternary_core
TCAM_TEST_BIN = test_ternary_tcam
SSM_TEST_BIN = test_ternary_ssm
HAMMING_TEST_BIN = test_hamming_router

.PHONY: all test test-avx2 test-asan test-ubsan test-clang clean

all: test

test: $(TEST_BIN) $(ENVELOPE_TEST_BIN) $(POCKET_TEST_BIN) $(FLAT32_TEST_BIN) $(FLAT32_DICT_TEST_BIN) $(BINARY32_TEST_BIN) $(T39_LBIT_TEST_BIN) $(TERNARY_TEST_BIN) $(TCAM_TEST_BIN) $(SSM_TEST_BIN) $(HAMMING_TEST_BIN)
	./$(TEST_BIN)
	./$(ENVELOPE_TEST_BIN)
	./$(POCKET_TEST_BIN)
	./$(FLAT32_TEST_BIN)
	./$(FLAT32_DICT_TEST_BIN)
	./$(BINARY32_TEST_BIN)
	./$(T39_LBIT_TEST_BIN)
	./$(TERNARY_TEST_BIN)
	./$(TCAM_TEST_BIN)
	./$(SSM_TEST_BIN)
	./$(HAMMING_TEST_BIN)

$(TEST_BIN): $(CORE_SOURCES) test_native.c nprq.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(CORE_SOURCES) test_native.c $(LDLIBS) -o $@

$(ENVELOPE_TEST_BIN): $(ENVELOPE_SOURCES) envelope.h nprq.h test_envelope.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(ENVELOPE_SOURCES) test_envelope.c $(LDLIBS) -o $@

$(POCKET_TEST_BIN): nprq.c pocket_rocket.c pocket_rocket.h nprq.h test_pocket_rocket.c
	$(CC) $(CPPFLAGS) $(POCKET_CPPFLAGS) $(CFLAGS) nprq.c pocket_rocket.c test_pocket_rocket.c $(LDLIBS) $(POCKET_LDLIBS) -o $@

$(FLAT32_TEST_BIN): nprq.c flat32.c flat32.h nprq.h test_flat32.c
	$(CC) $(CPPFLAGS) $(CFLAGS) nprq.c flat32.c test_flat32.c $(LDLIBS) -o $@

$(FLAT32_DICT_TEST_BIN): nprq.c flat32.c flat32_dict.c flat32.h flat32_dict.h nprq.h test_flat32_dict.c
	$(CC) $(CPPFLAGS) $(CFLAGS) nprq.c flat32.c flat32_dict.c test_flat32_dict.c $(LDLIBS) -o $@

$(BINARY32_TEST_BIN): binary32.c binary32.h test_binary32.c
	$(CC) $(CPPFLAGS) $(CFLAGS) binary32.c test_binary32.c $(LDLIBS) -o $@

$(T39_LBIT_TEST_BIN): t39_lbit.c t39_lbit.h test_t39_lbit.c
	$(CC) $(CPPFLAGS) $(CFLAGS) t39_lbit.c test_t39_lbit.c $(LDLIBS) -o $@

$(TERNARY_TEST_BIN): ternary_core.c ternary_core.h test_ternary_core.c
	$(CC) $(CPPFLAGS) $(CFLAGS) ternary_core.c test_ternary_core.c $(LDLIBS) -o $@

$(TCAM_TEST_BIN): ternary_core.c ternary_core.h ternary_tcam.c ternary_tcam.h test_ternary_tcam.c
	$(CC) $(CPPFLAGS) $(CFLAGS) ternary_core.c ternary_tcam.c test_ternary_tcam.c $(LDLIBS) -o $@

$(SSM_TEST_BIN): binary32.c binary32.h ternary_ssm.c ternary_ssm.h test_ternary_ssm.c
	$(CC) $(CPPFLAGS) $(CFLAGS) binary32.c ternary_ssm.c test_ternary_ssm.c $(LDLIBS) -o $@

test-avx2:
	$(CC) $(CPPFLAGS) $(CFLAGS) -mavx2 -mpopcnt ternary_core.c ternary_tcam.c test_ternary_tcam.c $(LDLIBS) -o $(TCAM_TEST_BIN)-avx2
	./$(TCAM_TEST_BIN)-avx2
	rm -f $(TCAM_TEST_BIN)-avx2

$(HAMMING_TEST_BIN): hamming_router.c hamming_router.h test_hamming_router.c
	$(CC) $(CPPFLAGS) $(CFLAGS) hamming_router.c test_hamming_router.c $(LDLIBS) -o $@

test-asan:
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer $(CORE_SOURCES) test_native.c $(LDLIBS) -o $(TEST_BIN)-asan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer $(ENVELOPE_SOURCES) test_envelope.c $(LDLIBS) -o $(ENVELOPE_TEST_BIN)-asan
	$(CC) $(CPPFLAGS) $(POCKET_CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer nprq.c pocket_rocket.c test_pocket_rocket.c $(LDLIBS) $(POCKET_LDLIBS) -o $(POCKET_TEST_BIN)-asan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer nprq.c flat32.c test_flat32.c $(LDLIBS) -o $(FLAT32_TEST_BIN)-asan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer nprq.c flat32.c flat32_dict.c test_flat32_dict.c $(LDLIBS) -o $(FLAT32_DICT_TEST_BIN)-asan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer binary32.c test_binary32.c $(LDLIBS) -o $(BINARY32_TEST_BIN)-asan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer t39_lbit.c test_t39_lbit.c $(LDLIBS) -o $(T39_LBIT_TEST_BIN)-asan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer ternary_core.c test_ternary_core.c $(LDLIBS) -o $(TERNARY_TEST_BIN)-asan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer ternary_core.c ternary_tcam.c test_ternary_tcam.c $(LDLIBS) -o $(TCAM_TEST_BIN)-asan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer binary32.c ternary_ssm.c test_ternary_ssm.c $(LDLIBS) -o $(SSM_TEST_BIN)-asan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=address -fno-omit-frame-pointer hamming_router.c test_hamming_router.c $(LDLIBS) -o $(HAMMING_TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(ENVELOPE_TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(POCKET_TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(FLAT32_TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(FLAT32_DICT_TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(BINARY32_TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(T39_LBIT_TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(TERNARY_TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(TCAM_TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(SSM_TEST_BIN)-asan
	ASAN_OPTIONS=detect_leaks=0 ./$(HAMMING_TEST_BIN)-asan
	rm -f $(TEST_BIN)-asan $(ENVELOPE_TEST_BIN)-asan $(POCKET_TEST_BIN)-asan $(FLAT32_TEST_BIN)-asan $(FLAT32_DICT_TEST_BIN)-asan $(BINARY32_TEST_BIN)-asan $(T39_LBIT_TEST_BIN)-asan $(TERNARY_TEST_BIN)-asan $(TCAM_TEST_BIN)-asan $(SSM_TEST_BIN)-asan $(HAMMING_TEST_BIN)-asan

test-ubsan:
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer $(CORE_SOURCES) test_native.c $(LDLIBS) -o $(TEST_BIN)-ubsan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer $(ENVELOPE_SOURCES) test_envelope.c $(LDLIBS) -o $(ENVELOPE_TEST_BIN)-ubsan
	$(CC) $(CPPFLAGS) $(POCKET_CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer nprq.c pocket_rocket.c test_pocket_rocket.c $(LDLIBS) $(POCKET_LDLIBS) -o $(POCKET_TEST_BIN)-ubsan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer nprq.c flat32.c test_flat32.c $(LDLIBS) -o $(FLAT32_TEST_BIN)-ubsan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer nprq.c flat32.c flat32_dict.c test_flat32_dict.c $(LDLIBS) -o $(FLAT32_DICT_TEST_BIN)-ubsan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer binary32.c test_binary32.c $(LDLIBS) -o $(BINARY32_TEST_BIN)-ubsan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer t39_lbit.c test_t39_lbit.c $(LDLIBS) -o $(T39_LBIT_TEST_BIN)-ubsan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer ternary_core.c test_ternary_core.c $(LDLIBS) -o $(TERNARY_TEST_BIN)-ubsan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer ternary_core.c ternary_tcam.c test_ternary_tcam.c $(LDLIBS) -o $(TCAM_TEST_BIN)-ubsan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer binary32.c ternary_ssm.c test_ternary_ssm.c $(LDLIBS) -o $(SSM_TEST_BIN)-ubsan
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -g -fsanitize=undefined -fno-omit-frame-pointer hamming_router.c test_hamming_router.c $(LDLIBS) -o $(HAMMING_TEST_BIN)-ubsan
	chmod u+x $(TEST_BIN)-ubsan $(ENVELOPE_TEST_BIN)-ubsan $(POCKET_TEST_BIN)-ubsan $(FLAT32_TEST_BIN)-ubsan $(FLAT32_DICT_TEST_BIN)-ubsan $(BINARY32_TEST_BIN)-ubsan $(T39_LBIT_TEST_BIN)-ubsan $(TERNARY_TEST_BIN)-ubsan $(TCAM_TEST_BIN)-ubsan $(SSM_TEST_BIN)-ubsan $(HAMMING_TEST_BIN)-ubsan
	./$(TEST_BIN)-ubsan
	./$(ENVELOPE_TEST_BIN)-ubsan
	./$(POCKET_TEST_BIN)-ubsan
	./$(FLAT32_TEST_BIN)-ubsan
	./$(FLAT32_DICT_TEST_BIN)-ubsan
	./$(BINARY32_TEST_BIN)-ubsan
	./$(T39_LBIT_TEST_BIN)-ubsan
	./$(TERNARY_TEST_BIN)-ubsan
	./$(TCAM_TEST_BIN)-ubsan
	./$(SSM_TEST_BIN)-ubsan
	./$(HAMMING_TEST_BIN)-ubsan
	rm -f $(TEST_BIN)-ubsan $(ENVELOPE_TEST_BIN)-ubsan $(POCKET_TEST_BIN)-ubsan $(FLAT32_TEST_BIN)-ubsan $(FLAT32_DICT_TEST_BIN)-ubsan $(BINARY32_TEST_BIN)-ubsan $(T39_LBIT_TEST_BIN)-ubsan $(TERNARY_TEST_BIN)-ubsan $(TCAM_TEST_BIN)-ubsan $(SSM_TEST_BIN)-ubsan $(HAMMING_TEST_BIN)-ubsan

test-clang:
	clang $(CPPFLAGS) $(CFLAGS) $(CORE_SOURCES) test_native.c $(LDLIBS) -o $(TEST_BIN)-clang
	clang $(CPPFLAGS) $(CFLAGS) $(ENVELOPE_SOURCES) test_envelope.c $(LDLIBS) -o $(ENVELOPE_TEST_BIN)-clang
	clang $(CPPFLAGS) $(POCKET_CPPFLAGS) $(CFLAGS) nprq.c pocket_rocket.c test_pocket_rocket.c $(LDLIBS) $(POCKET_LDLIBS) -o $(POCKET_TEST_BIN)-clang
	clang $(CPPFLAGS) $(CFLAGS) nprq.c flat32.c test_flat32.c $(LDLIBS) -o $(FLAT32_TEST_BIN)-clang
	clang $(CPPFLAGS) $(CFLAGS) nprq.c flat32.c flat32_dict.c test_flat32_dict.c $(LDLIBS) -o $(FLAT32_DICT_TEST_BIN)-clang
	clang $(CPPFLAGS) $(CFLAGS) binary32.c test_binary32.c $(LDLIBS) -o $(BINARY32_TEST_BIN)-clang
	clang $(CPPFLAGS) $(CFLAGS) t39_lbit.c test_t39_lbit.c $(LDLIBS) -o $(T39_LBIT_TEST_BIN)-clang
	clang $(CPPFLAGS) $(CFLAGS) ternary_core.c test_ternary_core.c $(LDLIBS) -o $(TERNARY_TEST_BIN)-clang
	clang $(CPPFLAGS) $(CFLAGS) ternary_core.c ternary_tcam.c test_ternary_tcam.c $(LDLIBS) -o $(TCAM_TEST_BIN)-clang
	clang $(CPPFLAGS) $(CFLAGS) binary32.c ternary_ssm.c test_ternary_ssm.c $(LDLIBS) -o $(SSM_TEST_BIN)-clang
	clang $(CPPFLAGS) $(CFLAGS) hamming_router.c test_hamming_router.c $(LDLIBS) -o $(HAMMING_TEST_BIN)-clang
	./$(TEST_BIN)-clang
	./$(ENVELOPE_TEST_BIN)-clang
	./$(POCKET_TEST_BIN)-clang
	./$(FLAT32_TEST_BIN)-clang
	./$(FLAT32_DICT_TEST_BIN)-clang
	./$(BINARY32_TEST_BIN)-clang
	./$(T39_LBIT_TEST_BIN)-clang
	./$(TERNARY_TEST_BIN)-clang
	./$(TCAM_TEST_BIN)-clang
	./$(SSM_TEST_BIN)-clang
	./$(HAMMING_TEST_BIN)-clang
	rm -f $(TEST_BIN)-clang $(ENVELOPE_TEST_BIN)-clang $(POCKET_TEST_BIN)-clang $(FLAT32_TEST_BIN)-clang $(FLAT32_DICT_TEST_BIN)-clang $(BINARY32_TEST_BIN)-clang $(T39_LBIT_TEST_BIN)-clang $(TERNARY_TEST_BIN)-clang $(TCAM_TEST_BIN)-clang $(SSM_TEST_BIN)-clang $(HAMMING_TEST_BIN)-clang $(TCAM_TEST_BIN)-avx2

clean:
	rm -f $(TEST_BIN) $(ENVELOPE_TEST_BIN) $(POCKET_TEST_BIN) $(FLAT32_TEST_BIN) $(FLAT32_DICT_TEST_BIN) $(BINARY32_TEST_BIN) $(T39_LBIT_TEST_BIN) $(TERNARY_TEST_BIN) $(TCAM_TEST_BIN) $(SSM_TEST_BIN) $(HAMMING_TEST_BIN) $(TEST_BIN)-asan $(ENVELOPE_TEST_BIN)-asan $(POCKET_TEST_BIN)-asan $(FLAT32_TEST_BIN)-asan $(FLAT32_DICT_TEST_BIN)-asan $(BINARY32_TEST_BIN)-asan $(T39_LBIT_TEST_BIN)-asan $(TERNARY_TEST_BIN)-asan $(TEST_BIN)-ubsan $(ENVELOPE_TEST_BIN)-ubsan $(POCKET_TEST_BIN)-ubsan $(FLAT32_TEST_BIN)-ubsan $(FLAT32_DICT_TEST_BIN)-ubsan $(BINARY32_TEST_BIN)-ubsan $(T39_LBIT_TEST_BIN)-ubsan $(TERNARY_TEST_BIN)-ubsan $(TEST_BIN)-clang $(ENVELOPE_TEST_BIN)-clang $(POCKET_TEST_BIN)-clang $(FLAT32_TEST_BIN)-clang $(FLAT32_DICT_TEST_BIN)-clang $(BINARY32_TEST_BIN)-clang $(T39_LBIT_TEST_BIN)-clang $(TERNARY_TEST_BIN)-clang .native_test_page.nprq .native_test_empty.nprq .native_pocket_empty.pkr .native_pocket_fixture.pkr .native_pocket_corrupt.pkr .native_pocket_truncated.pkr .native_pocket_trailing.pkr .native_pocket_bomb.pkr $(TCAM_TEST_BIN)-asan $(SSM_TEST_BIN)-asan $(HAMMING_TEST_BIN)-asan $(TCAM_TEST_BIN)-ubsan $(SSM_TEST_BIN)-ubsan $(HAMMING_TEST_BIN)-ubsan $(TCAM_TEST_BIN)-clang $(SSM_TEST_BIN)-clang $(HAMMING_TEST_BIN)-clang $(TCAM_TEST_BIN)-avx2
