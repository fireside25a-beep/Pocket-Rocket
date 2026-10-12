#define _XOPEN_SOURCE 700
#define _POSIX_C_SOURCE 200809L
#include "dxl.h"

#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define ARRAY_LEN(x) (sizeof(x) / sizeof((x)[0]))
#define MAX_ERRORS 96
#define MAX_IMPORT_DEPTH 64
#define MAX_RECURSION 256
#define MAX_EVAL_STEPS 2000000ULL
#define DXL_CACHE_DIR ".aegis-cache"

/* ---------- utilities ---------- */
typedef struct { char *data; size_t len, cap; } StrBuf;
static void die_oom(void){fputs("dxlc: out of memory\n",stderr);exit(2);} 
static void sb_init(StrBuf*b){memset(b,0,sizeof(*b));}
static void sb_reserve(StrBuf*b,size_t need){if(need<=b->cap)return;size_t c=b->cap?b->cap:256;while(c<need){if(c>SIZE_MAX/2)die_oom();c*=2;}char*p=realloc(b->data,c);if(!p)die_oom();b->data=p;b->cap=c;}
static void sb_append_n(StrBuf*b,const char*s,size_t n){sb_reserve(b,b->len+n+1);memcpy(b->data+b->len,s,n);b->len+=n;b->data[b->len]='\0';}
static void sb_append(StrBuf*b,const char*s){sb_append_n(b,s,strlen(s));}
static void sb_putc(StrBuf*b,char c){sb_reserve(b,b->len+2);b->data[b->len++]=c;b->data[b->len]='\0';}
static void sb_printf(StrBuf*b,const char*fmt,...){va_list ap,ap2;va_start(ap,fmt);va_copy(ap2,ap);int n=vsnprintf(NULL,0,fmt,ap);va_end(ap);if(n<0){va_end(ap2);return;}sb_reserve(b,b->len+(size_t)n+1);vsnprintf(b->data+b->len,(size_t)n+1,fmt,ap2);va_end(ap2);b->len+=(size_t)n;}
static void sb_free(StrBuf*b){free(b->data);memset(b,0,sizeof(*b));}
static char*xstrndup(const char*s,size_t n){char*p=malloc(n+1);if(!p)die_oom();memcpy(p,s,n);p[n]='\0';return p;}
static char*xstrdup(const char*s){return xstrndup(s,strlen(s));}
static void*grow_array(void*p,size_t elem,size_t*cap,size_t need){if(need<=*cap)return p;size_t c=*cap?*cap*2:8;while(c<need)c*=2;void*n=realloc(p,elem*c);if(!n)die_oom();*cap=c;return n;}
static bool path_exists(const char*p){struct stat st;return stat(p,&st)==0;}
static bool mkdir_p(const char*path){char*tmp=xstrdup(path);size_t n=strlen(tmp);if(n&&tmp[n-1]=='/')tmp[n-1]='\0';for(char*p=tmp+1;*p;p++)if(*p=='/'){*p='\0';if(mkdir(tmp,0755)&&errno!=EEXIST){free(tmp);return false;}*p='/';}bool ok=mkdir(tmp,0755)==0||errno==EEXIST;free(tmp);return ok;}
static char*read_file(const char*path,size_t*out_len){FILE*f=fopen(path,"rb");if(!f){fprintf(stderr,"dxlc: cannot open %s: %s\n",path,strerror(errno));return NULL;}if(fseek(f,0,SEEK_END)){fclose(f);return NULL;}long n=ftell(f);if(n<0){fclose(f);return NULL;}rewind(f);char*b=malloc((size_t)n+1);if(!b){fclose(f);die_oom();}size_t got=fread(b,1,(size_t)n,f);if(ferror(f)){free(b);fclose(f);return NULL;}fclose(f);b[got]='\0';if(out_len)*out_len=got;return b;}
static bool write_file(const char*path,const char*data,size_t len){char*dup=xstrdup(path);char*slash=strrchr(dup,'/');if(slash){*slash='\0';if(*dup&&!mkdir_p(dup)){free(dup);return false;}}free(dup);FILE*f=fopen(path,"wb");if(!f){fprintf(stderr,"dxlc: cannot write %s: %s\n",path,strerror(errno));return false;}bool ok=fwrite(data,1,len,f)==len&&fclose(f)==0;return ok;}
static bool copy_file(const char*src,const char*dst){size_t n=0;char*b=read_file(src,&n);if(!b)return false;bool ok=write_file(dst,b,n);free(b);return ok;}
static char*path_dirname(const char*path){const char*s=strrchr(path,'/');return s?xstrndup(path,(size_t)(s-path)):xstrdup(".");}
static char*path_join(const char*a,const char*b){if(!a||!*a)return xstrdup(b);if(b[0]=='/')return xstrdup(b);size_t na=strlen(a),nb=strlen(b);char*p=malloc(na+nb+2);if(!p)die_oom();memcpy(p,a,na);p[na]='/';memcpy(p+na+1,b,nb+1);return p;}
static char*canonical_path(const char*p){char*r=realpath(p,NULL);return r?r:xstrdup(p);}
static int run_cmd(char*const argv[]){pid_t pid=fork();if(pid<0)return-1;if(pid==0){execvp(argv[0],argv);perror(argv[0]);_exit(127);}int st=0;if(waitpid(pid,&st,0)<0)return-1;if(WIFEXITED(st))return WEXITSTATUS(st);if(WIFSIGNALED(st))return 128+WTERMSIG(st);return 128;}
static int run_cmd_input(char*const argv[],const char*data,size_t len){
    int fds[2];if(pipe(fds)<0)return-1;pid_t pid=fork();if(pid<0){close(fds[0]);close(fds[1]);return-1;}
    if(pid==0){close(fds[1]);if(dup2(fds[0],STDIN_FILENO)<0)_exit(127);close(fds[0]);execvp(argv[0],argv);perror(argv[0]);_exit(127);}
    close(fds[0]);size_t off=0;while(off<len){ssize_t n=write(fds[1],data+off,len-off);if(n<0){if(errno==EINTR)continue;break;}off+=(size_t)n;}close(fds[1]);
    int st=0;if(waitpid(pid,&st,0)<0)return-1;if(WIFEXITED(st))return WEXITSTATUS(st);if(WIFSIGNALED(st))return 128+WTERMSIG(st);return 128;
}

/* ---------- SHA-256 ---------- */
typedef struct { uint32_t h[8]; uint64_t bits; uint8_t block[64]; size_t used; } Sha256;
static uint32_t rotr32(uint32_t x,unsigned n){return(x>>n)|(x<<(32-n));}
static const uint32_t K256[64]={
0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};
static void sha_init(Sha256*s){uint32_t h[8]={0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};memcpy(s->h,h,sizeof h);s->bits=0;s->used=0;}
static void sha_block(Sha256*s,const uint8_t*b){uint32_t w[64];for(int i=0;i<16;i++)w[i]=((uint32_t)b[i*4]<<24)|((uint32_t)b[i*4+1]<<16)|((uint32_t)b[i*4+2]<<8)|b[i*4+3];for(int i=16;i<64;i++){uint32_t a=w[i-15],z=w[i-2];uint32_t s0=rotr32(a,7)^rotr32(a,18)^(a>>3);uint32_t s1=rotr32(z,17)^rotr32(z,19)^(z>>10);w[i]=w[i-16]+s0+w[i-7]+s1;}uint32_t a=s->h[0],b0=s->h[1],c=s->h[2],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];for(int i=0;i<64;i++){uint32_t S1=rotr32(e,6)^rotr32(e,11)^rotr32(e,25);uint32_t ch=(e&f)^((~e)&g);uint32_t t1=h+S1+ch+K256[i]+w[i];uint32_t S0=rotr32(a,2)^rotr32(a,13)^rotr32(a,22);uint32_t maj=(a&b0)^(a&c)^(b0&c);uint32_t t2=S0+maj;h=g;g=f;f=e;e=d+t1;d=c;c=b0;b0=a;a=t1+t2;}s->h[0]+=a;s->h[1]+=b0;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;}
static void sha_update(Sha256*s,const void*data,size_t n){const uint8_t*p=data;s->bits+=(uint64_t)n*8;while(n){size_t k=64-s->used;if(k>n)k=n;memcpy(s->block+s->used,p,k);s->used+=k;p+=k;n-=k;if(s->used==64){sha_block(s,s->block);s->used=0;}}}
static void sha_final(Sha256*s,uint8_t out[32]){s->block[s->used++]=0x80;if(s->used>56){while(s->used<64)s->block[s->used++]=0;sha_block(s,s->block);s->used=0;}while(s->used<56)s->block[s->used++]=0;for(int i=7;i>=0;i--)s->block[s->used++]=(uint8_t)(s->bits>>(i*8));sha_block(s,s->block);for(int i=0;i<8;i++){out[i*4]=(uint8_t)(s->h[i]>>24);out[i*4+1]=(uint8_t)(s->h[i]>>16);out[i*4+2]=(uint8_t)(s->h[i]>>8);out[i*4+3]=(uint8_t)s->h[i];}}
static void sha_hex(const void*data,size_t n,char hex[65]){Sha256 s;uint8_t d[32];sha_init(&s);sha_update(&s,data,n);sha_final(&s,d);static const char*h="0123456789abcdef";for(int i=0;i<32;i++){hex[i*2]=h[d[i]>>4];hex[i*2+1]=h[d[i]&15];}hex[64]='\0';}

/* ---------- lexer ---------- */
typedef enum {
TK_EOF,TK_IDENT,TK_INT,TK_STRING,
TK_FN,TK_COMPTIME,TK_CONST,TK_LET,TK_RETURN,TK_IF,TK_ELSE,TK_WHILE,
TK_TRUE,TK_FALSE,TK_EXPORT,TK_EXTERN,TK_TEST,TK_ASSERT,TK_IMPORT,TK_STRUCT,TK_ENUM,TK_AS,
TK_I64,TK_I32,TK_BOOL,TK_VOID,TK_ARRAY_I64,TK_SLICE_I64,TK_RESULT_I64,
TK_LPAREN,TK_RPAREN,TK_LBRACE,TK_RBRACE,TK_LBRACKET,TK_RBRACKET,
TK_COLON,TK_SEMI,TK_COMMA,TK_DOT,TK_ARROW,TK_ASSIGN,TK_PLUS,TK_MINUS,TK_STAR,TK_SLASH,TK_PERCENT,
TK_EQ,TK_NE,TK_LT,TK_LE,TK_GT,TK_GE,TK_AND,TK_OR,TK_BANG
}TokenKind;
typedef struct{TokenKind kind;const char*start;size_t len;int line,col;int64_t int_value;bool int_overflow;}Token;
typedef struct{const char*src;size_t len,pos;int line,col;}Lexer;
static void lex_init(Lexer*l,const char*s,size_t n){l->src=s;l->len=n;l->pos=0;l->line=1;l->col=1;}
static char lpeek(Lexer*l){return l->pos<l->len?l->src[l->pos]:'\0';}
static char lpeek2(Lexer*l){return l->pos+1<l->len?l->src[l->pos+1]:'\0';}
static char ltake(Lexer*l){char c=lpeek(l);if(!c)return 0;l->pos++;if(c=='\n'){l->line++;l->col=1;}else l->col++;return c;}
static TokenKind kw(const char*s,size_t n){struct K{const char*s;TokenKind k;}ks[]={
{"fn",TK_FN},{"comptime",TK_COMPTIME},{"const",TK_CONST},{"let",TK_LET},{"return",TK_RETURN},{"if",TK_IF},{"else",TK_ELSE},{"while",TK_WHILE},{"true",TK_TRUE},{"false",TK_FALSE},{"export",TK_EXPORT},{"extern",TK_EXTERN},{"test",TK_TEST},{"assert",TK_ASSERT},{"import",TK_IMPORT},{"struct",TK_STRUCT},{"enum",TK_ENUM},{"as",TK_AS},{"i64",TK_I64},{"i32",TK_I32},{"bool",TK_BOOL},{"void",TK_VOID},{"array_i64",TK_ARRAY_I64},{"slice_i64",TK_SLICE_I64},{"result_i64",TK_RESULT_I64}};for(size_t i=0;i<ARRAY_LEN(ks);i++)if(strlen(ks[i].s)==n&&!memcmp(s,ks[i].s,n))return ks[i].k;return TK_IDENT;}
static void lex_skip(Lexer*l){for(;;){while(isspace((unsigned char)lpeek(l)))ltake(l);if(lpeek(l)=='/'&&lpeek2(l)=='/'){while(lpeek(l)&&lpeek(l)!='\n')ltake(l);continue;}if(lpeek(l)=='/'&&lpeek2(l)=='*'){ltake(l);ltake(l);int depth=1;while(lpeek(l)&&depth){if(lpeek(l)=='/'&&lpeek2(l)=='*'){ltake(l);ltake(l);depth++;}else if(lpeek(l)=='*'&&lpeek2(l)=='/'){ltake(l);ltake(l);depth--;}else ltake(l);}continue;}break;}}
static Token lex_next(Lexer*l){lex_skip(l);Token t={0};t.start=l->src+l->pos;t.line=l->line;t.col=l->col;char c=ltake(l);if(!c){t.kind=TK_EOF;return t;}if(isalpha((unsigned char)c)||c=='_'){while(isalnum((unsigned char)lpeek(l))||lpeek(l)=='_')ltake(l);t.len=(size_t)((l->src+l->pos)-t.start);t.kind=kw(t.start,t.len);return t;}if(isdigit((unsigned char)c)){int base=10;if(c=='0'&&(lpeek(l)=='x'||lpeek(l)=='X')){ltake(l);base=16;}while((base==10&&isdigit((unsigned char)lpeek(l)))||(base==16&&isxdigit((unsigned char)lpeek(l)))||lpeek(l)=='_')ltake(l);t.len=(size_t)((l->src+l->pos)-t.start);t.kind=TK_INT;char*tmp=xstrndup(t.start,t.len),*w=tmp;for(char*r=tmp;*r;r++)if(*r!='_')*w++=*r;*w='\0';errno=0;t.int_value=strtoll(tmp,NULL,base);t.int_overflow=(errno==ERANGE);free(tmp);return t;}if(c=='"'){t.start=l->src+l->pos;while(lpeek(l)&&lpeek(l)!='"'){if(lpeek(l)=='\\'&&lpeek2(l))ltake(l);ltake(l);}t.len=(size_t)((l->src+l->pos)-t.start);if(lpeek(l)=='"')ltake(l);t.kind=TK_STRING;return t;}
#define ONE(ch,k) case ch:t.kind=k;t.len=1;return t
switch(c){ONE('(',TK_LPAREN);ONE(')',TK_RPAREN);ONE('{',TK_LBRACE);ONE('}',TK_RBRACE);ONE('[',TK_LBRACKET);ONE(']',TK_RBRACKET);ONE(':',TK_COLON);ONE(';',TK_SEMI);ONE(',',TK_COMMA);ONE('.',TK_DOT);ONE('+',TK_PLUS);ONE('*',TK_STAR);ONE('/',TK_SLASH);ONE('%',TK_PERCENT);case '-':if(lpeek(l)=='>'){ltake(l);t.kind=TK_ARROW;t.len=2;}else{t.kind=TK_MINUS;t.len=1;}return t;case '=':if(lpeek(l)=='='){ltake(l);t.kind=TK_EQ;t.len=2;}else{t.kind=TK_ASSIGN;t.len=1;}return t;case '!':if(lpeek(l)=='='){ltake(l);t.kind=TK_NE;t.len=2;}else{t.kind=TK_BANG;t.len=1;}return t;case '<':if(lpeek(l)=='='){ltake(l);t.kind=TK_LE;t.len=2;}else{t.kind=TK_LT;t.len=1;}return t;case '>':if(lpeek(l)=='='){ltake(l);t.kind=TK_GE;t.len=2;}else{t.kind=TK_GT;t.len=1;}return t;case '&':if(lpeek(l)=='&'){ltake(l);t.kind=TK_AND;t.len=2;return t;}break;case '|':if(lpeek(l)=='|'){ltake(l);t.kind=TK_OR;t.len=2;return t;}break;}
#undef ONE
t.kind=TK_EOF;t.len=1;return t;}
static char*tok_text(Token t){return xstrndup(t.start,t.len);}

