/* Real implementation of radiolinkSyslinkDispatch, copied verbatim from
 * cf/src/hal/src/radiolink.c at commit 9912584c85db92dbbba14334ffed20ebabba463e.
 * FreeRTOS queues, ticks, and led sequences are backed by safe host stubs.
 */
#include "crazyflie_radiolink.h"

/* Static state from radiolink.c */
static const ledseq_t seq_linkUp = {0};
static const ledseq_t seq_linkDown = {0};

static uint32_t lastPacketTick = 0;
static uint32_t count_rx_unicast = 0;
static uint32_t count_rx_broadcast = 0;
static uint8_t rssi = 0;
static bool isConnected = false;
static xQueueHandle txQueue = (void*)0x1000;
static xQueueHandle crtpPacketDelivery = (void*)0x2000;
static volatile P2PCallback p2p_callback;

/* Host stubs for FreeRTOS and crazyflie platform functions */
TickType_t xTaskGetTickCount(void) {
    return 1000;
}

BaseType_t xQueueSend(xQueueHandle q, const void *item, TickType_t wait) {
    (void)q;
    (void)item;
    (void)wait;
    return pdPASS;
}

BaseType_t xQueueReceive(xQueueHandle q, void *dest, TickType_t wait) {
    (void)q;
    (void)dest;
    (void)wait;
    return pdFALSE;
}

void ledseqRun(const ledseq_t *sequence) {
    (void)sequence;
}

void syslinkSendPacket(SyslinkPacket *slp) {
    (void)slp;
}

static bool radiolinkIsConnected(void) {
    return true;
}

/* Verbatim implementation of radiolinkSyslinkDispatch from cf/src/hal/src/radiolink.c */
void radiolinkSyslinkDispatch(SyslinkPacket *slp)
{
  if (slp->length > SYSLINK_MTU) {
    return; // Mirrors uart_syslink.c's waitForLength state: the real UART
            // receive state machine discards any packet whose length byte
            // exceeds SYSLINK_MTU (64) before it is ever dispatched.
  }
  static SyslinkPacket txPacket;

  if (slp->type == SYSLINK_RADIO_RAW || slp->type == SYSLINK_RADIO_RAW_BROADCAST) {
    lastPacketTick = xTaskGetTickCount();
  }

  if (slp->type == SYSLINK_RADIO_READY)
  {
    // ACK from nRF51 confirming radio is now enabled
    // No action needed, just silently acknowledge
  }
  else if (slp->type == SYSLINK_RADIO_RAW)
  {
    slp->length--; // Decrease to get CRTP size.
#ifdef CONFIG_RADIO_ASSERT_ON_QUEUE_FULL
    // Assert that we are not dropping any packets
    ASSERT(xQueueSend(crtpPacketDelivery, &slp->length, 0) == pdPASS);
#else
    xQueueSend(crtpPacketDelivery, &slp->length, 0);
#endif
    ++count_rx_unicast;
    ledseqRun(&seq_linkUp);
    // If a radio packet is received, one can be sent
    if (xQueueReceive(txQueue, &txPacket, 0) == pdTRUE)
    {
      ledseqRun(&seq_linkDown);
      syslinkSendPacket(&txPacket);
    }
  } else if (slp->type == SYSLINK_RADIO_RAW_BROADCAST)
  {
    slp->length--; // Decrease to get CRTP size.
    // broadcasts are best effort, so no need to handle the case where the queue is full
    BaseType_t result = xQueueSend(crtpPacketDelivery, &slp->length, 0);
    // only increment the received counter, if we were able to put it in the queue
    if (result == pdPASS) {
      ++count_rx_broadcast;
    }
    ledseqRun(&seq_linkUp);
    // no ack for broadcasts
  } else if (slp->type == SYSLINK_RADIO_RSSI)
  {
    //Extract RSSI sample sent from radio
    memcpy(&rssi, slp->data, sizeof(uint8_t)); //rssi will not change on disconnect
  } else if (slp->type == SYSLINK_RADIO_P2P_BROADCAST)
  {
    ledseqRun(&seq_linkUp);
    P2PPacket p2pp;
    p2pp.port=slp->data[0];
    p2pp.rssi = slp->data[1];

    const uint8_t p2pDataLength = slp->length - 2;
    memcpy(&p2pp.data[0], &slp->data[2], p2pDataLength);
    p2pp.size = p2pDataLength;

    if (p2p_callback) {
        p2p_callback(&p2pp);
    }
  }

  isConnected = radiolinkIsConnected();
}

void p2pRegisterCB(P2PCallback cb)
{
    p2p_callback = cb;
}
