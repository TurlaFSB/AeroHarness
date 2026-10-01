
/**
 * @brief Unpacks unsigned 8 bit value from the buffer from the offset
 *        requested.
 *
 * @param[inout] buf A pointer to the buf_ctx structure containing current
 *                   buffer position.
 * @param[out] val Memory where the value is to be unpacked.
 *
 * @retval 0 if the procedure is successful.
 * @retval -EINVAL if the buffer would be exceeded during the read
 */
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

/**
 * @brief Unpacks unsigned 16 bit value from the buffer from the offset
 *        requested.
 *
 * @param[inout] buf A pointer to the buf_ctx structure containing current
 *                   buffer position.
 * @param[out] val Memory where the value is to be unpacked.
 *
 * @retval 0 if the procedure is successful.
 * @retval -EINVAL if the buffer would be exceeded during the read
 */
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

/**
 * @brief Unpacks utf8 string from the buffer from the offset requested.
 *
 * @param[inout] buf A pointer to the buf_ctx structure containing current
 *                   buffer position.
 * @param[out] str Pointer to a string that will hold the string location
 *                 in the buffer.
 *
 * @retval 0 if the procedure is successful.
 * @retval -EINVAL if the buffer would be exceeded during the read
 */
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

/**
 * @brief Unpacks binary string from the buffer from the offset requested with
 *        the length provided.
 *
 * @param[in] length Binary string length.
 * @param[inout] buf A pointer to the buf_ctx structure containing current
 *                   buffer position.
 * @param[out] str Pointer to a binary string that will hold the binary string
 *                 location in the buffer.
 *
 * @retval 0 if the procedure is successful.
 * @retval -EINVAL if the buffer would be exceeded during the read
 */
static int unpack_raw_data(uint32_t length, struct buf_ctx *buf,
			   struct mqtt_binstr *str)
{
	NET_DBG(">> cur:%p, end:%p", (void *)buf->cur, (void *)buf->end);

	if ((buf->end - buf->cur) < length) {
		return -EINVAL;
	}

	str->len = length;

	/* Zero length binary strings are permitted. */
	if (length > 0) {
		str->data = buf->cur;
		buf->cur += length;
	} else {
		str->data = NULL;
	}

	NET_DBG("<< bin len:%08zx", GET_BINSTR_BUFFER_SIZE(str));

	return 0;
}

int unpack_variable_int(struct buf_ctx *buf, uint32_t *val)
{
	uint8_t shift = 0U;
	int bytes = 0;

	*val = 0U;
	do {
		if (bytes >= MQTT_MAX_LENGTH_BYTES) {
			return -EINVAL;
		}

		if (buf->cur >= buf->end) {
			return -EAGAIN;
		}

		*val += ((uint32_t)*(buf->cur) & MQTT_LENGTH_VALUE_MASK)
								<< shift;
		shift += MQTT_LENGTH_SHIFT;
		bytes++;
	} while ((*(buf->cur++) & MQTT_LENGTH_CONTINUATION_BIT) != 0U);

	if (*val > MQTT_MAX_PAYLOAD_SIZE) {
		return -EINVAL;
	}

	NET_DBG("variable int:0x%08x", *val);

	return bytes;
}

int fixed_header_decode(struct buf_ctx *buf, uint8_t *type_and_flags,
			uint32_t *length)
{
	int err_code;

	err_code = unpack_uint8(buf, type_and_flags);
	if (err_code != 0) {
		return err_code;
	}

	err_code = unpack_variable_int(buf, length);
	if (err_code < 0) {
		return err_code;
	}

	return 0;
}

#if defined(CONFIG_MQTT_VERSION_5_0)
/**
 * @brief Unpacks unsigned 32 bit value from the buffer from the offset
 *        requested.
 *
 * @param[inout] buf A pointer to the buf_ctx structure containing current
 *                   buffer position.
 * @param[out] val Memory where the value is to be unpacked.
 *
 * @retval 0 if the procedure is successful.
 * @retval -EINVAL if the buffer would be exceeded during the read
 */
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

/**
 * @brief Unpacks binary string from the buffer from the offset requested.
 *        Binary string length is decoded from the first two bytes of the buffer.
 *
 * @param[inout] buf A pointer to the buf_ctx structure containing current
 *                   buffer position.
 * @param[out] bin Pointer to a binary string that will hold the binary string
 *                 location in the buffer.
 *
 * @retval 0 if the procedure is successful.
 * @retval -EINVAL if the buffer would be exceeded during the read
 */
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

