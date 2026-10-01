#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>

#define CONFIG_MQTT_VERSION_5_0 1
#define CONFIG_MQTT_USER_PROPERTIES_MAX 5
#define CONFIG_MQTT_SUBSCRIPTION_ID_PROPERTIES_MAX 5

#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define LOG_MODULE_REGISTER(...)
#define NET_DBG(...)
#define NET_ERR(...)
#define ARG_UNUSED(x) (void)(x)

#define sys_get_be16(ptr) (uint16_t)(((uint16_t)((uint8_t *)(ptr))[0] << 8) | ((uint8_t *)(ptr))[1])
#define sys_get_be32(ptr) (((uint32_t)sys_get_be16(ptr) << 16) | sys_get_be16((uint8_t *)(ptr) + 2))

struct mqtt_utf8 {
	const uint8_t *utf8;
	uint32_t size;
};

struct mqtt_binstr {
	const uint8_t *data;
	uint32_t len;
};

struct mqtt_utf8_pair {
	struct mqtt_utf8 name;
	struct mqtt_utf8 value;
};

struct buf_ctx {
	uint8_t *cur;
	uint8_t *end;
};

#define MQTT_PROP_PAYLOAD_FORMAT_INDICATOR          0x01
#define MQTT_PROP_MESSAGE_EXPIRY_INTERVAL           0x02
#define MQTT_PROP_CONTENT_TYPE                      0x03
#define MQTT_PROP_RESPONSE_TOPIC                    0x08
#define MQTT_PROP_CORRELATION_DATA                  0x09
#define MQTT_PROP_SUBSCRIPTION_IDENTIFIER           0x0B
#define MQTT_PROP_SESSION_EXPIRY_INTERVAL           0x11
#define MQTT_PROP_ASSIGNED_CLIENT_IDENTIFIER        0x12
#define MQTT_PROP_SERVER_KEEP_ALIVE                 0x13
#define MQTT_PROP_AUTHENTICATION_METHOD             0x15
#define MQTT_PROP_AUTHENTICATION_DATA               0x16
#define MQTT_PROP_REQUEST_PROBLEM_INFORMATION       0x17
#define MQTT_PROP_WILL_DELAY_INTERVAL               0x18
#define MQTT_PROP_REQUEST_RESPONSE_INFORMATION      0x19
#define MQTT_PROP_RESPONSE_INFORMATION              0x1A
#define MQTT_PROP_SERVER_REFERENCE                  0x1C
#define MQTT_PROP_REASON_STRING                     0x1F
#define MQTT_PROP_RECEIVE_MAXIMUM                   0x21
#define MQTT_PROP_TOPIC_ALIAS_MAXIMUM               0x22
#define MQTT_PROP_TOPIC_ALIAS                       0x23
#define MQTT_PROP_MAXIMUM_QOS                       0x24
#define MQTT_PROP_RETAIN_AVAILABLE                  0x25
#define MQTT_PROP_USER_PROPERTY                     0x26
#define MQTT_PROP_MAXIMUM_PACKET_SIZE               0x27
#define MQTT_PROP_WILDCARD_SUBSCRIPTION_AVAILABLE   0x28
#define MQTT_PROP_SUBSCRIPTION_IDENTIFIER_AVAILABLE 0x29
#define MQTT_PROP_SHARED_SUBSCRIPTION_AVAILABLE     0x2A

#define MQTT_MAX_PAYLOAD_SIZE 0x0FFFFFFF
#define MQTT_MAX_LENGTH_BYTES 4
#define MQTT_LENGTH_VALUE_MASK 0x7F
#define MQTT_LENGTH_CONTINUATION_BIT 0x80
#define MQTT_LENGTH_SHIFT 7

#define GET_UT8STR_BUFFER_SIZE(STR) (sizeof(uint16_t) + (STR)->size)
#define GET_BINSTR_BUFFER_SIZE(STR) (sizeof(uint16_t) + (STR)->len)

#include "extracted.c"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    struct buf_ctx buf;
    buf.cur = (uint8_t *)data;
    buf.end = (uint8_t *)data + size;

    struct property_decoder props[2];
    uint32_t val1;
    bool found1 = false;
    props[0].type = MQTT_PROP_SESSION_EXPIRY_INTERVAL;
    props[0].data = &val1;
    props[0].found = &found1;

    struct mqtt_utf8 str2;
    bool found2 = false;
    props[1].type = MQTT_PROP_REASON_STRING;
    props[1].data = &str2;
    props[1].found = &found2;

    properties_decode(props, ARRAY_SIZE(props), &buf);

    return 0;
}
