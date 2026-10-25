#include "crazyflie_log_append.h"
#include <string.h>
#include <errno.h>

#define LOG_MAX_OPS 128
#define LOG_MAX_BLOCKS 16

static const uint8_t typeLength[] = {
  [LOG_UINT8]  = 1,
  [LOG_UINT16] = 2,
  [LOG_UINT32] = 4,
  [LOG_INT8]   = 1,
  [LOG_INT16]  = 2,
  [LOG_INT32]  = 4,
  [LOG_FLOAT]  = 4,
  [LOG_FP16]   = 2,
};

typedef enum {
  acqType_memory = 0,
  acqType_function = 1,
} acquisitionType_t;

struct log_ops {
  struct log_ops * next;
  uint8_t storageType : 4;
  uint8_t logType     : 4;
  void * variable;
  acquisitionType_t acquisitionType;
};

typedef void* xTimerHandle;
typedef struct { uint32_t dummy[14]; } StaticTimer_t;

struct log_block {
  int id;
  xTimerHandle timer;
  StaticTimer_t timerBuffer;
  uint32_t droppedPackets;
  struct log_ops * ops;
};

static struct log_block logBlocks[LOG_MAX_BLOCKS] = {
  [0] = { .id = FIXED_BLOCK_ID, .ops = NULL }
};

struct log_s {
  uint8_t type;
  char * name;
  void * address;
};

static struct log_s dummy_logs[1];
static struct log_s * logs = dummy_logs;

#define LOG_DEBUG(...) ((void)0)
#define LOG_ERROR(...) ((void)0)

static int blockCalcLength(struct log_block * block)
{
  struct log_ops * ops;
  int len = 0;

  for (ops = block->ops; ops; ops = ops->next)
    len += typeLength[ops->logType];

  return len;
}

static struct log_ops * opsMalloc(void)
{
  return NULL;
}

static void blockAppendOps(struct log_block * block, struct log_ops * ops)
{
  (void)block;
  (void)ops;
}

static int variableGetIndex(int id)
{
  (void)id;
  return -1;
}

static inline int logGetType(int varid)
{
  (void)varid;
  return 0;
}

static inline acquisitionType_t acquisitionTypeFromLogType(uint8_t logType)
{
  (void)logType;
  return acqType_memory;
}

int logAppendBlockV2(int id, struct ops_setting_v2 * settings, int len)
{
  int i;
  struct log_block * block;

  LOG_DEBUG("Appending %d variable to block %d\n", len, id);

  for (i=0; i<LOG_MAX_BLOCKS; i++)
    if (logBlocks[i].id == id) break;

  if (i >= LOG_MAX_BLOCKS) {
    LOG_ERROR("Trying to append block id %d that doesn't exist.", id);
    return ENOENT;
  }

  block = &logBlocks[i];

  for (i=0; i<len; i++)
  {
    int currentLength = blockCalcLength(block);
    struct log_ops * ops;
    int varId;

    if ((currentLength + typeLength[settings[i].logType & LOG_TYPE_MASK])>LOG_MAX_LEN) {
      LOG_ERROR("Trying to append a full block. Block id %d.\n", id);
      return E2BIG;
    }

    ops = opsMalloc();

    if(!ops) {
      LOG_ERROR("No more ops memory free!\n");
      return ENOMEM;
    }

    if (settings[i].id != 0xFFFFul)  //TOC variable
    {
      varId = variableGetIndex(settings[i].id);

      if (varId<0) {
        LOG_ERROR("Trying to add variable Id %d that does not exists.", settings[i].id);
        return ENOENT;
      }

      ops->variable    = logs[varId].address;
      ops->storageType = logGetType(varId);
      ops->logType     = settings[i].logType & LOG_TYPE_MASK;
      ops->acquisitionType = acquisitionTypeFromLogType(logs[varId].type);

      LOG_DEBUG("Appended variable %d to block %d\n", settings[i].id, id);
    } else {                     //Memory variable
      //TODO: Check that the address is in ram
      ops->variable    = (void*)(&settings[i]+1);
      ops->storageType = (settings[i].logType>>4) & LOG_TYPE_MASK;
      ops->logType     = settings[i].logType & LOG_TYPE_MASK;
      ops->acquisitionType = acqType_memory;
      i += 2;

      LOG_DEBUG("Appended var addr 0x%x to block %d\n", (int)ops->variable, id);
    }
    blockAppendOps(block, ops);

    LOG_DEBUG("   Now length %d\n", blockCalcLength(block));
  }

  return 0;
}
