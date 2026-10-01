
#define MAGIC 0xA55A
#define REG_STATUS 0x40001000
typedef struct { int a; } my_ctx;
void target_func(my_ctx *ctx, uint8_t *data, size_t len) {
    memcpy(ctx, data, len);
}
