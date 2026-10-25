#ifndef CRTP_TRAJECTORY_WRITE_H
#define CRTP_TRAJECTORY_WRITE_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#define TRAJECTORY_MEMORY_SIZE 4096

extern uint8_t trajectories_memory[TRAJECTORY_MEMORY_SIZE] __attribute__((aligned(4)));

bool crtpCommanderHighLevelWriteTrajectory(const uint32_t offset, const uint32_t length, const uint8_t* data);

#ifdef __cplusplus
}
#endif

#endif // CRTP_TRAJECTORY_WRITE_H