struct property_decoder {
	void *data;
	bool *found;
	uint8_t type;
};

int decode_uint32_property(struct property_decoder *prop,
			   uint32_t *remaining_len,
			   struct buf_ctx *buf)
{
	uint32_t *value = prop->data;

	if (*remaining_len < sizeof(uint32_t)) {
		return -EINVAL;
	}

	if (unpack_uint32(buf, value) < 0) {
		return -EINVAL;
	}

	*remaining_len -= sizeof(uint32_t);
	*prop->found = true;

	return 0;
}

int decode_uint16_property(struct property_decoder *prop,
			   uint32_t *remaining_len,
			   struct buf_ctx *buf)
{
	uint16_t *value = prop->data;

	if (*remaining_len < sizeof(uint16_t)) {
		return -EINVAL;
	}

	if (unpack_uint16(buf, value) < 0) {
		return -EINVAL;
	}

	*remaining_len -= sizeof(uint16_t);
	*prop->found = true;

	return 0;
}

int decode_uint8_property(struct property_decoder *prop,
			   uint32_t *remaining_len,
			   struct buf_ctx *buf)
{
	uint8_t *value = prop->data;

	if (*remaining_len < sizeof(uint8_t)) {
		return -EINVAL;
	}

	if (unpack_uint8(buf, value) < 0) {
		return -EINVAL;
	}

	*remaining_len -= sizeof(uint8_t);
	*prop->found = true;

	return 0;
}

int decode_string_property(struct property_decoder *prop,
			   uint32_t *remaining_len,
			   struct buf_ctx *buf)
{
	struct mqtt_utf8 *str = prop->data;

	if (unpack_utf8_str(buf, str) < 0) {
		return -EINVAL;
	}

	if (*remaining_len < sizeof(uint16_t) + str->size) {
		return -EINVAL;
	}

	*remaining_len -= sizeof(uint16_t) + str->size;
	*prop->found = true;

	return 0;
}

int decode_binary_property(struct property_decoder *prop,
			   uint32_t *remaining_len,
			   struct buf_ctx *buf)
{
	struct mqtt_binstr *bin = prop->data;

	if (unpack_binary_data(buf, bin) < 0) {
		return -EINVAL;
	}

	if (*remaining_len < sizeof(uint16_t) + bin->len) {
		return -EINVAL;
	}

	*remaining_len -= sizeof(uint16_t) + bin->len;
	*prop->found = true;

	return 0;
}

int decode_user_property(struct property_decoder *prop,
			   uint32_t *remaining_len,
			   struct buf_ctx *buf)
{
	struct mqtt_utf8_pair *user_prop = prop->data;
	struct mqtt_utf8_pair *chosen = NULL;
	struct mqtt_utf8_pair temp = { 0 };
	size_t prop_len;

	if (unpack_utf8_str(buf, &temp.name) < 0) {
		return -EINVAL;
	}

	if (unpack_utf8_str(buf, &temp.value) < 0) {
		return -EINVAL;
	}

	prop_len = (2 * sizeof(uint16_t)) + temp.name.size + temp.value.size;
	if (*remaining_len < prop_len) {
		return -EINVAL;
	}

	*remaining_len -= prop_len;
	*prop->found = true;

	for (int i = 0; i < CONFIG_MQTT_USER_PROPERTIES_MAX; i++) {
		if (user_prop[i].name.utf8 == NULL) {
			chosen = &user_prop[i];
			break;
		}
	}

	if (chosen == NULL) {
		NET_DBG("Cannot parse all user properties, ignore excess");
	} else {
		memcpy(chosen, &temp, sizeof(struct mqtt_utf8_pair));
	}

	return 0;
}

int decode_sub_id_property(struct property_decoder *prop,
			   uint32_t *remaining_len,
			   struct buf_ctx *buf)
{
	uint32_t *sub_id_array = prop->data;
	uint32_t *chosen = NULL;
	uint32_t value;
	int bytes;

	bytes = unpack_variable_int(buf, &value);
	if (bytes < 0) {
		return -EINVAL;
	}

	if (*remaining_len < bytes) {
		return -EINVAL;
	}

	*remaining_len -= bytes;
	*prop->found = true;

	for (int i = 0; i < CONFIG_MQTT_SUBSCRIPTION_ID_PROPERTIES_MAX; i++) {
		if (sub_id_array[i] == 0) {
			chosen = &sub_id_array[i];
			break;
		}
	}

	if (chosen == NULL) {
		NET_DBG("Cannot parse all subscription id properties, ignore excess");
	} else {
		*chosen = value;
	}

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

#endif