/* ---------- types and AST ---------- */
typedef enum{TY_INVALID,TY_I64,TY_I32,TY_BOOL,TY_VOID,TY_ARRAY_I64,TY_SLICE_I64,TY_RESULT_I64,TY_NAMED}TypeTag;
typedef struct{TypeTag tag;char*name;}Type;
static Type type_make(TypeTag t){Type x={t,NULL};return x;}
static Type type_named(const char*n){Type x={TY_NAMED,xstrdup(n)};return x;}
static bool type_eq(Type a,Type b){return a.tag==b.tag&&(a.tag!=TY_NAMED||!strcmp(a.name,b.name));}
static bool type_int(Type t){return t.tag==TY_I64||t.tag==TY_I32;}
static const char*type_name(Type t){switch(t.tag){case TY_I64:return"i64";case TY_I32:return"i32";case TY_BOOL:return"bool";case TY_VOID:return"void";case TY_ARRAY_I64:return"array_i64";case TY_SLICE_I64:return"slice_i64";case TY_RESULT_I64:return"result_i64";case TY_NAMED:return t.name?t.name:"<named>";default:return"<invalid>";}}

typedef enum{EX_INT,EX_BOOL,EX_NAME,EX_BINARY,EX_UNARY,EX_CALL,EX_FIELD,EX_INDEX,EX_STRUCT_INIT,EX_CAST}ExprKind;
typedef struct Expr Expr;
typedef struct{char*name;Expr*value;}FieldInit;
struct Expr{ExprKind kind;Token tok;Type type;union{int64_t int_value;bool bool_value;char*name;struct{TokenKind op;Expr*l,*r;}bin;struct{TokenKind op;Expr*inner;}un;struct{char*name;Expr**args;size_t argc;}call;struct{Expr*base;char*name;}field;struct{Expr*base,*index;}index;struct{char*type_name;FieldInit*fields;size_t count;}sinit;struct{Type to;Expr*value;}cast;}as;};
typedef enum{ST_BLOCK,ST_LET,ST_ASSIGN,ST_INDEX_ASSIGN,ST_RETURN,ST_EXPR,ST_IF,ST_WHILE,ST_ASSERT}StmtKind;
typedef struct Stmt Stmt;
struct Stmt{StmtKind kind;Token tok;union{struct{Stmt**items;size_t count;}block;struct{char*name;Type type;Expr*value;}let;struct{char*name;Expr*value;}assign;struct{Expr*base,*index,*value;}idx_assign;Expr*ret_expr;Expr*expr;struct{Expr*cond;Stmt*then_b,*else_b;}ifs;struct{Expr*cond;Stmt*body;}whiles;Expr*assert_expr;}as;};
typedef struct{char*name;Type type;Token tok;}Param;
typedef struct{char*name;Param*params;size_t param_count;Type ret;Stmt*body;bool is_comptime,is_export,is_extern;Token tok;char*path;}Function;
typedef struct{char*name;Type type;Expr*expr;int64_t value;bool evaluated,evaluating;Token tok;}Constant;
typedef struct{char*name;Type type;Token tok;}StructField;
typedef struct{char*name;StructField*fields;size_t field_count;Token tok;}StructDecl;
typedef struct{char*name;char**variants;size_t count;Token tok;}EnumDecl;
typedef struct{char*name;Stmt*body;Token tok;}TestDecl;
typedef struct{char*path;char*source;size_t len;char hash[65];}Module;
typedef struct{Function*funcs;size_t fn_count,fn_cap;Constant*consts;size_t const_count,const_cap;StructDecl*structs;size_t struct_count,struct_cap;EnumDecl*enums;size_t enum_count,enum_cap;Stmt**ct_blocks;size_t ct_count,ct_cap;TestDecl*tests;size_t test_count,test_cap;Module*mods;size_t mod_count,mod_cap;const char*target;}Program;
static Expr*new_expr(ExprKind k,Token t){Expr*e=calloc(1,sizeof(*e));if(!e)die_oom();e->kind=k;e->tok=t;e->type=type_make(TY_INVALID);return e;}
static Stmt*new_stmt(StmtKind k,Token t){Stmt*s=calloc(1,sizeof(*s));if(!s)die_oom();s->kind=k;s->tok=t;return s;}

/* ---------- parser ---------- */
typedef struct{Lexer lex;Token cur,next;const char*path;int errors;char**imports;size_t import_count,import_cap;}Parser;
static void padv(Parser*p){p->cur=p->next;p->next=lex_next(&p->lex);}
static void pinit(Parser*p,const char*path,const char*src,size_t n){memset(p,0,sizeof(*p));p->path=path;lex_init(&p->lex,src,n);p->cur=lex_next(&p->lex);p->next=lex_next(&p->lex);}
static void perr(Parser*p,Token t,const char*fmt,...){if(p->errors++>=MAX_ERRORS)return;fprintf(stderr,"%s:%d:%d: error: ",p->path,t.line,t.col);va_list ap;va_start(ap,fmt);vfprintf(stderr,fmt,ap);va_end(ap);fputc('\n',stderr);}
static bool paccept(Parser*p,TokenKind k){if(p->cur.kind==k){padv(p);return true;}return false;}
static Token pexpect(Parser*p,TokenKind k,const char*what){Token t=p->cur;if(t.kind!=k){perr(p,t,"expected %s",what);if(t.kind!=TK_EOF)padv(p);return t;}padv(p);return t;}
static Type parse_type(Parser*p){Token t=p->cur;switch(t.kind){case TK_I64:padv(p);return type_make(TY_I64);case TK_I32:padv(p);return type_make(TY_I32);case TK_BOOL:padv(p);return type_make(TY_BOOL);case TK_VOID:padv(p);return type_make(TY_VOID);case TK_ARRAY_I64:padv(p);return type_make(TY_ARRAY_I64);case TK_SLICE_I64:padv(p);return type_make(TY_SLICE_I64);case TK_RESULT_I64:padv(p);return type_make(TY_RESULT_I64);case TK_IDENT:padv(p);return type_named(tok_text(t));default:perr(p,t,"expected type");return type_make(TY_INVALID);}}
static Expr*parse_expr(Parser*p,int minp);
static Expr*parse_primary(Parser*p){Token t=p->cur;Expr*e=NULL;if(paccept(p,TK_INT)){if(t.int_overflow)perr(p,t,"integer literal is outside signed 64-bit range");e=new_expr(EX_INT,t);e->as.int_value=t.int_value;}else if(paccept(p,TK_TRUE)||paccept(p,TK_FALSE)){e=new_expr(EX_BOOL,t);e->as.bool_value=t.kind==TK_TRUE;}else if(paccept(p,TK_AS)){e=new_expr(EX_CAST,t);pexpect(p,TK_LPAREN,"'('");e->as.cast.to=parse_type(p);pexpect(p,TK_COMMA,"','");e->as.cast.value=parse_expr(p,0);pexpect(p,TK_RPAREN,"')'");}else if(paccept(p,TK_IDENT)){char*n=tok_text(t);Lexer probe=p->lex;Token after_next=lex_next(&probe);if(p->cur.kind==TK_LBRACE&&isupper((unsigned char)n[0])&&(p->next.kind==TK_RBRACE||(p->next.kind==TK_IDENT&&after_next.kind==TK_COLON))){padv(p);e=new_expr(EX_STRUCT_INIT,t);e->as.sinit.type_name=n;size_t cap=0;if(p->cur.kind!=TK_RBRACE){for(;;){Token f=pexpect(p,TK_IDENT,"field name");pexpect(p,TK_COLON,"':'");e->as.sinit.fields=grow_array(e->as.sinit.fields,sizeof(FieldInit),&cap,e->as.sinit.count+1);e->as.sinit.fields[e->as.sinit.count++]=(FieldInit){tok_text(f),parse_expr(p,0)};if(!paccept(p,TK_COMMA))break;}}pexpect(p,TK_RBRACE,"'}'");}else if(paccept(p,TK_LPAREN)){e=new_expr(EX_CALL,t);e->as.call.name=n;size_t cap=0;if(p->cur.kind!=TK_RPAREN){for(;;){e->as.call.args=grow_array(e->as.call.args,sizeof(Expr*),&cap,e->as.call.argc+1);e->as.call.args[e->as.call.argc++]=parse_expr(p,0);if(!paccept(p,TK_COMMA))break;}}pexpect(p,TK_RPAREN,"')'");}else{e=new_expr(EX_NAME,t);e->as.name=n;}}else if(paccept(p,TK_LPAREN)){e=parse_expr(p,0);pexpect(p,TK_RPAREN,"')'");}else if(paccept(p,TK_MINUS)||paccept(p,TK_BANG)){e=new_expr(EX_UNARY,t);e->as.un.op=t.kind;e->as.un.inner=parse_expr(p,7);}else{perr(p,t,"expected expression");if(p->cur.kind!=TK_EOF)padv(p);e=new_expr(EX_INT,t);e->as.int_value=0;}
for(;;){if(paccept(p,TK_DOT)){Token f=pexpect(p,TK_IDENT,"field or variant");Expr*n=new_expr(EX_FIELD,f);n->as.field.base=e;n->as.field.name=tok_text(f);e=n;continue;}if(paccept(p,TK_LBRACKET)){Expr*i=parse_expr(p,0);pexpect(p,TK_RBRACKET,"']'");Expr*n=new_expr(EX_INDEX,t);n->as.index.base=e;n->as.index.index=i;e=n;continue;}break;}return e;}
static int prec(TokenKind k){switch(k){case TK_OR:return 1;case TK_AND:return 2;case TK_EQ:case TK_NE:return 3;case TK_LT:case TK_LE:case TK_GT:case TK_GE:return 4;case TK_PLUS:case TK_MINUS:return 5;case TK_STAR:case TK_SLASH:case TK_PERCENT:return 6;default:return-1;}}
static Expr*parse_expr(Parser*p,int minp){Expr*l=parse_primary(p);for(;;){int q=prec(p->cur.kind);if(q<minp)break;Token op=p->cur;padv(p);Expr*r=parse_expr(p,q+1);Expr*n=new_expr(EX_BINARY,op);n->as.bin.op=op.kind;n->as.bin.l=l;n->as.bin.r=r;l=n;}return l;}
static Stmt*parse_block(Parser*p);
static Stmt*parse_stmt(Parser*p){Token t=p->cur;if(p->cur.kind==TK_LBRACE)return parse_block(p);if(paccept(p,TK_LET)){Token n=pexpect(p,TK_IDENT,"identifier");pexpect(p,TK_COLON,"':'");Type ty=parse_type(p);pexpect(p,TK_ASSIGN,"'='");Expr*v=parse_expr(p,0);pexpect(p,TK_SEMI,"';'");Stmt*s=new_stmt(ST_LET,t);s->as.let.name=tok_text(n);s->as.let.type=ty;s->as.let.value=v;return s;}if(paccept(p,TK_RETURN)){Stmt*s=new_stmt(ST_RETURN,t);if(p->cur.kind!=TK_SEMI)s->as.ret_expr=parse_expr(p,0);pexpect(p,TK_SEMI,"';'");return s;}if(paccept(p,TK_IF)){Expr*c=parse_expr(p,0);Stmt*a=parse_block(p),*b=NULL;if(paccept(p,TK_ELSE))b=p->cur.kind==TK_IF?parse_stmt(p):parse_block(p);Stmt*s=new_stmt(ST_IF,t);s->as.ifs.cond=c;s->as.ifs.then_b=a;s->as.ifs.else_b=b;return s;}if(paccept(p,TK_WHILE)){Expr*c=parse_expr(p,0);Stmt*b=parse_block(p);Stmt*s=new_stmt(ST_WHILE,t);s->as.whiles.cond=c;s->as.whiles.body=b;return s;}if(paccept(p,TK_ASSERT)){pexpect(p,TK_LPAREN,"'('");Expr*e=parse_expr(p,0);pexpect(p,TK_RPAREN,"')'");pexpect(p,TK_SEMI,"';'");Stmt*s=new_stmt(ST_ASSERT,t);s->as.assert_expr=e;return s;}
Expr*lhs=parse_expr(p,0);if(paccept(p,TK_ASSIGN)){Expr*v=parse_expr(p,0);pexpect(p,TK_SEMI,"';'");if(lhs->kind==EX_NAME){Stmt*s=new_stmt(ST_ASSIGN,t);s->as.assign.name=xstrdup(lhs->as.name);s->as.assign.value=v;return s;}if(lhs->kind==EX_INDEX){Stmt*s=new_stmt(ST_INDEX_ASSIGN,t);s->as.idx_assign.base=lhs->as.index.base;s->as.idx_assign.index=lhs->as.index.index;s->as.idx_assign.value=v;return s;}perr(p,t,"left side is not assignable");}else pexpect(p,TK_SEMI,"';'");Stmt*s=new_stmt(ST_EXPR,t);s->as.expr=lhs;return s;}
static Stmt*parse_block(Parser*p){Token t=pexpect(p,TK_LBRACE,"'{'");Stmt*s=new_stmt(ST_BLOCK,t);size_t cap=0;while(p->cur.kind!=TK_RBRACE&&p->cur.kind!=TK_EOF){s->as.block.items=grow_array(s->as.block.items,sizeof(Stmt*),&cap,s->as.block.count+1);s->as.block.items[s->as.block.count++]=parse_stmt(p);}pexpect(p,TK_RBRACE,"'}'");return s;}
static void add_fn(Program*pr,Function f){pr->funcs=grow_array(pr->funcs,sizeof(Function),&pr->fn_cap,pr->fn_count+1);pr->funcs[pr->fn_count++]=f;}
static void add_const(Program*pr,Constant c){pr->consts=grow_array(pr->consts,sizeof(Constant),&pr->const_cap,pr->const_count+1);pr->consts[pr->const_count++]=c;}
static void parse_module(Parser*p,Program*pr){while(p->cur.kind!=TK_EOF){bool exp=false,ct=false,ext=false;if(paccept(p,TK_IMPORT)){Token s=pexpect(p,TK_STRING,"import path");pexpect(p,TK_SEMI,"';'");p->imports=grow_array(p->imports,sizeof(char*),&p->import_cap,p->import_count+1);p->imports[p->import_count++]=tok_text(s);continue;}if(paccept(p,TK_EXPORT))exp=true;if(paccept(p,TK_EXTERN))ext=true;if(paccept(p,TK_COMPTIME)){if(p->cur.kind==TK_FN)ct=true;else if(p->cur.kind==TK_LBRACE){pr->ct_blocks=grow_array(pr->ct_blocks,sizeof(Stmt*),&pr->ct_cap,pr->ct_count+1);pr->ct_blocks[pr->ct_count++]=parse_block(p);continue;}else{perr(p,p->cur,"expected fn or block after comptime");continue;}}
if(paccept(p,TK_STRUCT)){Token n=pexpect(p,TK_IDENT,"struct name");StructDecl d={0};d.name=tok_text(n);d.tok=n;pexpect(p,TK_LBRACE,"'{'");size_t cap=0;while(p->cur.kind!=TK_RBRACE&&p->cur.kind!=TK_EOF){Token f=pexpect(p,TK_IDENT,"field name");pexpect(p,TK_COLON,"':'");StructField sf={tok_text(f),parse_type(p),f};d.fields=grow_array(d.fields,sizeof(StructField),&cap,d.field_count+1);d.fields[d.field_count++]=sf;paccept(p,TK_COMMA);paccept(p,TK_SEMI);}pexpect(p,TK_RBRACE,"'}'");pr->structs=grow_array(pr->structs,sizeof(StructDecl),&pr->struct_cap,pr->struct_count+1);pr->structs[pr->struct_count++]=d;continue;}
if(paccept(p,TK_ENUM)){Token n=pexpect(p,TK_IDENT,"enum name");EnumDecl d={0};d.name=tok_text(n);d.tok=n;pexpect(p,TK_LBRACE,"'{'");size_t cap=0;while(p->cur.kind!=TK_RBRACE&&p->cur.kind!=TK_EOF){Token v=pexpect(p,TK_IDENT,"variant");d.variants=grow_array(d.variants,sizeof(char*),&cap,d.count+1);d.variants[d.count++]=tok_text(v);if(!paccept(p,TK_COMMA))break;}pexpect(p,TK_RBRACE,"'}'");pr->enums=grow_array(pr->enums,sizeof(EnumDecl),&pr->enum_cap,pr->enum_count+1);pr->enums[pr->enum_count++]=d;continue;}
if(paccept(p,TK_FN)){Token n=pexpect(p,TK_IDENT,"function name");Function f={0};f.name=tok_text(n);f.tok=n;f.path=xstrdup(p->path);f.is_comptime=ct;f.is_export=exp;f.is_extern=ext;pexpect(p,TK_LPAREN,"'('");size_t cap=0;if(p->cur.kind!=TK_RPAREN){for(;;){Token pn=pexpect(p,TK_IDENT,"parameter name");pexpect(p,TK_COLON,"':'");Param pa={tok_text(pn),parse_type(p),pn};f.params=grow_array(f.params,sizeof(Param),&cap,f.param_count+1);f.params[f.param_count++]=pa;if(!paccept(p,TK_COMMA))break;}}pexpect(p,TK_RPAREN,"')'");pexpect(p,TK_ARROW,"'->'");f.ret=parse_type(p);if(ext){pexpect(p,TK_SEMI,"';'");}else f.body=parse_block(p);add_fn(pr,f);continue;}
if(paccept(p,TK_CONST)){Token n=pexpect(p,TK_IDENT,"constant name");pexpect(p,TK_COLON,"':'");Constant c={0};c.name=tok_text(n);c.type=parse_type(p);c.tok=n;pexpect(p,TK_ASSIGN,"'='");c.expr=parse_expr(p,0);pexpect(p,TK_SEMI,"';'");add_const(pr,c);continue;}
if(paccept(p,TK_TEST)){Token n=pexpect(p,TK_STRING,"test name");TestDecl td={tok_text(n),parse_block(p),n};pr->tests=grow_array(pr->tests,sizeof(TestDecl),&pr->test_cap,pr->test_count+1);pr->tests[pr->test_count++]=td;continue;}
perr(p,p->cur,"expected declaration");if(p->cur.kind!=TK_EOF)padv(p);}}

