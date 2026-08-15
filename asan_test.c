#include <stdlib.h>
int main() {
    char *buf = malloc(10);
    buf[10] = 'x'; // deliberate out-of-bounds write
    free(buf);
    return 0;
}
