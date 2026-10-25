#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "crtp_trajectory_write.h"

#define TRAJECTORY_MEMORY_SIZE 4096

// Global variables
uint8_t trajectories_memory[TRAJECTORY_MEMORY_SIZE] __attribute__((aligned(4)));

bool crtpCommanderHighLevelWriteTrajectory(const uint32_t offset, const uint32_t length, const uint8_t* data)
{
  bool result = false;

  if ((offset + length) <= sizeof(trajectories_memory)) {
    memcpy(&(trajectories_memory[offset]), data, length);
    result = true;
  }

  return result;
}