/* ---------- module graph ---------- */
typedef struct{char**paths;size_t count,cap;}PathSet;
static bool set_has(PathSet*s,const char*p){for(size_t i=0;i<s->count;i++)if(!strcmp(s->paths[i],p))return true;return false;}
static void set_add(PathSet*s,const char*p){s->paths=grow_array(s->paths,sizeof(char*),&s->cap,s->count+1);s->paths[s->count++]=xstrdup(p);}
static bool load_module_rec(Program*pr,const char*path,PathSet*vis,PathSet*stack,int depth){if(depth>MAX_IMPORT_DEPTH){fprintf(stderr,"dxlc: import depth exceeded at %s\n",path);return false;}char*canon=canonical_path(path);if(set_has(stack,canon)){fprintf(stderr,"dxlc: import cycle involving %s\n",canon);free(canon);return false;}if(set_has(vis,canon)){free(canon);return true;}if(!path_exists(canon)){fprintf(stderr,"dxlc: missing module %s\n",canon);free(canon);return false;}set_add(stack,canon);size_t n=0;char*src=read_file(canon,&n);if(!src){free(canon);return false;}Module m={0};m.path=xstrdup(canon);m.source=src;m.len=n;sha_hex(src,n,m.hash);pr->mods=grow_array(pr->mods,sizeof(Module),&pr->mod_cap,pr->mod_count+1);pr->mods[pr->mod_count++]=m;Parser p;pinit(&p,canon,src,n);parse_module(&p,pr);if(p.errors){free(canon);return false;}char*dir=path_dirname(canon);for(size_t i=0;i<p.import_count;i++){char*child=path_join(dir,p.imports[i]);if(!load_module_rec(pr,child,vis,stack,depth+1)){free(child);free(dir);free(canon);return false;}free(child);}free(dir);stack->count--;set_add(vis,canon);free(canon);return true;}
static bool load_program(const char*entry,Program*pr){memset(pr,0,sizeof(*pr));PathSet v={0},s={0};return load_module_rec(pr,entry,&v,&s,0);}

