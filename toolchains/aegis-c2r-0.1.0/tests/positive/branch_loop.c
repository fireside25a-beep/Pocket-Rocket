#include <stdio.h>
int main() {
    int i = 0;
    int sum = 0;
    while (i < 5) {
        if (i == 3) {
            sum = sum + 10;
        } else {
            sum = sum + i;
        }
        i = i + 1;
    }
    printf("%d\n", sum);
    return 0;
}
