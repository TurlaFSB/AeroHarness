#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

typedef uint8_t u8_t;
typedef uint16_t u16_t;
typedef uint32_t u32_t;
typedef int32_t s32_t;

#define EINVAL 22
#define EAGAIN 11
#define ENOMEM 12
#define ENOTCONN 107

#define MQTT_MAX_LENGTH_BYTES 4
#define MQTT_LENGTH_VALUE_MASK 0x7F
#define MQTT_LENGTH_CONTINUATION_BIT 0x80
#define MQTT_LENGTH_SHIFT 7
#define MQTT_MAX_PAYLOAD_SIZE 0x0FFFFFFF
#define MQTT_FIXED_HEADER_MIN_SIZE 2
#define MQTT_PKT_TYPE_PUBLISH 0x30
#define MQTT_HEADER_DUP_MASK 0x08
#define MQTT_HEADER_QOS_MASK 0x06
#define MQTT_HEADER_RETAIN_MASK 0x01
#define MQTT_QOS_0_AT_MOST_ONCE 0

#define MQTT_PKT_TYPE_CONNACK 0x20
#define MQTT_PKT_TYPE_PUBACK 0x40
#define MQTT_PKT_TYPE_PUBREC 0x50
#define MQTT_PKT_TYPE_PUBREL 0x60
#define MQTT_PKT_TYPE_PUBCOMP 0x70
#define MQTT_PKT_TYPE_SUBACK 0x90
#define MQTT_PKT_TYPE_UNSUBACK 0xB0
#define MQTT_PKT_TYPE_PINGRSP 0xD0

#define MQTT_CONNECTION_ACCEPTED 0
#define MQTT_VERSION_3_1_1 4
#define MQTT_CONNACK_FLAG_SESSION_PRESENT 1
enum mqtt_conn_return_code { A };

#define MQTT_TRC(...)
#define MQTT_ERR(...)
#define MQTT_SET_STATE(...)

struct buf_ctx {
	u8_t *cur;
	u8_t *end;
};

struct mqtt_utf8 {
    const u8_t *utf8;
    u32_t size;
};

struct mqtt_binstr {
    const u8_t *data;
    u32_t len;
};

struct mqtt_suback_param { u16_t message_id; struct mqtt_binstr return_codes; };
struct mqtt_unsuback_param { u16_t message_id; };

struct mqtt_topic {
    struct mqtt_utf8 topic;
    u8_t qos;
};

struct mqtt_publish_message {
    struct mqtt_topic topic;
    struct mqtt_binstr payload;
};

struct mqtt_publish_param {
    struct mqtt_publish_message message;
    u16_t message_id;
    u8_t dup_flag;
    u8_t retain_flag;
};

struct mqtt_connack_param {
    u8_t session_present_flag;
    u8_t return_code;
};
struct mqtt_puback_param { u16_t message_id; };
struct mqtt_pubrec_param { u16_t message_id; };
struct mqtt_pubrel_param { u16_t message_id; };
struct mqtt_pubcomp_param { u16_t message_id; };

enum mqtt_evt_type {
    MQTT_EVT_CONNACK,
    MQTT_EVT_PUBLISH,
    MQTT_EVT_PUBACK,
    MQTT_EVT_PUBREC,
    MQTT_EVT_PUBREL,
    MQTT_EVT_PUBCOMP,
    MQTT_EVT_SUBACK,
    MQTT_EVT_UNSUBACK,
    MQTT_EVT_PINGRESP
};

struct mqtt_evt {
    enum mqtt_evt_type type;
    union {
        struct mqtt_connack_param connack;
        struct mqtt_publish_param publish;
        struct mqtt_puback_param puback;
        struct mqtt_pubrec_param pubrec;
        struct mqtt_pubrel_param pubrel;
        struct mqtt_pubcomp_param pubcomp;
        struct mqtt_suback_param suback;
        struct mqtt_unsuback_param unsuback;
    } param;
    int result;
};

struct mqtt_client;
typedef void (*mqtt_evt_cb_t)(struct mqtt_client *client, const struct mqtt_evt *evt);

enum mqtt_state {
    MQTT_STATE_CONNECTED,
    MQTT_STATE_DISCONNECTED
};

struct mqtt_client {
    u8_t *rx_buf;
    u32_t rx_buf_size;
    mqtt_evt_cb_t evt_cb;
    struct {
        u32_t rx_buf_datalen;
        u32_t remaining_payload;
    } internal;
    u8_t protocol_version;
    int unacked_ping;
    enum mqtt_state state;
};

void event_notify(struct mqtt_client *client, const struct mqtt_evt *evt) {
    if (client->evt_cb) {
        client->evt_cb(client, evt);
    }
}

int mqtt_transport_read(struct mqtt_client *c, u8_t *data, int len, bool block) {
    return -EAGAIN;
}

#include "mqtt_decoder_vuln.c"
#include "mqtt_rx_vuln.c"

void dummy_cb(struct mqtt_client *client, const struct mqtt_evt *evt) {
    if (evt->type == MQTT_EVT_PUBLISH) {
        u32_t payload_len = evt->param.publish.message.payload.len;
        printf("PUBLISH EVENT! payload_len = %u\n", payload_len);
        
        char *app_buffer = malloc(1024);
        if (app_buffer) {
            memcpy(app_buffer, client->rx_buf, payload_len);
            free(app_buffer);
        }
    }
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size > 4096) return 0;
    u8_t rx_buf[4096];
    memcpy(rx_buf, data, size);

    struct mqtt_client client;
    memset(&client, 0, sizeof(client));
    client.rx_buf = rx_buf;
    client.rx_buf_size = sizeof(rx_buf);
    client.internal.rx_buf_datalen = size;
    client.evt_cb = dummy_cb;
    client.state = MQTT_STATE_CONNECTED;

    mqtt_handle_rx(&client);

    return 0;
}