/* ---------- semantic analysis ---------- */
typedef struct{char*name;Type type;int64_t value;bool moved;bool owner;bool freed;}Binding;
typedef struct Env Env;struct Env{Binding*items;size_t count,cap;Env*parent;};
static Binding*env_find(Env*e,const char*n){for(Env*c=e;c;c=c->parent)for(size_t i=c->count;i>0;i--)if(!strcmp(c->items[i-1].name,n))return&c->items[i-1];return NULL;}
static Binding*env_add(Env*e,const char*n,Type t,bool owner){e->items=grow_array(e->items,sizeof(Binding),&e->cap,e->count+1);Binding*b=&e->items[e->count++];*b=(Binding){xstrdup(n),t,0,false,owner,false};return b;}
static Function*find_fn(Program*p,const char*n){for(size_t i=0;i<p->fn_count;i++)if(!strcmp(p->funcs[i].name,n))return&p->funcs[i];return NULL;}
static Constant*find_const(Program*p,const char*n){for(size_t i=0;i<p->const_count;i++)if(!strcmp(p->consts[i].name,n))return&p->consts[i];return NULL;}
static StructDecl*find_struct(Program*p,const char*n){for(size_t i=0;i<p->struct_count;i++)if(!strcmp(p->structs[i].name,n))return&p->structs[i];return NULL;}
static EnumDecl*find_enum(Program*p,const char*n){for(size_t i=0;i<p->enum_count;i++)if(!strcmp(p->enums[i].name,n))return&p->enums[i];return NULL;}
static StructField*find_field(StructDecl*d,const char*n){for(size_t i=0;i<d->field_count;i++)if(!strcmp(d->fields[i].name,n))return&d->fields[i];return NULL;}
static int enum_variant(EnumDecl*d,const char*n){for(size_t i=0;i<d->count;i++)if(!strcmp(d->variants[i],n))return(int)i;return-1;}
typedef struct{Program*prog;const char*path;const char*target;int errors;uint64_t steps;}Sema;
static void serr(Sema*s,Token t,const char*fmt,...){if(s->errors++>=MAX_ERRORS)return;fprintf(stderr,"%s:%d:%d: error: ",s->path,t.line,t.col);va_list ap;va_start(ap,fmt);vfprintf(stderr,fmt,ap);va_end(ap);fputc('\n',stderr);}
static bool target_builtin(const char*t,const char*n,int64_t*out){bool x86=strstr(t,"x86_64"),arm=strstr(t,"aarch64"),wasm=strstr(t,"wasm32"),win=strstr(t,"windows"),lin=strstr(t,"linux");if(!strcmp(n,"TARGET_X86_64")){*out=x86;return true;}if(!strcmp(n,"TARGET_AARCH64")){*out=arm;return true;}if(!strcmp(n,"TARGET_WASM32")){*out=wasm;return true;}if(!strcmp(n,"TARGET_WINDOWS")){*out=win;return true;}if(!strcmp(n,"TARGET_LINUX")){*out=lin;return true;}return false;}
static Type sema_expr(Sema*s,Env*e,Expr*x);
static Type sema_call(Sema*s,Env*e,Expr*x){const char*n=x->as.call.name;size_t a=x->as.call.argc;
#define ARGC(k) do{if(a!=(k))serr(s,x->tok,"%s expects %d argument(s)",n,(int)(k));}while(0)
if(!strcmp(n,"print_i64")){ARGC(1);if(a&&sema_expr(s,e,x->as.call.args[0]).tag!=TY_I64)serr(s,x->tok,"print_i64 requires i64");return type_make(TY_VOID);}if(!strcmp(n,"print_i32")){ARGC(1);if(a&&sema_expr(s,e,x->as.call.args[0]).tag!=TY_I32)serr(s,x->tok,"print_i32 requires i32");return type_make(TY_VOID);}if(!strcmp(n,"print_bool")){ARGC(1);if(a&&sema_expr(s,e,x->as.call.args[0]).tag!=TY_BOOL)serr(s,x->tok,"print_bool requires bool");return type_make(TY_VOID);}if(!strcmp(n,"arg_count")){ARGC(0);return type_make(TY_I64);}if(!strcmp(n,"read_arg_bytes")){ARGC(1);if(a&&!type_int(sema_expr(s,e,x->as.call.args[0])))serr(s,x->tok,"read_arg_bytes index must be integer");return type_make(TY_ARRAY_I64);}if(!strcmp(n,"write_arg_bytes")){ARGC(2);if(a>0&&!type_int(sema_expr(s,e,x->as.call.args[0])))serr(s,x->tok,"write_arg_bytes index must be integer");if(a>1&&sema_expr(s,e,x->as.call.args[1]).tag!=TY_SLICE_I64)serr(s,x->tok,"write_arg_bytes requires slice_i64 data");return type_make(TY_RESULT_I64);}if(!strcmp(n,"print_bytes")){ARGC(1);if(a&&sema_expr(s,e,x->as.call.args[0]).tag!=TY_SLICE_I64)serr(s,x->tok,"print_bytes requires slice_i64");return type_make(TY_VOID);}if(!strcmp(n,"array_new")){ARGC(2);if(a>0&&!type_int(sema_expr(s,e,x->as.call.args[0])))serr(s,x->tok,"array_new length must be integer");if(a>1&&sema_expr(s,e,x->as.call.args[1]).tag!=TY_I64)serr(s,x->tok,"array_new initializer must be i64");return type_make(TY_ARRAY_I64);}if(!strcmp(n,"array_free")){ARGC(1);if(a){Expr*q=x->as.call.args[0];Type t=sema_expr(s,e,q);if(t.tag!=TY_ARRAY_I64)serr(s,x->tok,"array_free requires array_i64");if(q->kind!=EX_NAME)serr(s,x->tok,"array_free requires an owning local name");else{Binding*b=env_find(e,q->as.name);if(!b||!b->owner)serr(s,x->tok,"array_free requires an owning array local");else if(b->freed)serr(s,x->tok,"array '%s' already freed",b->name);else b->freed=true;}}return type_make(TY_VOID);}if(!strcmp(n,"array_len")){ARGC(1);if(a){Type t=sema_expr(s,e,x->as.call.args[0]);if(t.tag!=TY_ARRAY_I64&&t.tag!=TY_SLICE_I64)serr(s,x->tok,"array_len requires array_i64 or slice_i64");}return type_make(TY_I64);}if(!strcmp(n,"slice")){ARGC(3);if(a>0&&sema_expr(s,e,x->as.call.args[0]).tag!=TY_ARRAY_I64)serr(s,x->tok,"slice source must be array_i64");for(size_t i=1;i<a;i++)if(!type_int(sema_expr(s,e,x->as.call.args[i])))serr(s,x->tok,"slice bounds must be integers");return type_make(TY_SLICE_I64);}if(!strcmp(n,"ok_i64")){ARGC(1);if(a&&sema_expr(s,e,x->as.call.args[0]).tag!=TY_I64)serr(s,x->tok,"ok_i64 requires i64");return type_make(TY_RESULT_I64);}if(!strcmp(n,"err_i64")){ARGC(1);if(a&&sema_expr(s,e,x->as.call.args[0]).tag!=TY_I32)serr(s,x->tok,"err_i64 requires i32 error code");return type_make(TY_RESULT_I64);}if(!strcmp(n,"is_err")){ARGC(1);if(a&&sema_expr(s,e,x->as.call.args[0]).tag!=TY_RESULT_I64)serr(s,x->tok,"is_err requires result_i64");return type_make(TY_BOOL);}if(!strcmp(n,"unwrap_i64")){ARGC(1);if(a&&sema_expr(s,e,x->as.call.args[0]).tag!=TY_RESULT_I64)serr(s,x->tok,"unwrap_i64 requires result_i64");return type_make(TY_I64);}if(!strcmp(n,"error_code")){ARGC(1);if(a&&sema_expr(s,e,x->as.call.args[0]).tag!=TY_RESULT_I64)serr(s,x->tok,"error_code requires result_i64");return type_make(TY_I32);}
Function*f=find_fn(s->prog,n);if(!f){serr(s,x->tok,"unknown function '%s'",n);return type_make(TY_INVALID);}if(a!=f->param_count)serr(s,x->tok,"function '%s' expects %zu argument(s)",n,f->param_count);size_t m=a<f->param_count?a:f->param_count;for(size_t i=0;i<m;i++){Type t=sema_expr(s,e,x->as.call.args[i]);if(!type_eq(t,f->params[i].type))serr(s,x->as.call.args[i]->tok,"argument %zu is %s, expected %s",i+1,type_name(t),type_name(f->params[i].type));}return f->ret;
#undef ARGC
}
static Type sema_expr(Sema*s,Env*e,Expr*x){switch(x->kind){case EX_INT:x->type=type_make(TY_I64);break;case EX_BOOL:x->type=type_make(TY_BOOL);break;case EX_NAME:{Binding*b=env_find(e,x->as.name);if(b){if(b->freed)serr(s,x->tok,"use after free of '%s'",b->name);x->type=b->type;break;}Constant*c=find_const(s->prog,x->as.name);if(c){x->type=c->type;break;}int64_t v;if(target_builtin(s->target,x->as.name,&v)){x->type=type_make(TY_BOOL);break;}if(find_enum(s->prog,x->as.name)){x->type=type_named(x->as.name);break;}serr(s,x->tok,"unknown name '%s'",x->as.name);x->type=type_make(TY_INVALID);break;}case EX_UNARY:{Type a=sema_expr(s,e,x->as.un.inner);if(x->as.un.op==TK_MINUS&&type_int(a))x->type=a;else if(x->as.un.op==TK_BANG&&a.tag==TY_BOOL)x->type=type_make(TY_BOOL);else{serr(s,x->tok,"invalid unary operator for %s",type_name(a));x->type=type_make(TY_INVALID);}break;}case EX_BINARY:{Type a=sema_expr(s,e,x->as.bin.l),b=sema_expr(s,e,x->as.bin.r);TokenKind op=x->as.bin.op;if(op==TK_AND||op==TK_OR){if(a.tag!=TY_BOOL||b.tag!=TY_BOOL)serr(s,x->tok,"logical operator requires bool");x->type=type_make(TY_BOOL);}else if(op==TK_EQ||op==TK_NE){if(!type_eq(a,b))serr(s,x->tok,"comparison type mismatch: %s vs %s",type_name(a),type_name(b));else if(!(type_int(a)||a.tag==TY_BOOL||(a.tag==TY_NAMED&&find_enum(s->prog,a.name))))serr(s,x->tok,"equality is not defined for %s",type_name(a));x->type=type_make(TY_BOOL);}else if(op==TK_LT||op==TK_LE||op==TK_GT||op==TK_GE){if(!type_int(a)||!type_eq(a,b))serr(s,x->tok,"ordered comparison requires matching integers");x->type=type_make(TY_BOOL);}else{if(!type_int(a)||!type_eq(a,b))serr(s,x->tok,"arithmetic requires matching integers");x->type=a;}break;}case EX_CALL:x->type=sema_call(s,e,x);break;case EX_FIELD:{if(x->as.field.base->kind==EX_NAME){EnumDecl*d=find_enum(s->prog,x->as.field.base->as.name);if(d){if(enum_variant(d,x->as.field.name)<0)serr(s,x->tok,"unknown variant %s.%s",d->name,x->as.field.name);x->type=type_named(d->name);break;}}Type b=sema_expr(s,e,x->as.field.base);if(b.tag!=TY_NAMED){serr(s,x->tok,"field access requires struct or enum");x->type=type_make(TY_INVALID);break;}StructDecl*d=find_struct(s->prog,b.name);if(!d){serr(s,x->tok,"'%s' is not a struct",b.name);x->type=type_make(TY_INVALID);break;}StructField*f=find_field(d,x->as.field.name);if(!f){serr(s,x->tok,"unknown field '%s.%s'",d->name,x->as.field.name);x->type=type_make(TY_INVALID);}else x->type=f->type;break;}case EX_INDEX:{Type b=sema_expr(s,e,x->as.index.base),i=sema_expr(s,e,x->as.index.index);if(b.tag!=TY_ARRAY_I64&&b.tag!=TY_SLICE_I64)serr(s,x->tok,"indexing requires array_i64 or slice_i64");if(!type_int(i))serr(s,x->tok,"index must be integer");x->type=type_make(TY_I64);break;}case EX_STRUCT_INIT:{StructDecl*d=find_struct(s->prog,x->as.sinit.type_name);if(!d){serr(s,x->tok,"unknown struct '%s'",x->as.sinit.type_name);x->type=type_make(TY_INVALID);break;}for(size_t i=0;i<d->field_count;i++){FieldInit*got=NULL;for(size_t j=0;j<x->as.sinit.count;j++)if(!strcmp(d->fields[i].name,x->as.sinit.fields[j].name))got=&x->as.sinit.fields[j];if(!got)serr(s,x->tok,"missing field '%s.%s'",d->name,d->fields[i].name);else{Type t=sema_expr(s,e,got->value);if(!type_eq(t,d->fields[i].type))serr(s,got->value->tok,"field '%s' is %s, expected %s",d->fields[i].name,type_name(t),type_name(d->fields[i].type));}}for(size_t j=0;j<x->as.sinit.count;j++)if(!find_field(d,x->as.sinit.fields[j].name))serr(s,x->tok,"unknown field '%s.%s'",d->name,x->as.sinit.fields[j].name);x->type=type_named(d->name);break;}case EX_CAST:{Type a=sema_expr(s,e,x->as.cast.value),b=x->as.cast.to;if(!((type_int(a)&&type_int(b))||(a.tag==TY_BOOL&&type_int(b))||(type_int(a)&&b.tag==TY_BOOL)))serr(s,x->tok,"unsupported checked cast %s to %s",type_name(a),type_name(b));x->type=b;break;}}return x->type;}
typedef struct{Binding**bindings;bool*freed;size_t count,cap;}OwnerSnap;
static void owner_snapshot(Env*e,OwnerSnap*s){memset(s,0,sizeof(*s));for(Env*c=e;c;c=c->parent)for(size_t i=0;i<c->count;i++)if(c->items[i].owner){s->bindings=grow_array(s->bindings,sizeof(Binding*),&s->cap,s->count+1);s->freed=realloc(s->freed,(s->count+1)*sizeof(bool));if(!s->freed)die_oom();s->bindings[s->count]=&c->items[i];s->freed[s->count]=c->items[i].freed;s->count++;}}
static void owner_restore(const OwnerSnap*s){for(size_t i=0;i<s->count;i++)s->bindings[i]->freed=s->freed[i];}
static bool owner_same(const OwnerSnap*a,const OwnerSnap*b){if(a->count!=b->count)return false;for(size_t i=0;i<a->count;i++)if(a->bindings[i]!=b->bindings[i]||a->freed[i]!=b->freed[i])return false;return true;}
static void owner_free_snap(OwnerSnap*s){free(s->bindings);free(s->freed);memset(s,0,sizeof(*s));}
static bool sema_stmt(Sema*s,Env*e,Stmt*st,Type ret,bool*always){*always=false;switch(st->kind){case ST_BLOCK:{Env c={0};c.parent=e;bool ar=false;for(size_t i=0;i<st->as.block.count;i++){bool r=false;sema_stmt(s,&c,st->as.block.items[i],ret,&r);if(r)ar=true;}for(size_t i=0;i<c.count;i++)if(c.items[i].owner&&!c.items[i].freed)serr(s,st->tok,"owned array '%s' leaves scope without array_free",c.items[i].name);*always=ar;return true;}case ST_LET:{if(env_find(e,st->as.let.name))serr(s,st->tok,"duplicate local '%s'",st->as.let.name);Type t=sema_expr(s,e,st->as.let.value);if(!type_eq(t,st->as.let.type))serr(s,st->tok,"initializer is %s, expected %s",type_name(t),type_name(st->as.let.type));bool owner=st->as.let.type.tag==TY_ARRAY_I64;if(owner&&st->as.let.value->kind!=EX_CALL)serr(s,st->tok,"array owner must be initialized by array_new");env_add(e,st->as.let.name,st->as.let.type,owner);return true;}case ST_ASSIGN:{Binding*b=env_find(e,st->as.assign.name);if(!b){serr(s,st->tok,"unknown local '%s'",st->as.assign.name);return false;}if(b->owner){serr(s,st->tok,"owned arrays cannot be copied or reassigned");return false;}Type t=sema_expr(s,e,st->as.assign.value);if(!type_eq(t,b->type))serr(s,st->tok,"assignment is %s, expected %s",type_name(t),type_name(b->type));return true;}case ST_INDEX_ASSIGN:{Type b=sema_expr(s,e,st->as.idx_assign.base),i=sema_expr(s,e,st->as.idx_assign.index),v=sema_expr(s,e,st->as.idx_assign.value);if(b.tag!=TY_ARRAY_I64&&b.tag!=TY_SLICE_I64)serr(s,st->tok,"indexed assignment requires array or slice");if(!type_int(i)||v.tag!=TY_I64)serr(s,st->tok,"index assignment requires integer index and i64 value");return true;}case ST_RETURN:{if(ret.tag==TY_VOID&&st->as.ret_expr)serr(s,st->tok,"void function cannot return a value");else if(ret.tag!=TY_VOID&&!st->as.ret_expr)serr(s,st->tok,"function must return %s",type_name(ret));else if(st->as.ret_expr){Type t=sema_expr(s,e,st->as.ret_expr);if(!type_eq(t,ret))serr(s,st->tok,"return is %s, expected %s",type_name(t),type_name(ret));}*always=true;return true;}case ST_EXPR:sema_expr(s,e,st->as.expr);return true;case ST_ASSERT:if(sema_expr(s,e,st->as.assert_expr).tag!=TY_BOOL)serr(s,st->tok,"assert requires bool");return true;case ST_IF:{if(sema_expr(s,e,st->as.ifs.cond).tag!=TY_BOOL)serr(s,st->tok,"if condition requires bool");OwnerSnap before={0},ta={0},tb={0};owner_snapshot(e,&before);bool a=false,b=false;sema_stmt(s,e,st->as.ifs.then_b,ret,&a);owner_snapshot(e,&ta);owner_restore(&before);if(st->as.ifs.else_b)sema_stmt(s,e,st->as.ifs.else_b,ret,&b);owner_snapshot(e,&tb);if(!owner_same(&ta,&tb))serr(s,st->tok,"owned resources must have identical state on both branches");else owner_restore(&ta);owner_free_snap(&before);owner_free_snap(&ta);owner_free_snap(&tb);*always=a&&b;return true;}case ST_WHILE:{if(sema_expr(s,e,st->as.whiles.cond).tag!=TY_BOOL)serr(s,st->tok,"while condition requires bool");OwnerSnap before={0},after={0};owner_snapshot(e,&before);bool a=false;sema_stmt(s,e,st->as.whiles.body,ret,&a);owner_snapshot(e,&after);if(!owner_same(&before,&after))serr(s,st->tok,"owned resources cannot be consumed inside a loop");owner_restore(&before);owner_free_snap(&before);owner_free_snap(&after);return true;}}return true;}

typedef struct{bool returned;int64_t value;}EvalRes;
static bool eval_checked_add(Sema*s,Token t,int64_t a,int64_t b,int64_t*out){if(__builtin_add_overflow(a,b,out)){serr(s,t,"compile-time i64 addition overflow");return false;}return true;}
static bool eval_checked_sub(Sema*s,Token t,int64_t a,int64_t b,int64_t*out){if(__builtin_sub_overflow(a,b,out)){serr(s,t,"compile-time i64 subtraction overflow");return false;}return true;}
static bool eval_checked_mul(Sema*s,Token t,int64_t a,int64_t b,int64_t*out){if(__builtin_mul_overflow(a,b,out)){serr(s,t,"compile-time i64 multiplication overflow");return false;}return true;}

