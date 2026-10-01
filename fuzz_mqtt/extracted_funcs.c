static int unpack_uint8(struct buf_ctx *buf, uint8_t *val)
{
	uint8_t *cur = buf->cur;
	uint8_t *end = buf->end;

	NET_DBG(">> cur:%p, end:%p", (void *)cur, (void *)end);

	if ((end - cur) < sizeof(uint8_t)) {
		return -EINVAL;
	}

	*val = cur[0];
	buf->cur = (cur + sizeof(uint8_t));

	NET_DBG("<< val:%02x", *val);

	return 0;
}

static int unpack_uint16(struct buf_ctx *buf, uint16_t *val)
{
	uint8_t *cur = buf->cur;
	uint8_t *end = buf->end;

	NET_DBG(">> cur:%p, end:%p", (void *)cur, (void *)end);

	if ((end - cur) < sizeof(uint16_t)) {
		return -EINVAL;
	}

	*val = sys_get_be16(cur);
	buf->cur = (cur + sizeof(uint16_t));

	NET_DBG("<< val:%04x", *val);

	return 0;
}

static int unpack_uint32(struct buf_ctx *buf, uint32_t *val)
{
	uint8_t *cur = buf->cur;
	uint8_t *end = buf->end;

	NET_DBG(">> cur:%p, end:%p", (void *)cur, (void *)end);

	if ((end - cur) < sizeof(uint32_t)) {
		return -EINVAL;
	}

	*val = sys_get_be32(cur);
	buf->cur = (cur + sizeof(uint32_t));

	NET_DBG("<< val:%08x", *val);

	return 0;
}

static int unpack_utf8_str(struct buf_ctx *buf, struct mqtt_utf8 *str)
{
	uint16_t utf8_strlen;
	int err_code;

	NET_DBG(">> cur:%p, end:%p", (void *)buf->cur, (void *)buf->end);

	err_code = unpack_uint16(buf, &utf8_strlen);
	if (err_code != 0) {
		return err_code;
	}

	if ((buf->end - buf->cur) < utf8_strlen) {
		return -EINVAL;
	}

	str->size = utf8_strlen;
	/* Zero length UTF8 strings permitted. */
	if (utf8_strlen) {
		/* Point to right location in buffer. */
		str->utf8 = buf->cur;
		buf->cur += utf8_strlen;
	} else {
		str->utf8 = NULL;
	}

	NET_DBG("<< str_size:%08x", (uint32_t)GET_UT8STR_BUFFER_SIZE(str));

	return 0;
}

static int unpack_binary_data(struct buf_ctx *buf, struct mqtt_binstr *bin)
{
	uint16_t len;
	int err;

	NET_DBG(">> cur:%p, end:%p", (void *)buf->cur, (void *)buf->end);

	err = unpack_uint16(buf, &len);
	if (err != 0) {
		return err;
	}

	if ((buf->end - buf->cur) < len) {
		return -EINVAL;
	}

	bin->len = len;
	/* Zero length binary strings are permitted. */
	if (len > 0) {
		bin->data = buf->cur;
		buf->cur += len;
	} else {
		bin->data = NULL;
	}

	NET_DBG("<< bin len:%08zx", GET_BINSTR_BUFFER_SIZE(bin));

	return 0;
}

static int properties_decode(struct property_decoder *prop, uint8_t cnt,
			     struct buf_ctx *buf)
{
	uint32_t properties_len;
	int bytes;
	int err;

	bytes = unpack_variable_int(buf, &properties_len);
	if (bytes < 0) {
		return -EINVAL;
	}

	bytes += (int)properties_len;

	while (properties_len > 0) {
		struct property_decoder *current_prop = NULL;
		uint8_t type;

		/* Decode property type */
		err = unpack_uint8(buf, &type);
		if (err < 0) {
			return -EINVAL;
		}

		properties_len--;

		/* Search if the property is supported in the provided property
		 * array.
		 */
		for (int i = 0; i < cnt; i++) {
			if (type == prop[i].type) {
				current_prop = &prop[i];
			}
		}

		if (current_prop == NULL) {
			NET_DBG("Unsupported property %u", type);
			return -EBADMSG;
		}

		/* Decode property value. */
		switch (type) {
		case MQTT_PROP_SESSION_EXPIRY_INTERVAL:
		case MQTT_PROP_MAXIMUM_PACKET_SIZE:
		case MQTT_PROP_MESSAGE_EXPIRY_INTERVAL:
			err = decode_uint32_property(current_prop,
						     &properties_len, buf);
			break;
		case MQTT_PROP_RECEIVE_MAXIMUM:
		case MQTT_PROP_TOPIC_ALIAS_MAXIMUM:
		case MQTT_PROP_SERVER_KEEP_ALIVE:
		case MQTT_PROP_TOPIC_ALIAS:
			err = decode_uint16_property(current_prop,
						     &properties_len, buf);
			break;
		case MQTT_PROP_MAXIMUM_QOS:
		case MQTT_PROP_RETAIN_AVAILABLE:
		case MQTT_PROP_WILDCARD_SUBSCRIPTION_AVAILABLE:
		case MQTT_PROP_SUBSCRIPTION_IDENTIFIER_AVAILABLE:
		case MQTT_PROP_SHARED_SUBSCRIPTION_AVAILABLE:
		case MQTT_PROP_PAYLOAD_FORMAT_INDICATOR:
			err = decode_uint8_property(current_prop,
						    &properties_len, buf);
			break;
		case MQTT_PROP_ASSIGNED_CLIENT_IDENTIFIER:
		case MQTT_PROP_REASON_STRING:
		case MQTT_PROP_RESPONSE_INFORMATION:
		case MQTT_PROP_SERVER_REFERENCE:
		case MQTT_PROP_AUTHENTICATION_METHOD:
		case MQTT_PROP_RESPONSE_TOPIC:
		case MQTT_PROP_CONTENT_TYPE:
			err = decode_string_property(current_prop,
						     &properties_len, buf);
			break;
		case MQTT_PROP_USER_PROPERTY:
			err = decode_user_property(current_prop,
						   &properties_len, buf);
			break;
		case MQTT_PROP_AUTHENTICATION_DATA:
		case MQTT_PROP_CORRELATION_DATA:
			err = decode_binary_property(current_prop,
						     &properties_len, buf);
			break;
		case MQTT_PROP_SUBSCRIPTION_IDENTIFIER:
			err = decode_sub_id_property(current_prop,
						     &properties_len, buf);
			break;
		default:
			err = -ENOTSUP;
		}

		if (err < 0) {
			return err;
		}
	}

	return bytes;
}