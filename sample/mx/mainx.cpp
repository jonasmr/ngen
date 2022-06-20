#include <stdio.h>
int sub();
int fisk22();
int main2();

int main()
{
#ifndef MX_DEF
	#error "missing define"
#endif
	printf("fisk2 %d\n", fisk22());
	printf("main2 %d\n", main2());

	printf("this is main %d\n", sub());
}