static bool eval_expr(Sema*s,Env*e,Expr*x,int depth,int64_t*out);
static bool eval_constant(Sema*s,Constant*c,int depth,int64_t*out);
static EvalRes eval_stmt(Sema*s,Env*e,Stmt*st,int depth){EvalRes r={0};if(++s->steps>MAX_EVAL_STEPS){serr(s,st->tok,"compile-time step limit exceeded");r.returned=true;return r;}switch(st->kind){case ST_BLOCK:{Env c={0};c.parent=e;for(size_t i=0;i<st->as.block.count;i++){r=eval_stmt(s,&c,st->as.block.items[i],depth);if(r.returned)return r;}return r;}case ST_LET:{int64_t v=0;if(eval_expr(s,e,st->as.let.value,depth,&v)){Binding*b=env_add(e,st->as.let.name,st->as.let.type,false);b->value=v;b->moved=false;}return r;}case ST_ASSIGN:{Binding*b=env_find(e,st->as.assign.name);int64_t v=0;if(b&&eval_expr(s,e,st->as.assign.value,depth,&v))b->value=v;return r;}case ST_INDEX_ASSIGN:return r;case ST_RETURN:r.returned=true;if(st->as.ret_expr)eval_expr(s,e,st->as.ret_expr,depth,&r.value);return r;case ST_EXPR:{int64_t v;eval_expr(s,e,st->as.expr,depth,&v);return r;}case ST_ASSERT:{int64_t v=0;if(!eval_expr(s,e,st->as.assert_expr,depth,&v)||!v)serr(s,st->tok,"compile-time assertion failed");return r;}case ST_IF:{int64_t v=0;if(eval_expr(s,e,st->as.ifs.cond,depth,&v)){if(v)return eval_stmt(s,e,st->as.ifs.then_b,depth);if(st->as.ifs.else_b)return eval_stmt(s,e,st->as.ifs.else_b,depth);}return r;}case ST_WHILE:{for(;;){int64_t v=0;if(!eval_expr(s,e,st->as.whiles.cond,depth,&v)||!v)break;r=eval_stmt(s,e,st->as.whiles.body,depth);if(r.returned)return r;if(++s->steps>MAX_EVAL_STEPS){serr(s,st->tok,"compile-time loop limit exceeded");break;}}return r;}}return r;}
static bool eval_expr(Sema*s,Env*e,Expr*x,int depth,int64_t*out){if(depth>MAX_RECURSION){serr(s,x->tok,"compile-time recursion limit exceeded");return false;}if(++s->steps>MAX_EVAL_STEPS){serr(s,x->tok,"compile-time step limit exceeded");return false;}switch(x->kind){case EX_INT:*out=x->as.int_value;return true;case EX_BOOL:*out=x->as.bool_value;return true;case EX_NAME:{Binding*b=env_find(e,x->as.name);if(b){*out=b->value;return true;}Constant*c=find_const(s->prog,x->as.name);if(c)return eval_constant(s,c,depth+1,out);int64_t v;if(target_builtin(s->target,x->as.name,&v)){*out=v;return true;}serr(s,x->tok,"'%s' is not compile-time known",x->as.name);return false;}case EX_UNARY:{int64_t a;if(!eval_expr(s,e,x->as.un.inner,depth,&a))return false;if(x->as.un.op==TK_MINUS){if(a==INT64_MIN){serr(s,x->tok,"compile-time i64 negation overflow");return false;}*out=-a;}else *out=!a;return true;}case EX_BINARY:{int64_t a,b;if(!eval_expr(s,e,x->as.bin.l,depth,&a)||!eval_expr(s,e,x->as.bin.r,depth,&b))return false;switch(x->as.bin.op){case TK_PLUS:return eval_checked_add(s,x->tok,a,b,out);case TK_MINUS:return eval_checked_sub(s,x->tok,a,b,out);case TK_STAR:return eval_checked_mul(s,x->tok,a,b,out);case TK_SLASH:if(!b){serr(s,x->tok,"division by zero");return false;}if(a==INT64_MIN&&b==-1){serr(s,x->tok,"compile-time i64 division overflow");return false;}*out=a/b;break;case TK_PERCENT:if(!b){serr(s,x->tok,"modulo by zero");return false;}if(a==INT64_MIN&&b==-1){*out=0;break;}*out=a%b;break;case TK_EQ:*out=a==b;break;case TK_NE:*out=a!=b;break;case TK_LT:*out=a<b;break;case TK_LE:*out=a<=b;break;case TK_GT:*out=a>b;break;case TK_GE:*out=a>=b;break;case TK_AND:*out=a&&b;break;case TK_OR:*out=a||b;break;default:return false;}return true;}case EX_CALL:{Function*f=find_fn(s->prog,x->as.call.name);if(!f||!f->is_comptime){serr(s,x->tok,"call to non-comptime function '%s'",x->as.call.name);return false;}if(x->as.call.argc!=f->param_count)return false;Env local={0};for(size_t i=0;i<f->param_count;i++){int64_t v;if(!eval_expr(s,e,x->as.call.args[i],depth+1,&v))return false;Binding*b=env_add(&local,f->params[i].name,f->params[i].type,false);b->value=v;}EvalRes r=eval_stmt(s,&local,f->body,depth+1);if(!r.returned)return false;*out=r.value;return true;}case EX_FIELD:{if(x->as.field.base->kind==EX_NAME){EnumDecl*d=find_enum(s->prog,x->as.field.base->as.name);int v=d?enum_variant(d,x->as.field.name):-1;if(v>=0){*out=v;return true;}}return false;}case EX_CAST:{int64_t v;if(!eval_expr(s,e,x->as.cast.value,depth,&v))return false;if(x->as.cast.to.tag==TY_I32&&(v<INT32_MIN||v>INT32_MAX)){serr(s,x->tok,"checked cast overflows i32");return false;}if(x->as.cast.to.tag==TY_BOOL&&v!=0&&v!=1){serr(s,x->tok,"checked cast to bool requires 0 or 1");return false;}*out=v;return true;}default:serr(s,x->tok,"expression is not supported at compile time");return false;}}
static bool eval_constant(Sema*s,Constant*c,int depth,int64_t*out){
    if(c->evaluated){*out=c->value;return true;}
    if(c->evaluating){serr(s,c->tok,"cyclic constant dependency involving '%s'",c->name);return false;}
    if(depth>MAX_RECURSION){serr(s,c->tok,"constant dependency recursion limit exceeded");return false;}
    c->evaluating=true;
    Env e={0};
    int64_t v=0;
    bool ok=eval_expr(s,&e,c->expr,depth+1,&v);
    c->evaluating=false;
    if(ok){c->value=v;c->evaluated=true;*out=v;}
    return ok;
}

static bool type_declared(Program*p,Type t){
    if(t.tag!=TY_NAMED) return t.tag!=TY_INVALID;
    return find_struct(p,t.name)!=NULL||find_enum(p,t.name)!=NULL;
}
static int struct_index(Program*p,const char*n){for(size_t i=0;i<p->struct_count;i++)if(!strcmp(p->structs[i].name,n))return(int)i;return-1;}
static bool validate_struct_cycle(Sema*s,size_t idx,uint8_t*state){
    if(state[idx]==2) return true;
    if(state[idx]==1){serr(s,s->prog->structs[idx].tok,"recursive by-value struct cycle involving '%s'",s->prog->structs[idx].name);return false;}
    state[idx]=1;
    StructDecl*d=&s->prog->structs[idx];
    bool ok=true;
    for(size_t i=0;i<d->field_count;i++){
        Type t=d->fields[i].type;
        if(t.tag==TY_NAMED){int child=struct_index(s->prog,t.name);if(child>=0&&!validate_struct_cycle(s,(size_t)child,state))ok=false;}
    }
    state[idx]=2;
    return ok;
}
static void validate_declarations(Sema*s){
    Program*p=s->prog;
    for(size_t i=0;i<p->struct_count;i++){
        StructDecl*d=&p->structs[i];
        if(find_enum(p,d->name))serr(s,d->tok,"type name '%s' is used by both a struct and enum",d->name);
        for(size_t j=0;j<d->field_count;j++){
            StructField*f=&d->fields[j];
            if(!type_declared(p,f->type))serr(s,f->tok,"unknown field type '%s'",type_name(f->type));
            if(f->type.tag==TY_VOID)serr(s,f->tok,"struct fields cannot have type void");
            if(f->type.tag==TY_ARRAY_I64||f->type.tag==TY_SLICE_I64)serr(s,f->tok,"owned arrays and borrowed slices are not allowed as struct fields in 0.2");
            for(size_t k=j+1;k<d->field_count;k++)if(!strcmp(f->name,d->fields[k].name))serr(s,d->fields[k].tok,"duplicate field '%s.%s'",d->name,f->name);
        }
    }
    for(size_t i=0;i<p->enum_count;i++){
        EnumDecl*d=&p->enums[i];
        for(size_t j=0;j<d->count;j++)for(size_t k=j+1;k<d->count;k++)if(!strcmp(d->variants[j],d->variants[k]))serr(s,d->tok,"duplicate enum variant '%s.%s'",d->name,d->variants[j]);
    }
    for(size_t i=0;i<p->fn_count;i++){
        Function*f=&p->funcs[i];
        if(!type_declared(p,f->ret))serr(s,f->tok,"unknown return type '%s'",type_name(f->ret));
        if(f->ret.tag==TY_ARRAY_I64||f->ret.tag==TY_SLICE_I64)serr(s,f->tok,"functions cannot return owned arrays or borrowed slices in 0.2");
        for(size_t j=0;j<f->param_count;j++){
            if(!type_declared(p,f->params[j].type)||f->params[j].type.tag==TY_VOID)serr(s,f->params[j].tok,"invalid parameter type '%s'",type_name(f->params[j].type));
            for(size_t k=j+1;k<f->param_count;k++)if(!strcmp(f->params[j].name,f->params[k].name))serr(s,f->params[k].tok,"duplicate parameter '%s'",f->params[j].name);
        }
    }
    for(size_t i=0;i<p->const_count;i++){
        Constant*c=&p->consts[i];
        bool scalar=c->type.tag==TY_I64||c->type.tag==TY_I32||c->type.tag==TY_BOOL||(c->type.tag==TY_NAMED&&find_enum(p,c->type.name));
        if(!type_declared(p,c->type))serr(s,c->tok,"unknown constant type '%s'",type_name(c->type));
        else if(!scalar)serr(s,c->tok,"compile-time constants support integers, bool, and enums only");
        for(size_t j=i+1;j<p->const_count;j++)if(!strcmp(c->name,p->consts[j].name))serr(s,p->consts[j].tok,"duplicate constant '%s'",c->name);
    }
    uint8_t*state=calloc(p->struct_count?p->struct_count:1,1);if(!state)die_oom();
    for(size_t i=0;i<p->struct_count;i++)validate_struct_cycle(s,i,state);
    free(state);
}

static bool sema_program(Program*p,const char*target){p->target=target;Sema s={p,p->mods[0].path,target,0,0};validate_declarations(&s);for(size_t i=0;i<p->struct_count;i++){for(size_t j=i+1;j<p->struct_count;j++)if(!strcmp(p->structs[i].name,p->structs[j].name))serr(&s,p->structs[j].tok,"duplicate struct '%s'",p->structs[i].name);}for(size_t i=0;i<p->enum_count;i++)for(size_t j=i+1;j<p->enum_count;j++)if(!strcmp(p->enums[i].name,p->enums[j].name))serr(&s,p->enums[j].tok,"duplicate enum '%s'",p->enums[i].name);for(size_t i=0;i<p->fn_count;i++)for(size_t j=i+1;j<p->fn_count;j++)if(!strcmp(p->funcs[i].name,p->funcs[j].name))serr(&s,p->funcs[j].tok,"duplicate function '%s'",p->funcs[i].name);
for(size_t i=0;i<p->const_count;i++){Constant*c=&p->consts[i];Env e={0};Type t=sema_expr(&s,&e,c->expr);if(!type_eq(t,c->type))serr(&s,c->tok,"constant is %s, expected %s",type_name(t),type_name(c->type));int64_t v=0;eval_constant(&s,c,0,&v);}
for(size_t i=0;i<p->fn_count;i++){Function*f=&p->funcs[i];s.path=f->path;Env e={0};for(size_t j=0;j<f->param_count;j++){if(f->params[j].type.tag==TY_ARRAY_I64)serr(&s,f->params[j].tok,"array_i64 parameters are forbidden; pass slice_i64 to borrow");env_add(&e,f->params[j].name,f->params[j].type,false);}if(f->body){bool ar=false;sema_stmt(&s,&e,f->body,f->ret,&ar);if(f->ret.tag!=TY_VOID&&!ar)serr(&s,f->tok,"function '%s' may not return on every path",f->name);}}
for(size_t i=0;i<p->ct_count;i++){Env e={0};bool ar=false;sema_stmt(&s,&e,p->ct_blocks[i],type_make(TY_VOID),&ar);eval_stmt(&s,&e,p->ct_blocks[i],0);}for(size_t i=0;i<p->test_count;i++){Env e={0};bool ar=false;sema_stmt(&s,&e,p->tests[i].body,type_make(TY_VOID),&ar);}return s.errors==0;}

