#include "4DPluginAPI.h"
// Compile only the actual dispatcher's legacy Mac branch, not a fictional Windows ABI.
#undef __LP64__
#undef CGFLOAT_IS_DOUBLE
#define CGFLOAT_IS_DOUBLE 0
