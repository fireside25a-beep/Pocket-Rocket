#include<stdio.h>
/* same admitted program, different source bytes */
int add ( int a , int b ) { return a+b; }
int main ( ) {
 int x=add(40,2); // spacing and comment
 printf ( "%d\n" , x ) ;
 return 0 ;
}