/* ---------- C code generator ---------- */
static const char*c_type(Type t){switch(t.tag){case TY_I64:return"int64_t";case TY_I32:return"int32_t";case TY_BOOL:return"bool";case TY_VOID:return"void";case TY_ARRAY_I64:return"dxl_array_i64";case TY_SLICE_I64:return"dxl_slice_i64";case TY_RESULT_I64:return"dxl_result_i64";case TY_NAMED:return t.name;default:return"int64_t";}}
typedef struct{Program*p;StrBuf out;bool in_test;}CG;
static void cg_expr(CG*c,Expr*x);
static const char*c_fn_name(const char*n){return!strcmp(n,"main")?"dxl_user_main":n;}
static void cg_expr(CG*c,Expr*x){
    switch(x->kind){
        case EX_INT: sb_printf(&c->out,"((int64_t)%lldLL)",(long long)x->as.int_value); break;
        case EX_BOOL: sb_append(&c->out,x->as.bool_value?"true":"false"); break;
        case EX_NAME:{int64_t target_value=0;if(c->p->target&&target_builtin(c->p->target,x->as.name,&target_value))sb_append(&c->out,target_value?"true":"false");else sb_append(&c->out,x->as.name);break;}
        case EX_UNARY:
            if(x->as.un.op==TK_MINUS&&type_int(x->type)){
                sb_append(&c->out,x->type.tag==TY_I32?"dxl_i32_neg(":"dxl_i64_neg(");cg_expr(c,x->as.un.inner);sb_putc(&c->out,')');
            }else{sb_putc(&c->out,'(');sb_append(&c->out,"!");cg_expr(c,x->as.un.inner);sb_putc(&c->out,')');}
            break;
        case EX_BINARY:{
            TokenKind opk=x->as.bin.op;
            if(opk==TK_PLUS||opk==TK_MINUS||opk==TK_STAR||opk==TK_SLASH||opk==TK_PERCENT){
                const char*base=x->type.tag==TY_I32?"dxl_i32_":"dxl_i64_";const char*tail=opk==TK_PLUS?"add(":opk==TK_MINUS?"sub(":opk==TK_STAR?"mul(":opk==TK_SLASH?"div(":"mod(";
                sb_append(&c->out,base);sb_append(&c->out,tail);cg_expr(c,x->as.bin.l);sb_append(&c->out,", ");cg_expr(c,x->as.bin.r);sb_putc(&c->out,')');break;
            }
            const char*op="?";switch(opk){case TK_EQ:op="==";break;case TK_NE:op="!=";break;case TK_LT:op="<";break;case TK_LE:op="<=";break;case TK_GT:op=">";break;case TK_GE:op=">=";break;case TK_AND:op="&&";break;case TK_OR:op="||";break;default:break;}
            sb_putc(&c->out,'(');cg_expr(c,x->as.bin.l);sb_printf(&c->out," %s ",op);cg_expr(c,x->as.bin.r);sb_putc(&c->out,')');break;
        }
        case EX_CALL:{
            const char*n=x->as.call.name,*cn=n;
            if(!strcmp(n,"print_i64"))cn="dxl_print_i64";
            else if(!strcmp(n,"print_i32"))cn="dxl_print_i32";
            else if(!strcmp(n,"print_bool"))cn="dxl_print_bool";
            else if(!strcmp(n,"arg_count"))cn="dxl_arg_count";
            else if(!strcmp(n,"read_arg_bytes"))cn="dxl_read_arg_bytes";
            else if(!strcmp(n,"write_arg_bytes"))cn="dxl_write_arg_bytes";
            else if(!strcmp(n,"print_bytes"))cn="dxl_print_bytes";
            else if(!strcmp(n,"array_new"))cn="dxl_array_new";
            else if(!strcmp(n,"array_free"))cn="dxl_array_free";
            else if(!strcmp(n,"array_len"))cn="dxl_len";
            else if(!strcmp(n,"slice"))cn="dxl_slice";
            else if(!strcmp(n,"ok_i64"))cn="dxl_ok_i64";
            else if(!strcmp(n,"err_i64"))cn="dxl_err_i64";
            else if(!strcmp(n,"is_err"))cn="dxl_is_err";
            else if(!strcmp(n,"unwrap_i64"))cn="dxl_unwrap_i64";
            else if(!strcmp(n,"error_code"))cn="dxl_error_code";
            sb_printf(&c->out,"%s(",c_fn_name(cn));
            for(size_t i=0;i<x->as.call.argc;i++){if(i)sb_append(&c->out,", ");cg_expr(c,x->as.call.args[i]);}
            sb_putc(&c->out,')');break;
        }
        case EX_FIELD:
            if(x->as.field.base->kind==EX_NAME&&find_enum(c->p,x->as.field.base->as.name))
                sb_printf(&c->out,"%s_%s",x->as.field.base->as.name,x->as.field.name);
            else {sb_putc(&c->out,'(');cg_expr(c,x->as.field.base);sb_printf(&c->out,").%s",x->as.field.name);}break;
        case EX_INDEX:
            sb_append(&c->out,x->as.index.base->type.tag==TY_ARRAY_I64?"dxl_array_get(":"dxl_slice_get(");
            cg_expr(c,x->as.index.base);sb_append(&c->out,", ");cg_expr(c,x->as.index.index);sb_putc(&c->out,')');break;
        case EX_STRUCT_INIT:
            sb_printf(&c->out,"(%s){",x->as.sinit.type_name);
            for(size_t i=0;i<x->as.sinit.count;i++){if(i)sb_append(&c->out,", ");sb_printf(&c->out,".%s = ",x->as.sinit.fields[i].name);cg_expr(c,x->as.sinit.fields[i].value);}sb_putc(&c->out,'}');break;
        case EX_CAST:
            if(x->as.cast.to.tag==TY_I32)sb_append(&c->out,"dxl_checked_i32(");
            else if(x->as.cast.to.tag==TY_I64)sb_append(&c->out,"dxl_checked_i64(");
            else sb_append(&c->out,"dxl_checked_bool(");
            cg_expr(c,x->as.cast.value);sb_putc(&c->out,')');break;
    }
}
static void indent(StrBuf*b,int n){for(int i=0;i<n;i++)sb_append(b,"    ");}
static void cg_stmt(CG*c,Stmt*s,int d);
static void cg_block(CG*c,Stmt*s,int d){sb_append(&c->out,"{\n");for(size_t i=0;i<s->as.block.count;i++)cg_stmt(c,s->as.block.items[i],d+1);indent(&c->out,d);sb_append(&c->out,"}\n");}
static void cg_stmt(CG*c,Stmt*s,int d){
    indent(&c->out,d);
    switch(s->kind){
        case ST_BLOCK:cg_block(c,s,d);break;
        case ST_LET:sb_printf(&c->out,"%s %s = ",c_type(s->as.let.type),s->as.let.name);cg_expr(c,s->as.let.value);sb_append(&c->out,";\n");break;
        case ST_ASSIGN:sb_printf(&c->out,"%s = ",s->as.assign.name);cg_expr(c,s->as.assign.value);sb_append(&c->out,";\n");break;
        case ST_INDEX_ASSIGN:
            sb_append(&c->out,s->as.idx_assign.base->type.tag==TY_ARRAY_I64?"dxl_array_set(":"dxl_slice_set(");
            cg_expr(c,s->as.idx_assign.base);sb_append(&c->out,", ");cg_expr(c,s->as.idx_assign.index);sb_append(&c->out,", ");cg_expr(c,s->as.idx_assign.value);sb_append(&c->out,");\n");break;
        case ST_RETURN:sb_append(&c->out,"return");if(s->as.ret_expr){sb_putc(&c->out,' ');cg_expr(c,s->as.ret_expr);}sb_append(&c->out,";\n");break;
        case ST_EXPR:cg_expr(c,s->as.expr);sb_append(&c->out,";\n");break;
        case ST_ASSERT:
            if(c->in_test){sb_append(&c->out,"if (!(");cg_expr(c,s->as.assert_expr);sb_append(&c->out,")) return false;\n");}
            else{sb_append(&c->out,"dxl_assert(");cg_expr(c,s->as.assert_expr);sb_append(&c->out,");\n");}break;
        case ST_IF:
            sb_append(&c->out,"if (dxl_truth(");cg_expr(c,s->as.ifs.cond);sb_append(&c->out,")) ");cg_block(c,s->as.ifs.then_b,d);
            if(s->as.ifs.else_b){indent(&c->out,d);sb_append(&c->out,"else ");if(s->as.ifs.else_b->kind==ST_IF)cg_stmt(c,s->as.ifs.else_b,d);else cg_block(c,s->as.ifs.else_b,d);}break;
        case ST_WHILE:sb_append(&c->out,"while (dxl_truth(");cg_expr(c,s->as.whiles.cond);sb_append(&c->out,")) ");cg_block(c,s->as.whiles.body,d);break;
    }
}
static void emit_c(Program*p,bool tests,StrBuf*out){
    CG c={0};c.p=p;c.in_test=false;sb_init(&c.out);
    sb_printf(&c.out,"/* Generated by dxlc %s. Deterministic C11 backend. */\n",DXL_VERSION_STRING);
    sb_append(&c.out,"typedef __INT64_TYPE__ int64_t;\ntypedef __INT32_TYPE__ int32_t;\ntypedef __UINT64_TYPE__ uint64_t;\ntypedef __SIZE_TYPE__ size_t;\ntypedef _Bool bool;\n#define true 1\n#define false 0\n#define DXL_SIZE_MAX ((size_t)-1)\n#define DXL_INT32_MIN (-2147483647-1)\n#define DXL_INT32_MAX 2147483647\nextern int printf(const char*, ...);\nextern int puts(const char*);\nextern int putchar(int);\nextern int fflush(void*);\nextern void *malloc(size_t);\nextern void free(void*);\nextern void abort(void);\nextern int atexit(void (*)(void));\ntypedef struct dxl_FILE dxl_FILE;\nextern dxl_FILE *dxl_fopen(const char*, const char*) __asm__(\"fopen\");\nextern int dxl_fclose(dxl_FILE*) __asm__(\"fclose\");\nextern int dxl_fseek(dxl_FILE*, long, int) __asm__(\"fseek\");\nextern long dxl_ftell(dxl_FILE*) __asm__(\"ftell\");\nextern size_t dxl_fread(void*, size_t, size_t, dxl_FILE*) __asm__(\"fread\");\nextern size_t dxl_fwrite(const void*, size_t, size_t, dxl_FILE*) __asm__(\"fwrite\");\n#define DXL_SEEK_SET 0\n#define DXL_SEEK_END 2\nstatic int dxl_argc = 0;\nstatic char **dxl_argv = 0;\n\n");
    sb_append(&c.out,
"typedef struct dxl_arr_hdr { uint64_t magic; size_t len; bool freed; int64_t *data; struct dxl_arr_hdr *next; } dxl_arr_hdr;\n"
"typedef struct { dxl_arr_hdr *h; } dxl_array_i64;\n"
"typedef struct { dxl_arr_hdr *owner; size_t start; size_t len; } dxl_slice_i64;\n"
"typedef struct { bool is_err; int32_t err; int64_t value; } dxl_result_i64;\n"
"static const uint64_t DXL_ARRAY_MAGIC = ((uint64_t)0x44584c4152524159ULL);\n"
"static void dxl_panic(const char *m){printf(\"Aegis panic: %s\\n\",m);fflush((void*)0);abort();}\n"
"static bool dxl_truth(bool x){return x;}\n"
"static void dxl_assert(bool x){if(!x)dxl_panic(\"assertion failed\");}\n"
"static int32_t dxl_checked_i32(int64_t x){if(x<DXL_INT32_MIN||x>DXL_INT32_MAX)dxl_panic(\"checked cast overflow\");return (int32_t)x;}\n"
"static int64_t dxl_checked_i64(int64_t x){return x;}\n"
"static bool dxl_checked_bool(int64_t x){if(x!=0&&x!=1)dxl_panic(\"checked bool cast requires 0 or 1\");return x!=0;}\n");
    sb_append(&c.out,
"static int64_t dxl_i64_add(int64_t a,int64_t b){int64_t r;if(__builtin_add_overflow(a,b,&r))dxl_panic(\"i64 addition overflow\");return r;}\n"
"static int64_t dxl_i64_sub(int64_t a,int64_t b){int64_t r;if(__builtin_sub_overflow(a,b,&r))dxl_panic(\"i64 subtraction overflow\");return r;}\n"
"static int64_t dxl_i64_mul(int64_t a,int64_t b){int64_t r;if(__builtin_mul_overflow(a,b,&r))dxl_panic(\"i64 multiplication overflow\");return r;}\n"
"static int64_t dxl_i64_div(int64_t a,int64_t b){if(!b)dxl_panic(\"division by zero\");if(a==(-9223372036854775807LL-1)&&b==-1)dxl_panic(\"i64 division overflow\");return a/b;}\n"
"static int64_t dxl_i64_mod(int64_t a,int64_t b){if(!b)dxl_panic(\"modulo by zero\");if(a==(-9223372036854775807LL-1)&&b==-1)return 0;return a%b;}\n"
"static int64_t dxl_i64_neg(int64_t a){if(a==(-9223372036854775807LL-1))dxl_panic(\"i64 negation overflow\");return -a;}\n"
"static int32_t dxl_i32_add(int32_t a,int32_t b){int32_t r;if(__builtin_add_overflow(a,b,&r))dxl_panic(\"i32 addition overflow\");return r;}\n"
"static int32_t dxl_i32_sub(int32_t a,int32_t b){int32_t r;if(__builtin_sub_overflow(a,b,&r))dxl_panic(\"i32 subtraction overflow\");return r;}\n"
"static int32_t dxl_i32_mul(int32_t a,int32_t b){int32_t r;if(__builtin_mul_overflow(a,b,&r))dxl_panic(\"i32 multiplication overflow\");return r;}\n"
"static int32_t dxl_i32_div(int32_t a,int32_t b){if(!b)dxl_panic(\"division by zero\");if(a==DXL_INT32_MIN&&b==-1)dxl_panic(\"i32 division overflow\");return a/b;}\n"
"static int32_t dxl_i32_mod(int32_t a,int32_t b){if(!b)dxl_panic(\"modulo by zero\");if(a==DXL_INT32_MIN&&b==-1)return 0;return a%b;}\n"
"static int32_t dxl_i32_neg(int32_t a){if(a==DXL_INT32_MIN)dxl_panic(\"i32 negation overflow\");return -a;}\n");
    sb_append(&c.out,
"static void dxl_print_i64(int64_t x){printf(\"%lld\\n\",(long long)x);}\n"
"static void dxl_print_i32(int32_t x){printf(\"%d\\n\",(int)x);}\n"
"static void dxl_print_bool(bool x){puts(x?\"true\":\"false\");}\n"
"static int64_t dxl_arg_count(void){return (int64_t)dxl_argc;}\n"
"static dxl_arr_hdr *dxl_arrays = 0;\n"
"static bool dxl_cleanup_registered = false;\n"
"static void dxl_cleanup_arrays(void){dxl_arr_hdr*h=dxl_arrays;while(h){dxl_arr_hdr*n=h->next;if(h->data)free(h->data);h->magic=0;free(h);h=n;}dxl_arrays=0;}\n"
"static dxl_array_i64 dxl_array_new(int64_t n,int64_t init){if(n<0||(uint64_t)n>DXL_SIZE_MAX/sizeof(int64_t))dxl_panic(\"invalid array length\");dxl_arr_hdr*h=malloc(sizeof(*h));if(!h)dxl_panic(\"out of memory\");h->data=n?malloc((size_t)n*sizeof(int64_t)):0;if(n&&!h->data)dxl_panic(\"out of memory\");h->magic=DXL_ARRAY_MAGIC;h->len=(size_t)n;h->freed=false;h->next=dxl_arrays;dxl_arrays=h;if(!dxl_cleanup_registered){if(atexit(dxl_cleanup_arrays)!=0)dxl_panic(\"atexit registration failed\");dxl_cleanup_registered=true;}for(size_t i=0;i<h->len;i++)h->data[i]=init;return(dxl_array_i64){h};}\n"
"static dxl_array_i64 dxl_read_arg_bytes(int64_t idx){if(idx<0||idx>=dxl_argc)dxl_panic(\"argument index out of bounds\");dxl_FILE*f=dxl_fopen(dxl_argv[idx],\"rb\");if(!f)dxl_panic(\"cannot open input file\");if(dxl_fseek(f,0,DXL_SEEK_END)!=0)dxl_panic(\"cannot seek input file\");long n=dxl_ftell(f);if(n<0)dxl_panic(\"cannot size input file\");if(n>67108864L)dxl_panic(\"input file exceeds 64 MiB safety limit\");if(dxl_fseek(f,0,DXL_SEEK_SET)!=0)dxl_panic(\"cannot rewind input file\");dxl_array_i64 a=dxl_array_new((int64_t)n,0);for(long i=0;i<n;i++){unsigned char ch=0;if(dxl_fread(&ch,1,1,f)!=1)dxl_panic(\"cannot read input file\");a.h->data[i]=(int64_t)ch;}if(dxl_fclose(f)!=0)dxl_panic(\"cannot close input file\");return a;}\n"
"static dxl_result_i64 dxl_write_arg_bytes(int64_t idx,dxl_slice_i64 s){if(idx<0||idx>=dxl_argc)return(dxl_result_i64){true,2,0};if(!s.owner||s.owner->magic!=DXL_ARRAY_MAGIC||s.owner->freed)return(dxl_result_i64){true,3,0};if(s.len>67108864u)return(dxl_result_i64){true,8,0};dxl_FILE*f=dxl_fopen(dxl_argv[idx],\"wb\");if(!f)return(dxl_result_i64){true,4,0};for(size_t i=0;i<s.len;i++){int64_t v=s.owner->data[s.start+i];if(v<0||v>255){dxl_fclose(f);return(dxl_result_i64){true,5,0};}unsigned char ch=(unsigned char)v;if(dxl_fwrite(&ch,1,1,f)!=1){dxl_fclose(f);return(dxl_result_i64){true,6,0};}}if(dxl_fclose(f)!=0)return(dxl_result_i64){true,7,0};return(dxl_result_i64){false,0,(int64_t)s.len};}\n"
"static void dxl_print_bytes(dxl_slice_i64 s){if(!s.owner||s.owner->magic!=DXL_ARRAY_MAGIC||s.owner->freed)dxl_panic(\"dangling slice\");for(size_t i=0;i<s.len;i++){int64_t v=s.owner->data[s.start+i];if(v<0||v>255)dxl_panic(\"byte outside 0..255\");putchar((int)v);}}\n"
);
    sb_append(&c.out,
"static dxl_arr_hdr*dxl_arr_check(dxl_array_i64 a){if(!a.h||a.h->magic!=DXL_ARRAY_MAGIC||a.h->freed)dxl_panic(\"invalid or freed array\");return a.h;}\n"
"static int64_t dxl_array_get(dxl_array_i64 a,int64_t i){dxl_arr_hdr*h=dxl_arr_check(a);if(i<0||(uint64_t)i>=h->len)dxl_panic(\"array index out of bounds\");return h->data[i];}\n"
"static void dxl_array_set(dxl_array_i64 a,int64_t i,int64_t v){dxl_arr_hdr*h=dxl_arr_check(a);if(i<0||(uint64_t)i>=h->len)dxl_panic(\"array index out of bounds\");h->data[i]=v;}\n"
"static int64_t dxl_len_array(dxl_array_i64 a){return (int64_t)dxl_arr_check(a)->len;}\n"
"static int64_t dxl_len_slice(dxl_slice_i64 s){if(!s.owner||s.owner->magic!=DXL_ARRAY_MAGIC||s.owner->freed)dxl_panic(\"dangling slice\");return (int64_t)s.len;}\n"
"#define dxl_len(x) _Generic((x), dxl_array_i64: dxl_len_array, dxl_slice_i64: dxl_len_slice)(x)\n"
"static dxl_slice_i64 dxl_slice(dxl_array_i64 a,int64_t start,int64_t len){dxl_arr_hdr*h=dxl_arr_check(a);if(start<0||len<0||(uint64_t)start+(uint64_t)len>h->len)dxl_panic(\"slice out of bounds\");return(dxl_slice_i64){h,(size_t)start,(size_t)len};}\n"
"static int64_t dxl_slice_get(dxl_slice_i64 s,int64_t i){if(!s.owner||s.owner->magic!=DXL_ARRAY_MAGIC||s.owner->freed)dxl_panic(\"dangling slice\");if(i<0||(uint64_t)i>=s.len)dxl_panic(\"slice index out of bounds\");return s.owner->data[s.start+(size_t)i];}\n"
"static void dxl_slice_set(dxl_slice_i64 s,int64_t i,int64_t v){if(!s.owner||s.owner->magic!=DXL_ARRAY_MAGIC||s.owner->freed)dxl_panic(\"dangling slice\");if(i<0||(uint64_t)i>=s.len)dxl_panic(\"slice index out of bounds\");s.owner->data[s.start+(size_t)i]=v;}\n"
"static void dxl_array_free(dxl_array_i64 a){dxl_arr_hdr*h=dxl_arr_check(a);free(h->data);h->data=0;h->freed=true;}\n"
"static dxl_result_i64 dxl_ok_i64(int64_t v){return(dxl_result_i64){false,0,v};}\n"
"static dxl_result_i64 dxl_err_i64(int32_t e){if(e==0)e=1;return(dxl_result_i64){true,e,0};}\n"
"static bool dxl_is_err(dxl_result_i64 r){return r.is_err;}\n"
"static int64_t dxl_unwrap_i64(dxl_result_i64 r){if(r.is_err)dxl_panic(\"unwrap of error result\");return r.value;}\n"
"static int32_t dxl_error_code(dxl_result_i64 r){return r.is_err?r.err:0;}\n\n");
    for(size_t i=0;i<p->enum_count;i++){
        EnumDecl*d=&p->enums[i];sb_printf(&c.out,"typedef enum %s { ",d->name);
        for(size_t j=0;j<d->count;j++){if(j)sb_append(&c.out,", ");sb_printf(&c.out,"%s_%s = %zu",d->name,d->variants[j],j);}
        sb_printf(&c.out," } %s;\n",d->name);
    }
    for(size_t i=0;i<p->struct_count;i++){
        StructDecl*d=&p->structs[i];sb_printf(&c.out,"typedef struct %s { ",d->name);
        for(size_t j=0;j<d->field_count;j++)sb_printf(&c.out,"%s %s; ",c_type(d->fields[j].type),d->fields[j].name);
        sb_printf(&c.out,"} %s;\n",d->name);
    }
    sb_putc(&c.out,'\n');
    for(size_t i=0;i<p->const_count;i++){
        Constant*k=&p->consts[i];
        if(k->evaluated)sb_printf(&c.out,"static const %s %s = (%s)%lld;\n",c_type(k->type),k->name,c_type(k->type),(long long)k->value);
    }
    sb_putc(&c.out,'\n');
    for(size_t i=0;i<p->fn_count;i++){
        Function*f=&p->funcs[i];if(tests&&!strcmp(f->name,"main"))continue;
        sb_printf(&c.out,"%s%s %s(",(!strcmp(f->name,"main")||f->is_export)?"":"static ",c_type(f->ret),c_fn_name(f->name));
        for(size_t j=0;j<f->param_count;j++){if(j)sb_append(&c.out,", ");sb_append(&c.out,c_type(f->params[j].type));}
        if(!f->param_count) {
            sb_append(&c.out,"void");
        }
        sb_append(&c.out,");\n");
    }
    sb_putc(&c.out,'\n');
    for(size_t i=0;i<p->fn_count;i++){
        Function*f=&p->funcs[i];
        if(tests&&!strcmp(f->name,"main"))continue;
        sb_printf(&c.out,"%s%s %s(",(!strcmp(f->name,"main")||f->is_export)?"":"static ",c_type(f->ret),c_fn_name(f->name));
        for(size_t j=0;j<f->param_count;j++){if(j)sb_append(&c.out,", ");sb_printf(&c.out,"%s %s",c_type(f->params[j].type),f->params[j].name);}
        if(!f->param_count)sb_append(&c.out,"void");
        if(f->is_extern){sb_append(&c.out,");\n");continue;}
        sb_append(&c.out,") ");cg_block(&c,f->body,0);sb_putc(&c.out,'\n');
    }
    if(!tests&&find_fn(p,"main"))sb_append(&c.out,"int main(int argc,char**argv){dxl_argc=argc;dxl_argv=argv;return (int)dxl_user_main();}\n");
    if(tests){
        for(size_t i=0;i<p->test_count;i++){
            c.in_test=true;sb_printf(&c.out,"static bool dxl_test_%zu(void) ",i);
            sb_append(&c.out,"{\n");
            for(size_t j=0;j<p->tests[i].body->as.block.count;j++)cg_stmt(&c,p->tests[i].body->as.block.items[j],1);
            sb_append(&c.out,"    return true;\n}\n");c.in_test=false;
        }
        sb_append(&c.out,"int main(int argc,char**argv){dxl_argc=argc;dxl_argv=argv;size_t pass=0;\n");
        for(size_t i=0;i<p->test_count;i++)sb_printf(&c.out,"if(dxl_test_%zu()){puts(\"PASS  %s\");pass++;}else{puts(\"FAIL  %s\");}\n",i,p->tests[i].name,p->tests[i].name);
        sb_printf(&c.out,"printf(\"RESULT: %%zu/%zu PASS\\n\",pass);return pass==%zu?0:1;}\n",p->test_count,p->test_count);
    }
    *out=c.out;
}

