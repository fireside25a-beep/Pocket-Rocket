#include <stdio.h>
int muladd(int a, int b, int c) {
    return a * b + c;
}
int twice(int x) {
    return muladd(x, 2, 0);
}
int main() {
    printf("%d\n", twice(21));
    return 0;
}
