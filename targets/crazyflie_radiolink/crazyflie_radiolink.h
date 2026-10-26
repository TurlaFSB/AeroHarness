#ifndef CRAZYFLIE_RADIOLINK_H_
#define CRAZYFLIE_RADIOLINK_H_

#include "freertos_stubs.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Target function forward declaration for CASTExtractor */
void radiolinkSyslinkDispatch(SyslinkPacket *slp);
void p2pRegisterCB(P2PCallback cb);

#ifdef __cplusplus
}
#endif

#endif /* CRAZYFLIE_RADIOLINK_H_ */
