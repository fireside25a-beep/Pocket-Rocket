CC ?= cc
PKG_CONFIG ?= pkg-config
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Wstrict-prototypes
CFLAGS += -D_GNU_SOURCE
GTK4_AVAILABLE := $(shell $(PKG_CONFIG) --exists gtk4 2>/dev/null && echo yes)

.PHONY: all check clean

ifeq ($(GTK4_AVAILABLE),yes)
GTK4_FLAGS := $(shell $(PKG_CONFIG) --cflags --libs gtk4)

all: pocket_rocket_workspace

pocket_rocket_workspace: pocket_rocket_workspace.c
	$(CC) $(CFLAGS) pocket_rocket_workspace.c $(GTK4_FLAGS) -o $@

check: pocket_rocket_workspace
	@test -x pocket_rocket_workspace
else

all check:
	@echo "GTK4 development files are unavailable; install gtk4 and pkg-config, then rerun make -C ui"
	@exit 2
endif

clean:
	rm -f pocket_rocket_workspace
