#include <stdio.h>

int fisk22()
{
#ifdef HEST
	return 42 * 42;
#else
	return 42;
#endif
}