/* ---------- typed IR ---------- */
static void tir_expr(StrBuf*b,Expr*x){
    switch(x->kind){
        case EX_INT:sb_printf(b,"(i64 %lld)",(long long)x->as.int_value);break;
        case EX_BOOL:sb_printf(b,"(bool %s)",x->as.bool_value?"true":"false");break;
        case EX_NAME:sb_printf(b,"(name %s : %s)",x->as.name,type_name(x->type));break;
        case EX_BINARY:sb_printf(b,"(bin %d : %s ",(int)x->as.bin.op,type_name(x->type));tir_expr(b,x->as.bin.l);sb_putc(b,' ');tir_expr(b,x->as.bin.r);sb_putc(b,')');break;
        case EX_UNARY:sb_printf(b,"(un %d : %s ",(int)x->as.un.op,type_name(x->type));tir_expr(b,x->as.un.inner);sb_putc(b,')');break;
        case EX_CALL:sb_printf(b,"(call %s : %s",x->as.call.name,type_name(x->type));for(size_t i=0;i<x->as.call.argc;i++){sb_putc(b,' ');tir_expr(b,x->as.call.args[i]);}sb_putc(b,')');break;
        case EX_FIELD:sb_printf(b,"(field %s : %s ",x->as.field.name,type_name(x->type));tir_expr(b,x->as.field.base);sb_putc(b,')');break;
        case EX_INDEX:sb_printf(b,"(index : %s ",type_name(x->type));tir_expr(b,x->as.index.base);sb_putc(b,' ');tir_expr(b,x->as.index.index);sb_putc(b,')');break;
        case EX_STRUCT_INIT:sb_printf(b,"(struct-init %s",x->as.sinit.type_name);for(size_t i=0;i<x->as.sinit.count;i++){sb_printf(b," (%s ",x->as.sinit.fields[i].name);tir_expr(b,x->as.sinit.fields[i].value);sb_putc(b,')');}sb_putc(b,')');break;
        case EX_CAST:sb_printf(b,"(checked-cast %s ",type_name(x->as.cast.to));tir_expr(b,x->as.cast.value);sb_putc(b,')');break;
    }
}
static void emit_tir(Program*p,const char*target,StrBuf*out){
    StrBuf b;sb_init(&b);sb_printf(&b,"aegis-tir %s target %s\n",DXL_VERSION_STRING,target);
    for(size_t i=0;i<p->struct_count;i++){StructDecl*d=&p->structs[i];sb_printf(&b,"struct %s",d->name);for(size_t j=0;j<d->field_count;j++)sb_printf(&b," (%s %s)",d->fields[j].name,type_name(d->fields[j].type));sb_putc(&b,'\n');}
    for(size_t i=0;i<p->enum_count;i++){EnumDecl*d=&p->enums[i];sb_printf(&b,"enum %s",d->name);for(size_t j=0;j<d->count;j++)sb_printf(&b," %s=%zu",d->variants[j],j);sb_putc(&b,'\n');}
    for(size_t i=0;i<p->const_count;i++){Constant*k=&p->consts[i];sb_printf(&b,"const %s : %s = ",k->name,type_name(k->type));tir_expr(&b,k->expr);sb_putc(&b,'\n');}
    for(size_t i=0;i<p->fn_count;i++){Function*f=&p->funcs[i];sb_printf(&b,"fn %s (",f->name);for(size_t j=0;j<f->param_count;j++){if(j)sb_append(&b,", ");sb_printf(&b,"%s:%s",f->params[j].name,type_name(f->params[j].type));}sb_printf(&b,") -> %s%s\n",type_name(f->ret),f->is_comptime?" comptime":"");}
    for(size_t i=0;i<p->test_count;i++)sb_printf(&b,"test \"%s\"\n",p->tests[i].name);
    *out=b;
}
/* ---------- formatter ---------- */
static char*trim_line(char*s){while(*s&&isspace((unsigned char)*s)&&*s!='\n')s++;char*e=s+strlen(s);while(e>s&&isspace((unsigned char)e[-1]))e--;*e='\0';return s;}
static void format_source(const char*src,StrBuf*out){
    sb_init(out);char*copy=xstrdup(src),*save=NULL,*line=strtok_r(copy,"\n",&save);int ind=0;
    while(line){char*t=trim_line(line);if(*t){if(*t=='}'&&ind>0)ind--;for(int i=0;i<ind;i++)sb_append(out,"    ");sb_append(out,t);sb_putc(out,'\n');bool in_str=false,esc=false;for(char*q=t;*q;q++){if(in_str){if(esc)esc=false;else if(*q=='\\')esc=true;else if(*q=='"')in_str=false;}else if(*q=='"')in_str=true;else if(*q=='{')ind++;else if(*q=='}'&&q!=t&&ind>0)ind--;}}line=strtok_r(NULL,"\n",&save);
    }
    free(copy);
}

