#include <stdio.h>
#include <assert.h>
int main() {
    int x = 3;
    int y = 4;
    assert(x < y && y != 0);
    printf("%d\n", (x == 3) || (y == 5));
    printf("%d\n", !0);
    return 0;
}
