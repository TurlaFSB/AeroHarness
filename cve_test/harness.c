#include <stdint.h>
#include <stddef.h>
#include <errno.h>

typedef uint8_t u8_t;
typedef uint16_t u16_t;
typedef uint32_t u32_t;

struct buf_ctx {
	u8_t *cur;
	u8_t *end;
};

#define MQTT_MAX_LENGTH_BYTES 4
#define MQTT_LENGTH_VALUE_MASK 0x7F
#define MQTT_LENGTH_CONTINUATION_BIT 0x80
#define MQTT_LENGTH_SHIFT 7

#define MQTT_TRC(...)

int packet_length_decode(struct buf_ctx *buf, u32_t *length)
{
	u8_t shift = 0U;
	u8_t bytes = 0U;

	*length = 0U;
	do {
		if (bytes > MQTT_MAX_LENGTH_BYTES) {
			return -EINVAL;
		}

		if (buf->cur >= buf->end) {
			return -EAGAIN;
		}

		*length += ((u32_t)*(buf->cur) & MQTT_LENGTH_VALUE_MASK)
								<< shift;
		shift += MQTT_LENGTH_SHIFT;
		bytes++;
	} while ((*(buf->cur++) & MQTT_LENGTH_CONTINUATION_BIT) != 0U);

	MQTT_TRC("length:0x%08x", *length);

	return 0;
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    struct buf_ctx buf;
    buf.cur = (u8_t *)data;
    buf.end = (u8_t *)data + size;
    u32_t length;
    packet_length_decode(&buf, &length);
    return 0;
}