/* ---------- manifest, lock and cache ---------- */
typedef struct{char name[128],version[64],entry[PATH_MAX],target[128],output[PATH_MAX];}Manifest;
static void manifest_defaults(Manifest*m){memset(m,0,sizeof(*m));strcpy(m->name,"aegis-app");strcpy(m->version,"0.1.0");strcpy(m->entry,"src/main.dxl");strcpy(m->target,"native");strcpy(m->output,"build/aegis-app");}
static bool parse_manifest(const char*path,Manifest*m){
    manifest_defaults(m);size_t n=0;char*s=read_file(path,&n);if(!s)return false;char*save=NULL,*line=strtok_r(s,"\n",&save);
    while(line){char*t=trim_line(line);if(*t&&*t!='#'&&*t!='['){char*eq=strchr(t,'=');if(eq){*eq='\0';char*k=trim_line(t),*v=trim_line(eq+1);if(*v=='"'){v++;char*q=strrchr(v,'"');if(q)*q='\0';}if(!strcmp(k,"name"))snprintf(m->name,sizeof m->name,"%s",v);else if(!strcmp(k,"version"))snprintf(m->version,sizeof m->version,"%s",v);else if(!strcmp(k,"entry"))snprintf(m->entry,sizeof m->entry,"%s",v);else if(!strcmp(k,"target"))snprintf(m->target,sizeof m->target,"%s",v);else if(!strcmp(k,"output"))snprintf(m->output,sizeof m->output,"%s",v);}}line=strtok_r(NULL,"\n",&save);}
    free(s);return true;
}
static int module_cmp(const void*a,const void*b){const Module*x=a,*y=b;int h=strcmp(x->hash,y->hash);return h?h:strcmp(x->path,y->path);}
static const char*relative_to(const char*root,const char*path){size_t n=strlen(root);return !strncmp(root,path,n)&&path[n]=='/'?path+n+1:path;}
static void lock_text(const char*project,Program*p,StrBuf*b){
    char*root=canonical_path(project);qsort(p->mods,p->mod_count,sizeof(Module),module_cmp);sb_init(b);sb_printf(b,"# Aegis lock v1\ncompiler = \"%s\"\n",DXL_VERSION_STRING);
    for(size_t i=0;i<p->mod_count;i++)sb_printf(b,"module = \"%s\" sha256 = \"%s\"\n",relative_to(root,p->mods[i].path),p->mods[i].hash);
    free(root);
}
static bool write_lock(const char*project,Program*p){StrBuf b;lock_text(project,p,&b);char*path=path_join(project,"aegis.lock");bool ok=write_file(path,b.data,b.len);free(path);sb_free(&b);return ok;}
static bool verify_lock(const char*project,Program*p){
    char*path=path_join(project,"aegis.lock");size_t n=0;char*have=read_file(path,&n);if(!have){fprintf(stderr,"dxlc: missing aegis.lock; run 'dxlc project lock %s'\n",project);free(path);return false;}
    StrBuf want;lock_text(project,p,&want);bool ok=n==want.len&&!memcmp(have,want.data,n);if(!ok)fprintf(stderr,"dxlc: aegis.lock is stale; run 'dxlc project lock %s'\n",project);free(have);free(path);sb_free(&want);return ok;
}
static void program_fingerprint(Program*p,const char*target,bool tests,char out[65]){
    Sha256 s;sha_init(&s);sha_update(&s,DXL_VERSION_STRING,strlen(DXL_VERSION_STRING));sha_update(&s,target,strlen(target));sha_update(&s,&tests,sizeof tests);qsort(p->mods,p->mod_count,sizeof(Module),module_cmp);
    for(size_t i=0;i<p->mod_count;i++){sha_update(&s,p->mods[i].hash,64);sha_update(&s,&p->mods[i].len,sizeof p->mods[i].len);}uint8_t d[32];sha_final(&s,d);static const char*h="0123456789abcdef";for(int i=0;i<32;i++){out[i*2]=h[d[i]>>4];out[i*2+1]=h[d[i]&15];}out[64]=0;
}

/* ---------- driver ---------- */
static const char*target_triple(const char*n){if(!n||!strcmp(n,"native")||!strcmp(n,"x86_64-linux"))return"x86_64-unknown-linux-gnu";if(!strcmp(n,"aarch64-linux"))return"aarch64-unknown-linux-gnu";if(!strcmp(n,"x86_64-windows"))return"x86_64-w64-windows-gnu";if(!strcmp(n,"wasm32"))return"wasm32-unknown-unknown";return n;}
static const char*arg_value(int ac,char**av,const char*k,const char*d){for(int i=0;i+1<ac;i++)if(!strcmp(av[i],k))return av[i+1];return d;}
static bool has_arg(int ac,char**av,const char*k){for(int i=0;i<ac;i++)if(!strcmp(av[i],k))return true;return false;}
static bool compile_front(const char*entry,const char*target,Program*p){if(!load_program(entry,p))return false;return sema_program(p,target);}
static bool ensure_parent(const char*path){char*d=path_dirname(path);bool ok=mkdir_p(d);free(d);return ok;}
static int compile_c_file(const char*cpath,const char*out,const char*target,const char*emit){
    if(!ensure_parent(out)) return 1;
    char targ[256];
    snprintf(targ,sizeof targ,"--target=%s",target);
    char*cc=(char*)(getenv("DXLC_CLANG")?getenv("DXLC_CLANG"):"clang");
    char*args[28];
    int n=0;
    args[n++]=cc;args[n++]=targ;args[n++]=(char*)"-std=c11";args[n++]=(char*)"-O2";args[n++]=(char*)"-Wall";args[n++]=(char*)"-Wextra";args[n++]=(char*)"-Wpedantic";args[n++]=(char*)"-Werror";args[n++]=(char*)"-Wno-builtin-requires-header";args[n++]=(char*)"-Wno-unused-function";args[n++]=(char*)"-Wno-unused-const-variable";args[n++]=(char*)"-ffile-prefix-map=/tmp=/src";args[n++]=(char*)"-fdebug-prefix-map=/tmp=/src";args[n++]=(char*)"-fmacro-prefix-map=/tmp=/src";args[n++]=(char*)"-Xclang";args[n++]=(char*)"-main-file-name";args[n++]=(char*)"-Xclang";args[n++]=(char*)"generated.dxl.c";args[n++]=(char*)"-fno-ident";args[n++]=(char*)"-x";args[n++]=(char*)"c";if(!strcmp(emit,"obj"))args[n++]=(char*)"-c";args[n++]=(char*)"-";args[n++]=(char*)"-o";args[n++]=(char*)out;args[n]=NULL;size_t src_len=0;char*src=read_file(cpath,&src_len);if(!src)return 1;int rc=run_cmd_input(args,src,src_len);free(src);return rc;
}
static int link_object(const char*obj,const char*out,const char*target){
    if(!ensure_parent(out)) return 1;
    char targ[256];
    snprintf(targ,sizeof targ,"--target=%s",target);
    char*cc=(char*)(getenv("DXLC_CLANG")?getenv("DXLC_CLANG"):"clang");
    char*args[]={cc,targ,(char*)obj,(char*)"-o",(char*)out,NULL};
    return run_cmd(args);
}
static int build_entry(const char*entry,const char*out,const char*tname,const char*emit,bool tests,bool use_cache,const char*cache_root){
    const char*target=target_triple(tname);Program p;if(!compile_front(entry,target,&p))return 1;StrBuf c;emit_c(&p,tests,&c);
    if(!strcmp(emit,"c")){int rc=write_file(out,c.data,c.len)?0:1;sb_free(&c);return rc;}
    if(!strcmp(emit,"tir")){StrBuf t;emit_tir(&p,target,&t);int rc=write_file(out,t.data,t.len)?0:1;sb_free(&t);sb_free(&c);return rc;}
    char hash[65];program_fingerprint(&p,target,tests,hash);
    char tmp[]="/tmp/dxlc-c-XXXXXX";int fd=mkstemp(tmp);if(fd<0){perror("mkstemp");sb_free(&c);return 1;}FILE*f=fdopen(fd,"wb");if(!f){close(fd);unlink(tmp);sb_free(&c);return 1;}fwrite(c.data,1,c.len,f);fclose(f);
    int rc=0;
    if(use_cache){
        char*cache=path_join(cache_root?cache_root:".",DXL_CACHE_DIR);mkdir_p(cache);StrBuf b;sb_init(&b);sb_printf(&b,"%s/%s.o",cache,hash);char*obj=xstrdup(b.data);sb_free(&b);
        if(path_exists(obj))printf("cache hit %s\n",hash);else{rc=compile_c_file(tmp,obj,target,"obj");if(!rc)printf("cache store %s\n",hash);}
        if(!rc){if(!strcmp(emit,"obj"))rc=copy_file(obj,out)?0:1;else rc=link_object(obj,out,target);}free(cache);free(obj);
    }else rc=compile_c_file(tmp,out,target,emit);
    unlink(tmp);sb_free(&c);return rc;
}
static int command_fmt(const char*path,bool check){size_t n=0;char*s=read_file(path,&n);if(!s)return 1;StrBuf b;format_source(s,&b);int rc=0;if(check){if(n!=b.len||memcmp(s,b.data,b.len)){fprintf(stderr,"%s is not formatted\n",path);rc=1;}}else if(!write_file(path,b.data,b.len))rc=1;free(s);sb_free(&b);return rc;}
static int project_cmd(const char*cmd,const char*dir,int ac,char**av){
    char*mp=path_join(dir,"aegis.pkg");Manifest m;if(!parse_manifest(mp,&m)){free(mp);return 1;}free(mp);char*entry=path_join(dir,m.entry),*out=path_join(dir,m.output);const char*tname=arg_value(ac,av,"--target",m.target);
    Program p;if(!compile_front(entry,target_triple(tname),&p)){free(entry);free(out);return 1;}
    if(!strcmp(cmd,"lock")){bool ok=write_lock(dir,&p);free(entry);free(out);return ok?0:1;}
    if(!verify_lock(dir,&p)){free(entry);free(out);return 1;}
    if(!strcmp(cmd,"check")){printf("project %s %s: OK (%zu modules)\n",m.name,m.version,p.mod_count);free(entry);free(out);return 0;}
    if(!strcmp(cmd,"test")){char*to=path_join(dir,"build/tests");int rc=build_entry(entry,to,tname,"exe",true,true,dir);if(!rc){char*args[]={to,NULL};rc=run_cmd(args);}free(to);free(entry);free(out);return rc;}
    if(!strcmp(cmd,"build")){const char*emit=arg_value(ac,av,"--emit","exe");int rc=build_entry(entry,out,tname,emit,false,true,dir);if(!rc)printf("built %s\n",out);free(entry);free(out);return rc;}
    free(entry);free(out);fprintf(stderr,"dxlc: unknown project command %s\n",cmd);return 1;
}
static void usage(void){puts("DXL compiler dxlc " DXL_VERSION_STRING "\n\nCommands:\n  dxlc check FILE [--target T]\n  dxlc build FILE -o OUT [--target T] [--emit exe|obj|c|tir]\n  dxlc run FILE\n  dxlc test FILE\n  dxlc emit-c FILE -o OUT\n  dxlc emit-tir FILE -o OUT [--target T]\n  dxlc fmt FILE [--check]\n  dxlc project build|check|test|lock DIR [--target T]\n  dxlc targets\n  dxlc version\n\nTargets: native, x86_64-linux, aarch64-linux, x86_64-windows, wasm32");}
int main(int ac,char**av){
    if(ac<2){usage();return 1;}const char*cmd=av[1];
    if(!strcmp(cmd,"version")){puts("dxlc " DXL_VERSION_STRING);return 0;}
    if(!strcmp(cmd,"targets")){puts("native -> x86_64-unknown-linux-gnu\nx86_64-linux -> x86_64-unknown-linux-gnu\naarch64-linux -> aarch64-unknown-linux-gnu\nx86_64-windows -> x86_64-w64-windows-gnu\nwasm32 -> wasm32-unknown-unknown");return 0;}
    if(!strcmp(cmd,"project")){if(ac<4){usage();return 1;}return project_cmd(av[2],av[3],ac,av);}
    if(ac<3){usage();return 1;}const char*input=av[2],*tname=arg_value(ac,av,"--target","native"),*target=target_triple(tname);
    if(!strcmp(cmd,"fmt"))return command_fmt(input,has_arg(ac,av,"--check"));
    if(!strcmp(cmd,"check")){Program p;if(!compile_front(input,target,&p))return 1;printf("checked %s for %s: OK (%zu modules, %zu tests)\n",input,target,p.mod_count,p.test_count);return 0;}
    if(!strcmp(cmd,"emit-c")||!strcmp(cmd,"emit-tir")||!strcmp(cmd,"build")){const char*out=arg_value(ac,av,"-o",NULL);if(!out){fprintf(stderr,"dxlc: -o is required\n");return 1;}const char*emit=!strcmp(cmd,"emit-c")?"c":!strcmp(cmd,"emit-tir")?"tir":arg_value(ac,av,"--emit","exe");return build_entry(input,out,tname,emit,false,false,NULL);}
    if(!strcmp(cmd,"run")){char tmp[]="/tmp/dxl-run-XXXXXX";int fd=mkstemp(tmp);if(fd<0)return 1;close(fd);unlink(tmp);int rc=build_entry(input,tmp,tname,"exe",false,false,NULL);if(!rc){char*args[]={tmp,NULL};rc=run_cmd(args);}unlink(tmp);return rc;}
    if(!strcmp(cmd,"test")){char tmp[]="/tmp/dxl-test-XXXXXX";int fd=mkstemp(tmp);if(fd<0)return 1;close(fd);unlink(tmp);int rc=build_entry(input,tmp,tname,"exe",true,false,NULL);if(!rc){char*args[]={tmp,NULL};rc=run_cmd(args);}unlink(tmp);return rc;}
    fprintf(stderr,"dxlc: unknown command '%s'\n",cmd);usage();return 1;
}
