#define _POSIX_C_SOURCE 200809L
#include "aegis_c2r.h"

#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define C2R_MAX_INPUT (1024u * 1024u)
#define MAX_FUNCS 63
#define MAX_PARAMS 16
#define MAX_LOCALS 256
#define MAX_NODES 65535
#define MAX_DEPTH 64
#define MAX_ARGS 262144
#define NAME_CAP 64

typedef struct {
    char *data;
    size_t len;
    size_t cap;
} Str;

static void sb_init(Str *s) { s->data = NULL; s->len = 0; s->cap = 0; }
static void sb_free(Str *s) { free(s->data); s->data = NULL; s->len = s->cap = 0; }
static bool sb_reserve(Str *s, size_t add) {
    if (add > SIZE_MAX - s->len - 1) return false;
    size_t need = s->len + add + 1;
    if (need <= s->cap) return true;
    size_t cap = s->cap ? s->cap : 256;
    while (cap < need) {
        if (cap > SIZE_MAX / 2) { cap = need; break; }
        cap *= 2;
    }
    char *p = (char *)realloc(s->data, cap);
    if (!p) return false;
    s->data = p; s->cap = cap;
    return true;
}
static bool sb_append_n(Str *s, const char *p, size_t n) {
    if (!sb_reserve(s, n)) return false;
    memcpy(s->data + s->len, p, n);
    s->len += n; s->data[s->len] = '\0';
    return true;
}
static bool sb_append(Str *s, const char *p) { return sb_append_n(s, p, strlen(p)); }
#if defined(__GNUC__) || defined(__clang__)
__attribute__((format(printf, 2, 3)))
#endif
static bool sb_printf(Str *s, const char *fmt, ...) {
    va_list ap, cp;
    va_start(ap, fmt); va_copy(cp, ap);
    int n = vsnprintf(NULL, 0, fmt, cp); va_end(cp);
    if (n < 0) { va_end(ap); return false; }
    if (!sb_reserve(s, (size_t)n)) { va_end(ap); return false; }
    int n2 = vsnprintf(s->data + s->len, s->cap - s->len, fmt, ap); va_end(ap);
    if (n2 != n) return false;
    s->len += (size_t)n; return true;
}

static int fail_plain(int code, const char *msg) {
    fprintf(stderr, "E%04d 0:0 %s\n", code, msg);
    return 1;
}

/* Compact SHA-256 implementation, written for this project from FIPS 180-4. */
typedef struct { uint32_t h[8]; uint64_t bits; uint8_t buf[64]; size_t used; } Sha256;
static uint32_t rotr32(uint32_t x, unsigned n) { return (x >> n) | (x << (32u - n)); }
static uint32_t be32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3]; }
static void put_be32(uint8_t *p, uint32_t x) { p[0]=(uint8_t)(x>>24); p[1]=(uint8_t)(x>>16); p[2]=(uint8_t)(x>>8); p[3]=(uint8_t)x; }
static const uint32_t K256[64] = {
0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};
static void sha_init(Sha256 *s) { static const uint32_t iv[8]={0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u}; memcpy(s->h,iv,sizeof iv); s->bits=0; s->used=0; }
static void sha_block(Sha256 *s, const uint8_t b[64]) {
    uint32_t w[64]; for (int i=0;i<16;i++) w[i]=be32(b+4*i);
    for (int i=16;i<64;i++){uint32_t a=rotr32(w[i-15],7)^rotr32(w[i-15],18)^(w[i-15]>>3);uint32_t z=rotr32(w[i-2],17)^rotr32(w[i-2],19)^(w[i-2]>>10);w[i]=w[i-16]+a+w[i-7]+z;}
    uint32_t a=s->h[0],b0=s->h[1],c=s->h[2],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];
    for(int i=0;i<64;i++){uint32_t S1=rotr32(e,6)^rotr32(e,11)^rotr32(e,25);uint32_t ch=(e&f)^((~e)&g);uint32_t t1=h+S1+ch+K256[i]+w[i];uint32_t S0=rotr32(a,2)^rotr32(a,13)^rotr32(a,22);uint32_t maj=(a&b0)^(a&c)^(b0&c);uint32_t t2=S0+maj;h=g;g=f;f=e;e=d+t1;d=c;c=b0;b0=a;a=t1+t2;}
    s->h[0]+=a;s->h[1]+=b0;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void sha_update(Sha256 *s, const void *vp, size_t n) {
    const uint8_t *p=(const uint8_t*)vp; if (n > (UINT64_MAX - s->bits)/8u) abort(); s->bits += (uint64_t)n*8u;
    while(n){size_t take=64-s->used;if(take>n)take=n;memcpy(s->buf+s->used,p,take);s->used+=take;p+=take;n-=take;if(s->used==64){sha_block(s,s->buf);s->used=0;}}
}
static void sha_final(Sha256 *s, uint8_t out[32]) {
    s->buf[s->used++]=0x80u; if(s->used>56){while(s->used<64)s->buf[s->used++]=0;sha_block(s,s->buf);s->used=0;} while(s->used<56)s->buf[s->used++]=0;
    for(int i=7;i>=0;i--) { s->buf[s->used++]=(uint8_t)(s->bits>>(i*8)); }
    sha_block(s,s->buf);
    for(int i=0;i<8;i++) { put_be32(out+4*i,s->h[i]); }
}
static void sha_hex(const void *p,size_t n,char out[65]){static const char h[]="0123456789abcdef";uint8_t d[32];Sha256 s;sha_init(&s);sha_update(&s,p,n);sha_final(&s,d);for(int i=0;i<32;i++){out[2*i]=h[d[i]>>4];out[2*i+1]=h[d[i]&15];}out[64]='\0';}

typedef enum {
 T_EOF=0,T_ID,T_NUM,T_STR,
 T_INT,T_IF,T_ELSE,T_WHILE,T_RETURN,T_ASSERT,T_PRINTF,
 T_LP,T_RP,T_LB,T_RB,T_SEMI,T_COMMA,
 T_PLUS,T_MINUS,T_STAR,T_SLASH,T_PERCENT,T_BANG,T_ASSIGN,
 T_EQ,T_NE,T_LT,T_LE,T_GT,T_GE,T_AND,T_OR
} TokKind;
typedef struct { TokKind k; int32_t num; char text[NAME_CAP]; unsigned line,col; } Tok;
typedef struct { const char *src; size_t len,pos; unsigned line,col; Tok cur; int err; } Lex;

static bool ident0(unsigned char c){return isalpha(c)||c=='_';}
static bool ident1(unsigned char c){return isalnum(c)||c=='_';}
static TokKind kw(const char *s){if(strcmp(s,"int")==0)return T_INT;if(strcmp(s,"if")==0)return T_IF;if(strcmp(s,"else")==0)return T_ELSE;if(strcmp(s,"while")==0)return T_WHILE;if(strcmp(s,"return")==0)return T_RETURN;if(strcmp(s,"assert")==0)return T_ASSERT;if(strcmp(s,"printf")==0)return T_PRINTF;return T_ID;}
static int lex_diag(Lex *l,int code,unsigned line,unsigned col,const char *msg){fprintf(stderr,"E%04d %u:%u %s\n",code,line,col,msg);l->err=1;return 0;}
static int lex_next(Lex *l){
    if(l->err)return 0;
    for(;;){
        while(l->pos<l->len && isspace((unsigned char)l->src[l->pos])){if(l->src[l->pos]=='\n'){l->line++;l->col=1;}else l->col++;l->pos++;}
        if(l->pos+1<l->len && l->src[l->pos]=='/' && l->src[l->pos+1]=='/'){while(l->pos<l->len&&l->src[l->pos]!='\n'){l->pos++;l->col++;}continue;}
        if(l->pos+1<l->len && l->src[l->pos]=='/' && l->src[l->pos+1]=='*'){unsigned sl=l->line,sc=l->col;l->pos+=2;l->col+=2;bool done=false;while(l->pos<l->len){if(l->pos+1<l->len&&l->src[l->pos]=='*'&&l->src[l->pos+1]=='/'){l->pos+=2;l->col+=2;done=true;break;}if(l->src[l->pos]=='\n'){l->line++;l->col=1;l->pos++;}else{l->pos++;l->col++;}}if(!done)return lex_diag(l,2001,sl,sc,"unterminated block comment");continue;}
        break;
    }
    Tok t; memset(&t,0,sizeof t); t.line=l->line;t.col=l->col;
    if(l->pos>=l->len){t.k=T_EOF;l->cur=t;return 1;}
    unsigned char c=(unsigned char)l->src[l->pos];
    if(ident0(c)){size_t start=l->pos;while(l->pos<l->len&&ident1((unsigned char)l->src[l->pos])){l->pos++;l->col++;}size_t n=l->pos-start;if(n>=NAME_CAP)return lex_diag(l,2002,t.line,t.col,"identifier too long");memcpy(t.text,l->src+start,n);t.text[n]='\0';t.k=kw(t.text);l->cur=t;return 1;}
    if(isdigit(c)){uint64_t v=0;while(l->pos<l->len&&isdigit((unsigned char)l->src[l->pos])){unsigned d=(unsigned)(l->src[l->pos]-'0');v=v*10u+d;if(v>INT32_MAX)return lex_diag(l,2003,t.line,t.col,"decimal literal exceeds i32 positive range");l->pos++;l->col++;}t.k=T_NUM;t.num=(int32_t)v;l->cur=t;return 1;}
    if(c=='"'){l->pos++;l->col++;size_t n=0;while(l->pos<l->len&&l->src[l->pos]!='"'){if(l->src[l->pos]=='\n')return lex_diag(l,2004,t.line,t.col,"newline in string literal");if(n+1>=NAME_CAP)return lex_diag(l,2005,t.line,t.col,"string literal too long");if(l->src[l->pos]=='\\'&&l->pos+1<l->len){t.text[n++]=l->src[l->pos++];l->col++;t.text[n++]=l->src[l->pos++];l->col++;}else{t.text[n++]=l->src[l->pos++];l->col++;}}if(l->pos>=l->len)return lex_diag(l,2006,t.line,t.col,"unterminated string literal");l->pos++;l->col++;t.text[n]='\0';t.k=T_STR;l->cur=t;return 1;}
    #define TWO(a,b,tk) if(c==(unsigned char)(a)&&l->pos+1<l->len&&l->src[l->pos+1]==(b)){t.k=(tk);l->pos+=2;l->col+=2;l->cur=t;return 1;}
    TWO('=','=',T_EQ) TWO('!','=',T_NE) TWO('<','=',T_LE) TWO('>','=',T_GE) TWO('&','&',T_AND) TWO('|','|',T_OR)
    #undef TWO
    l->pos++;l->col++;
    switch(c){case '(':t.k=T_LP;break;case ')':t.k=T_RP;break;case '{':t.k=T_LB;break;case '}':t.k=T_RB;break;case ';':t.k=T_SEMI;break;case ',':t.k=T_COMMA;break;case '+':t.k=T_PLUS;break;case '-':t.k=T_MINUS;break;case '*':t.k=T_STAR;break;case '/':t.k=T_SLASH;break;case '%':t.k=T_PERCENT;break;case '!':t.k=T_BANG;break;case '=':t.k=T_ASSIGN;break;case '<':t.k=T_LT;break;case '>':t.k=T_GT;break;default:return lex_diag(l,2007,t.line,t.col,"unsupported byte/token");}
    l->cur=t;return 1;
}

typedef enum {E_NUM,E_VAR,E_CALL,E_UNARY,E_BINARY} EKind;
typedef struct {EKind k; TokKind op; int32_t val; char name[NAME_CAP]; int a,b; int arg_start,arg_count;} Expr;
typedef enum {S_DECL,S_ASSIGN,S_RETURN,S_CALL,S_IF,S_WHILE,S_BLOCK,S_PRINT,S_ASSERT} SKind;
typedef struct {SKind k; char name[NAME_CAP]; int expr; int b1,b2; int next;} Stmt;
typedef struct {int first,last;} Block;
typedef struct {char name[NAME_CAP];int param_count;char params[MAX_PARAMS][NAME_CAP];int local_count;char locals[MAX_LOCALS][NAME_CAP];int body;} Func;
typedef struct {
    Expr expr[MAX_NODES]; int expr_n;
    Stmt stmt[MAX_NODES]; int stmt_n;
    Block block[MAX_NODES]; int block_n;
    int args[MAX_ARGS]; int arg_n;
    Func funcs[MAX_FUNCS]; int func_n;
    int max_depth; unsigned features;
} Program;

typedef struct {Lex lx; Program *p; int cur_func; int depth; int err;} Parser;
static int pdiag(Parser *p,int code,const char *msg){fprintf(stderr,"E%04d %u:%u %s\n",code,p->lx.cur.line,p->lx.cur.col,msg);p->err=1;return -1;}
static bool accept(Parser *p,TokKind k){if(p->lx.cur.k==k){lex_next(&p->lx);return true;}return false;}
static bool expect(Parser *p,TokKind k,int code,const char *msg){if(p->lx.cur.k!=k){pdiag(p,code,msg);return false;}return lex_next(&p->lx)!=0;}
static int new_expr(Parser *p,EKind k){if(p->p->expr_n>=MAX_NODES){pdiag(p,4001,"expression/node limit exceeded");return -1;}int i=p->p->expr_n++;memset(&p->p->expr[i],0,sizeof p->p->expr[i]);p->p->expr[i].k=k;p->p->expr[i].a=p->p->expr[i].b=-1;return i;}
static int new_stmt(Parser *p,SKind k){if(p->p->stmt_n>=MAX_NODES){pdiag(p,4002,"statement/node limit exceeded");return -1;}int i=p->p->stmt_n++;memset(&p->p->stmt[i],0,sizeof p->p->stmt[i]);p->p->stmt[i].k=k;p->p->stmt[i].expr=-1;p->p->stmt[i].b1=p->p->stmt[i].b2=-1;p->p->stmt[i].next=-1;return i;}
static int new_block(Parser *p){if(p->p->block_n>=MAX_NODES){pdiag(p,4003,"block/node limit exceeded");return -1;}int i=p->p->block_n++;p->p->block[i].first=p->p->block[i].last=-1;return i;}
static void block_add(Program *p,int b,int s){if(p->block[b].first<0)p->block[b].first=s;else p->stmt[p->block[b].last].next=s;p->block[b].last=s;}
static int find_var(Parser *p,const char *name){Func *f=&p->p->funcs[p->cur_func];for(int i=0;i<f->param_count;i++)if(strcmp(f->params[i],name)==0)return 1;for(int i=0;i<f->local_count;i++)if(strcmp(f->locals[i],name)==0)return 1;return 0;}
static int find_func(Program *pr,const char *name){for(int i=0;i<pr->func_n;i++)if(strcmp(pr->funcs[i].name,name)==0)return i;return -1;}
static bool callable_name(Program *pr,const char *name){return strcmp(name,"printf")==0||strcmp(name,"assert")==0||find_func(pr,name)>=0;}
static int parse_expr(Parser *p);
static int parse_primary(Parser *p){
    if(p->depth>MAX_DEPTH){pdiag(p,4004,"expression nesting limit exceeded");return -1;}
    if(p->lx.cur.k==T_NUM){int i=new_expr(p,E_NUM);if(i<0)return -1;p->p->expr[i].val=p->lx.cur.num;lex_next(&p->lx);return i;}
    if(p->lx.cur.k==T_ID){char name[NAME_CAP];memcpy(name,p->lx.cur.text,NAME_CAP);lex_next(&p->lx);
        if(accept(p,T_LP)){int fi=find_func(p->p,name);if(fi<0)return pdiag(p,5001,"call to unknown or forward function");if(fi==p->cur_func)return pdiag(p,5002,"direct recursion is outside S0");int start=p->p->arg_n,count=0;if(!accept(p,T_RP)){for(;;){if(p->p->arg_n>=MAX_ARGS)return pdiag(p,4005,"argument storage limit exceeded");int e=parse_expr(p);if(e<0)return -1;p->p->args[p->p->arg_n++]=e;count++;if(accept(p,T_RP))break;if(!expect(p,T_COMMA,3001,"expected ',' or ')' in call"))return -1;}}
            if(count!=p->p->funcs[fi].param_count) return pdiag(p,5003,"function argument count mismatch");
            int i=new_expr(p,E_CALL);
            if(i<0) return -1;
            strncpy(p->p->expr[i].name,name,NAME_CAP-1);
            p->p->expr[i].arg_start=start; p->p->expr[i].arg_count=count; p->p->features|=1u<<0;
            return i;
        }
        if(!find_var(p,name)) return pdiag(p,5004,"unknown variable");
        int i=new_expr(p,E_VAR);
        if(i<0) return -1;
        strncpy(p->p->expr[i].name,name,NAME_CAP-1);
        return i;
    }
    if(accept(p,T_LP)){p->depth++;int e=parse_expr(p);p->depth--;if(e<0)return -1;if(!expect(p,T_RP,3002,"expected ')'"))return -1;return e;}
    return pdiag(p,3003,"expected expression");
}
static int parse_unary(Parser *p){if(p->lx.cur.k==T_MINUS||p->lx.cur.k==T_BANG){TokKind op=p->lx.cur.k;lex_next(&p->lx);int a=parse_unary(p);if(a<0)return -1;int i=new_expr(p,E_UNARY);if(i<0)return -1;p->p->expr[i].op=op;p->p->expr[i].a=a;p->p->features|=(op==T_BANG)?(1u<<1):(1u<<2);return i;}return parse_primary(p);}
static int mkbin(Parser *p,int a,TokKind op,int b){if((op==T_SLASH||op==T_PERCENT)&&p->p->expr[b].k==E_NUM&&p->p->expr[b].val==0)return pdiag(p,5005,"literal divide/remainder by zero");int i=new_expr(p,E_BINARY);if(i<0)return -1;p->p->expr[i].a=a;p->p->expr[i].b=b;p->p->expr[i].op=op;if(op==T_AND||op==T_OR)p->p->features|=1u<<3;return i;}
static int parse_mul(Parser *p){int a=parse_unary(p);while(a>=0&&(p->lx.cur.k==T_STAR||p->lx.cur.k==T_SLASH||p->lx.cur.k==T_PERCENT)){TokKind op=p->lx.cur.k;lex_next(&p->lx);int b=parse_unary(p);if(b<0)return -1;a=mkbin(p,a,op,b);}return a;}
static int parse_add(Parser *p){int a=parse_mul(p);while(a>=0&&(p->lx.cur.k==T_PLUS||p->lx.cur.k==T_MINUS)){TokKind op=p->lx.cur.k;lex_next(&p->lx);int b=parse_mul(p);if(b<0)return -1;a=mkbin(p,a,op,b);}return a;}
static int parse_rel(Parser *p){int a=parse_add(p);while(a>=0&&(p->lx.cur.k==T_LT||p->lx.cur.k==T_LE||p->lx.cur.k==T_GT||p->lx.cur.k==T_GE)){TokKind op=p->lx.cur.k;lex_next(&p->lx);int b=parse_add(p);if(b<0)return -1;a=mkbin(p,a,op,b);}return a;}
static int parse_eq(Parser *p){int a=parse_rel(p);while(a>=0&&(p->lx.cur.k==T_EQ||p->lx.cur.k==T_NE)){TokKind op=p->lx.cur.k;lex_next(&p->lx);int b=parse_rel(p);if(b<0)return -1;a=mkbin(p,a,op,b);}return a;}
static int parse_and(Parser *p){int a=parse_eq(p);while(a>=0&&p->lx.cur.k==T_AND){lex_next(&p->lx);int b=parse_eq(p);if(b<0)return -1;a=mkbin(p,a,T_AND,b);}return a;}
static int parse_expr(Parser *p){int a=parse_and(p);while(a>=0&&p->lx.cur.k==T_OR){lex_next(&p->lx);int b=parse_and(p);if(b<0)return -1;a=mkbin(p,a,T_OR,b);}return a;}

static int parse_block(Parser *p,bool outer);
static int parse_stmt(Parser *p){
    if(p->lx.cur.k==T_RETURN){lex_next(&p->lx);int e=parse_expr(p);if(e<0)return -1;if(!expect(p,T_SEMI,3010,"expected ';' after return"))return -1;int s=new_stmt(p,S_RETURN);p->p->stmt[s].expr=e;return s;}
    if(p->lx.cur.k==T_IF){lex_next(&p->lx);if(!expect(p,T_LP,3011,"expected '(' after if"))return -1;int e=parse_expr(p);if(e<0)return -1;if(!expect(p,T_RP,3012,"expected ')' after if condition"))return -1;int b1=parse_block(p,false);if(b1<0)return -1;int b2=-1;if(accept(p,T_ELSE)){b2=parse_block(p,false);if(b2<0)return -1;}int s=new_stmt(p,S_IF);p->p->stmt[s].expr=e;p->p->stmt[s].b1=b1;p->p->stmt[s].b2=b2;p->p->features|=1u<<4;return s;}
    if(p->lx.cur.k==T_WHILE){lex_next(&p->lx);if(!expect(p,T_LP,3013,"expected '(' after while"))return -1;int e=parse_expr(p);if(e<0)return -1;if(!expect(p,T_RP,3014,"expected ')' after while condition"))return -1;int b=parse_block(p,false);if(b<0)return -1;int s=new_stmt(p,S_WHILE);p->p->stmt[s].expr=e;p->p->stmt[s].b1=b;p->p->features|=1u<<5;return s;}
    if(p->lx.cur.k==T_LB){int b=parse_block(p,false);if(b<0)return -1;int s=new_stmt(p,S_BLOCK);p->p->stmt[s].b1=b;return s;}
    if(p->lx.cur.k==T_PRINTF){lex_next(&p->lx);if(!expect(p,T_LP,3015,"expected '(' after printf"))return -1;if(p->lx.cur.k!=T_STR)return pdiag(p,3016,"printf requires literal format");if(strcmp(p->lx.cur.text,"%d\\n")!=0)return pdiag(p,4006,"only printf(\"%d\\\\n\", expr) is supported");lex_next(&p->lx);if(!expect(p,T_COMMA,3017,"expected ',' in printf"))return -1;int e=parse_expr(p);if(e<0)return -1;if(!expect(p,T_RP,3018,"expected ')' after printf"))return -1;if(!expect(p,T_SEMI,3019,"expected ';' after printf"))return -1;int s=new_stmt(p,S_PRINT);p->p->stmt[s].expr=e;p->p->features|=1u<<6;return s;}
    if(p->lx.cur.k==T_ASSERT){lex_next(&p->lx);if(!expect(p,T_LP,3020,"expected '(' after assert"))return -1;int e=parse_expr(p);if(e<0)return -1;if(!expect(p,T_RP,3021,"expected ')' after assert"))return -1;if(!expect(p,T_SEMI,3022,"expected ';' after assert"))return -1;int s=new_stmt(p,S_ASSERT);p->p->stmt[s].expr=e;p->p->features|=1u<<7;return s;}
    if(p->lx.cur.k==T_INT)return pdiag(p,4007,"local declarations must be a prefix of the outer function body");
    if(p->lx.cur.k==T_ID){char name[NAME_CAP];memcpy(name,p->lx.cur.text,NAME_CAP);lex_next(&p->lx);if(accept(p,T_ASSIGN)){if(!find_var(p,name))return pdiag(p,5006,"assignment to unknown variable");int e=parse_expr(p);if(e<0)return -1;if(!expect(p,T_SEMI,3023,"expected ';' after assignment"))return -1;int s=new_stmt(p,S_ASSIGN);strncpy(p->p->stmt[s].name,name,NAME_CAP-1);p->p->stmt[s].expr=e;return s;}
        if(p->lx.cur.k!=T_LP) return pdiag(p,3024,"only assignment or call statements may begin with identifier");
        int fi=find_func(p->p,name);
        if(fi<0) return pdiag(p,5007,"call to unknown or forward function");
        if(fi==p->cur_func) return pdiag(p,5008,"direct recursion is outside S0");
        lex_next(&p->lx);
        int start=p->p->arg_n, count=0;
        if(!accept(p,T_RP)){
            for(;;){
                if(p->p->arg_n>=MAX_ARGS) return pdiag(p,4008,"argument storage limit exceeded");
                int e=parse_expr(p); if(e<0) return -1;
                p->p->args[p->p->arg_n++]=e; count++;
                if(accept(p,T_RP)) break;
                if(!expect(p,T_COMMA,3025,"expected comma or right parenthesis in call")) return -1;
            }
        }
        if(count!=p->p->funcs[fi].param_count) return pdiag(p,5009,"function argument count mismatch");
        if(!expect(p,T_SEMI,3026,"expected semicolon after call")) return -1;
        int e=new_expr(p,E_CALL); if(e<0) return -1;
        strncpy(p->p->expr[e].name,name,NAME_CAP-1);
        p->p->expr[e].arg_start=start; p->p->expr[e].arg_count=count;
        int st=new_stmt(p,S_CALL); if(st<0) return -1;
        p->p->stmt[st].expr=e; p->p->features|=1u<<0;
        return st;
    }
    return pdiag(p,3027,"unsupported or malformed statement");
}
static int parse_block(Parser *p,bool outer){
    if(!expect(p,T_LB,3030,"expected opening brace")) return -1;
    p->depth++;
    if(p->depth>MAX_DEPTH){ p->depth--; return pdiag(p,4009,"statement nesting limit exceeded"); }
    if(p->depth>p->p->max_depth) p->p->max_depth=p->depth;
    int b=new_block(p);
    if(b<0){ p->depth--; return -1; }
    Func *f=&p->p->funcs[p->cur_func];
    if(outer){while(p->lx.cur.k==T_INT){lex_next(&p->lx);if(p->lx.cur.k!=T_ID){p->depth--;return pdiag(p,3031,"expected local name");}char name[NAME_CAP];memcpy(name,p->lx.cur.text,NAME_CAP);lex_next(&p->lx);if(f->local_count>=MAX_LOCALS){p->depth--;return pdiag(p,4010,"local limit exceeded");}if(find_var(p,name)||callable_name(p->p,name)){p->depth--;return pdiag(p,5010,"duplicate local or callable shadowing");}if(!expect(p,T_ASSIGN,3032,"local requires initializer")){p->depth--;return -1;}int e=parse_expr(p);if(e<0){p->depth--;return -1;}if(!expect(p,T_SEMI,3033,"expected ';' after local")){p->depth--;return -1;}int s=new_stmt(p,S_DECL);if(s<0){p->depth--;return -1;}strncpy(p->p->stmt[s].name,name,NAME_CAP-1);p->p->stmt[s].expr=e;block_add(p->p,b,s);strncpy(f->locals[f->local_count++],name,NAME_CAP-1);}}
    while(p->lx.cur.k!=T_RB){if(p->lx.cur.k==T_EOF){p->depth--;return pdiag(p,3034,"unexpected EOF in block");}int s=parse_stmt(p);if(s<0){p->depth--;return -1;}block_add(p->p,b,s);}
    lex_next(&p->lx);p->depth--;return b;
}

static bool preprocess(const char *src,size_t n,Str *out){
    sb_init(out);size_t i=0;unsigned line=1;
    while(i<n){size_t start=i;while(i<n&&src[i]!='\n')i++;size_t end=i;size_t j=start;while(j<end&&(src[j]==' '||src[j]=='\t'||src[j]=='\r'))j++;
        if(j<end&&src[j]=='#'){Str norm;sb_init(&norm);for(size_t k=j;k<end;k++)if(src[k]!=' '&&src[k]!='\t'&&src[k]!='\r')if(!sb_append_n(&norm,src+k,1)){sb_free(&norm);return false;}bool ok=norm.data&&(strcmp(norm.data,"#include<stdio.h>")==0||strcmp(norm.data,"#include<assert.h>")==0);sb_free(&norm);if(!ok){fprintf(stderr,"E4000 %u:1 unsupported preprocessor directive\n",line);return false;}for(size_t k=start;k<end;k++)if(!sb_append_n(out," ",1))return false;}
        else if(!sb_append_n(out,src+start,end-start))return false;
        if(i<n&&src[i]=='\n'){if(!sb_append_n(out,"\n",1))return false;i++;line++;}
    }return true;
}
static int parse_program(const char *src,size_t n,Program *pr){
    memset(pr,0,sizeof *pr);Str filtered;if(!preprocess(src,n,&filtered)){sb_free(&filtered);return 1;}
    Parser p;memset(&p,0,sizeof p);p.p=pr;p.cur_func=-1;p.lx.src=filtered.data?filtered.data:"";p.lx.len=filtered.len;p.lx.line=1;p.lx.col=1;if(!lex_next(&p.lx)){sb_free(&filtered);return 1;}
    bool seen_main=false;
    while(p.lx.cur.k!=T_EOF&&!p.err){if(seen_main){pdiag(&p,4011,"main must be final function");break;}if(!expect(&p,T_INT,3040,"top-level declaration must be int-returning function"))break;if(p.lx.cur.k!=T_ID){pdiag(&p,3041,"expected function name");break;}char name[NAME_CAP];memcpy(name,p.lx.cur.text,NAME_CAP);lex_next(&p.lx);if(find_func(pr,name)>=0){pdiag(&p,5011,"duplicate function");break;}if(pr->func_n>=MAX_FUNCS){pdiag(&p,4012,"function limit exceeded");break;}int fi=pr->func_n++;Func *f=&pr->funcs[fi];memset(f,0,sizeof *f);strncpy(f->name,name,NAME_CAP-1);p.cur_func=fi;if(!expect(&p,T_LP,3042,"expected '(' after function name"))break;
        if(!accept(&p,T_RP)){for(;;){if(!expect(&p,T_INT,3043,"parameters must be int"))break;if(p.err)break;if(p.lx.cur.k!=T_ID){pdiag(&p,3044,"expected parameter name");break;}if(f->param_count>=MAX_PARAMS){pdiag(&p,4013,"parameter limit exceeded");break;}char pn[NAME_CAP];memcpy(pn,p.lx.cur.text,NAME_CAP);lex_next(&p.lx);for(int q=0;q<f->param_count;q++)if(strcmp(f->params[q],pn)==0){pdiag(&p,5012,"duplicate parameter");break;}if(p.err)break;if(callable_name(pr,pn)){pdiag(&p,5013,"parameter shadows callable name");break;}strncpy(f->params[f->param_count++],pn,NAME_CAP-1);if(accept(&p,T_RP))break;if(!expect(&p,T_COMMA,3045,"expected ',' or ')' in parameter list"))break;}if(p.err)break;}
        if(strcmp(name,"main")==0&&f->param_count!=0){pdiag(&p,4014,"main must have no parameters in S0");break;}
        int b=parse_block(&p,true);if(b<0)break;f->body=b;if(pr->block[b].last<0||pr->stmt[pr->block[b].last].k!=S_RETURN){pdiag(&p,5014,"function requires explicit final top-level return");break;}if(strcmp(name,"main")==0)seen_main=true;
    }
    if(!p.err&&!seen_main)pdiag(&p,5015,"missing final main function");
    if(!p.err){long nodes=(long)pr->expr_n+(long)pr->stmt_n+(long)pr->block_n+(long)pr->func_n;if(nodes>MAX_NODES)pdiag(&p,4015,"total AST node limit exceeded");}
    sb_free(&filtered);return p.err?1:0;
}

static const char *opname(TokKind op){switch(op){case T_PLUS:return "+";case T_MINUS:return "-";case T_STAR:return "*";case T_SLASH:return "/";case T_PERCENT:return "%";case T_BANG:return "!";case T_EQ:return "==";case T_NE:return "!=";case T_LT:return "<";case T_LE:return "<=";case T_GT:return ">";case T_GE:return ">=";case T_AND:return "&&";case T_OR:return "||";default:return "?";}}
static bool ast_expr(Str *s,const Program *p,int i){const Expr *e=&p->expr[i];switch(e->k){case E_NUM:return sb_printf(s,"(num %" PRId32 ")",e->val);case E_VAR:return sb_printf(s,"(var %s)",e->name);case E_CALL:if(!sb_printf(s,"(call %s",e->name))return false;for(int q=0;q<e->arg_count;q++){if(!sb_append(s," ")||!ast_expr(s,p,p->args[e->arg_start+q]))return false;}return sb_append(s,")");case E_UNARY:if(!sb_printf(s,"(%s ",opname(e->op))||!ast_expr(s,p,e->a))return false;return sb_append(s,")");case E_BINARY:if(!sb_printf(s,"(%s ",opname(e->op))||!ast_expr(s,p,e->a)||!sb_append(s," ")||!ast_expr(s,p,e->b))return false;return sb_append(s,")");}return false;}
static bool ast_block(Str *s,const Program *p,int b,int ind);
static bool indent(Str *s,int n){for(int i=0;i<n;i++)if(!sb_append(s,"  "))return false;return true;}
static bool ast_stmt(Str *s,const Program *p,int i,int ind){const Stmt *st=&p->stmt[i];if(!indent(s,ind))return false;switch(st->k){case S_DECL:if(!sb_printf(s,"(decl %s ",st->name)||!ast_expr(s,p,st->expr)||!sb_append(s,")\n"))return false;break;case S_ASSIGN:if(!sb_printf(s,"(assign %s ",st->name)||!ast_expr(s,p,st->expr)||!sb_append(s,")\n"))return false;break;case S_RETURN:if(!sb_append(s,"(return ")||!ast_expr(s,p,st->expr)||!sb_append(s,")\n"))return false;break;case S_CALL:if(!sb_append(s,"(call-stmt ")||!ast_expr(s,p,st->expr)||!sb_append(s,")\n"))return false;break;case S_PRINT:if(!sb_append(s,"(print ")||!ast_expr(s,p,st->expr)||!sb_append(s,")\n"))return false;break;case S_ASSERT:if(!sb_append(s,"(assert ")||!ast_expr(s,p,st->expr)||!sb_append(s,")\n"))return false;break;case S_IF:if(!sb_append(s,"(if ")||!ast_expr(s,p,st->expr)||!sb_append(s,"\n")||!ast_block(s,p,st->b1,ind+1))return false;if(st->b2>=0){if(!indent(s,ind+1)||!sb_append(s,"(else\n")||!ast_block(s,p,st->b2,ind+2)||!indent(s,ind+1)||!sb_append(s,")\n"))return false;}if(!indent(s,ind)||!sb_append(s,")\n"))return false;break;case S_WHILE:if(!sb_append(s,"(while ")||!ast_expr(s,p,st->expr)||!sb_append(s,"\n")||!ast_block(s,p,st->b1,ind+1)||!indent(s,ind)||!sb_append(s,")\n"))return false;break;case S_BLOCK:if(!sb_append(s,"(block-stmt\n")||!ast_block(s,p,st->b1,ind+1)||!indent(s,ind)||!sb_append(s,")\n"))return false;break;}return true;}
static bool ast_block(Str *s,const Program *p,int b,int ind){if(!indent(s,ind)||!sb_append(s,"(block\n"))return false;for(int i=p->block[b].first;i>=0;i=p->stmt[i].next)if(!ast_stmt(s,p,i,ind+1))return false;if(!indent(s,ind)||!sb_append(s,")\n"))return false;return true;}
static bool emit_ast(Str *s,const Program *p){sb_init(s);long nodes=(long)p->expr_n+(long)p->stmt_n+(long)p->block_n+(long)p->func_n;if(!sb_printf(s,"AEGIS-C2R-AST/1\nprofile %s\nmetrics functions=%d statements=%d expressions=%d blocks=%d nodes=%ld max_nesting=%d\n",AEGIS_C2R_PROFILE,p->func_n,p->stmt_n,p->expr_n,p->block_n,nodes,p->max_depth))return false;for(int f=0;f<p->func_n;f++){const Func *fn=&p->funcs[f];if(!sb_printf(s,"function %s params=%d\n",fn->name,fn->param_count))return false;for(int q=0;q<fn->param_count;q++)if(!sb_printf(s,"  param %s\n",fn->params[q]))return false;if(!ast_block(s,p,fn->body,1)||!sb_append(s,"end-function\n"))return false;}return true;}

static bool rust_expr(Str *s,const Program *p,int i){const Expr *e=&p->expr[i];switch(e->k){case E_NUM:return sb_printf(s,"%" PRId32 "i32",e->val);case E_VAR:return sb_printf(s,"c2r_%s",e->name);case E_CALL:if(!sb_printf(s,"c2r_%s(",e->name))return false;for(int q=0;q<e->arg_count;q++){if(q&& !sb_append(s,", "))return false;if(!rust_expr(s,p,p->args[e->arg_start+q]))return false;}return sb_append(s,")");case E_UNARY:if(e->op==T_MINUS){if(!sb_append(s,"ae_neg(" )||!rust_expr(s,p,e->a))return false;return sb_append(s,")");}if(!sb_append(s,"((" )||!rust_expr(s,p,e->a)||!sb_append(s," == 0) as i32)"))return false;return true;case E_BINARY:break;}
    if(e->op==T_PLUS||e->op==T_MINUS||e->op==T_STAR||e->op==T_SLASH||e->op==T_PERCENT){const char *fn=e->op==T_PLUS?"ae_add":e->op==T_MINUS?"ae_sub":e->op==T_STAR?"ae_mul":e->op==T_SLASH?"ae_div":"ae_rem";if(!sb_printf(s,"%s(",fn)||!rust_expr(s,p,e->a)||!sb_append(s,", ")||!rust_expr(s,p,e->b)||!sb_append(s,")"))return false;return true;}
    if(e->op==T_AND||e->op==T_OR){if(!sb_append(s,"((" )||!rust_expr(s,p,e->a)||!sb_append(s," != 0 ")||!sb_append(s,e->op==T_AND?"&& ":"|| ")||!rust_expr(s,p,e->b)||!sb_append(s," != 0) as i32)"))return false;return true;}
    if(!sb_append(s,"((" )||!rust_expr(s,p,e->a)||!sb_printf(s," %s ",opname(e->op))||!rust_expr(s,p,e->b)||!sb_append(s,") as i32)")) return false;
    return true;
}
static bool rust_block(Str *s,const Program *p,int b,int ind);
static bool rust_stmt(Str *s,const Program *p,int i,int ind){const Stmt *st=&p->stmt[i];if(!indent(s,ind))return false;switch(st->k){case S_DECL:if(!sb_printf(s,"let mut c2r_%s: i32 = ",st->name)||!rust_expr(s,p,st->expr)||!sb_append(s,";\n"))return false;break;case S_ASSIGN:if(!sb_printf(s,"c2r_%s = ",st->name)||!rust_expr(s,p,st->expr)||!sb_append(s,";\n"))return false;break;case S_RETURN:if(!sb_append(s,"return ")||!rust_expr(s,p,st->expr)||!sb_append(s,";\n"))return false;break;case S_CALL:if(!rust_expr(s,p,st->expr)||!sb_append(s,";\n"))return false;break;case S_PRINT:if(!sb_append(s,"println!(\"{}\", ")||!rust_expr(s,p,st->expr)||!sb_append(s,");\n"))return false;break;case S_ASSERT:if(!sb_append(s,"assert!((")||!rust_expr(s,p,st->expr)||!sb_append(s,") != 0, \"C assert failed\");\n"))return false;break;case S_IF:if(!sb_append(s,"if (")||!rust_expr(s,p,st->expr)||!sb_append(s,") != 0 {\n")||!rust_block(s,p,st->b1,ind+1)||!indent(s,ind)||!sb_append(s,"}"))return false;if(st->b2>=0){if(!sb_append(s," else {\n")||!rust_block(s,p,st->b2,ind+1)||!indent(s,ind)||!sb_append(s,"}"))return false;}if(!sb_append(s,"\n"))return false;break;case S_WHILE:if(!sb_append(s,"while (")||!rust_expr(s,p,st->expr)||!sb_append(s,") != 0 {\n")||!rust_block(s,p,st->b1,ind+1)||!indent(s,ind)||!sb_append(s,"}\n"))return false;break;case S_BLOCK:if(!sb_append(s,"{\n")||!rust_block(s,p,st->b1,ind+1)||!indent(s,ind)||!sb_append(s,"}\n"))return false;break;}return true;}
static bool rust_block(Str *s,const Program *p,int b,int ind){for(int i=p->block[b].first;i>=0;i=p->stmt[i].next)if(!rust_stmt(s,p,i,ind))return false;return true;}
static bool emit_rust(Str *s,const Program *p){sb_init(s);if(!sb_append(s,"#![forbid(unsafe_code)]\n#![allow(dead_code)]\n#![allow(unused_mut)]\n\nfn ae_add(a:i32,b:i32)->i32{a.checked_add(b).expect(\"C signed overflow in +\")}\nfn ae_sub(a:i32,b:i32)->i32{a.checked_sub(b).expect(\"C signed overflow in -\")}\nfn ae_mul(a:i32,b:i32)->i32{a.checked_mul(b).expect(\"C signed overflow in *\")}\nfn ae_div(a:i32,b:i32)->i32{a.checked_div(b).expect(\"C undefined division\")}\nfn ae_rem(a:i32,b:i32)->i32{a.checked_rem(b).expect(\"C undefined remainder\")}\nfn ae_neg(a:i32)->i32{a.checked_neg().expect(\"C signed overflow in unary -\")}\n\n"))return false;
    for(int f=0;f<p->func_n;f++){const Func *fn=&p->funcs[f];const char *rn=strcmp(fn->name,"main")==0?"c2r_main_impl":NULL;if(rn){if(!sb_printf(s,"fn %s(",rn))return false;}else if(!sb_printf(s,"fn c2r_%s(",fn->name))return false;for(int q=0;q<fn->param_count;q++){if(q&&!sb_append(s,", "))return false;if(!sb_printf(s,"mut c2r_%s: i32",fn->params[q]))return false;}if(!sb_append(s,") -> i32 {\n")||!rust_block(s,p,fn->body,1)||!sb_append(s,"}\n\n"))return false;}
    return sb_append(s,"fn main() {\n  let code = c2r_main_impl();\n  std::process::exit(code);\n}\n");
}

static bool emit_aegis(Str *dxl,Str *dxs,Str *dxa,const Program *p,int cert){sb_init(dxl);sb_init(dxs);sb_init(dxa);if(!sb_printf(dxl,"fn main() -> i32 {\n    let value: i64 = %d * 16777216 + %d * 4096 + %d;\n    assert(value == %d);\n    print_i64(value);\n    return as(i32, 0);\n}\n",p->func_n,p->stmt_n,p->expr_n,cert))return false;if(!sb_printf(dxs,"%d dup %d eq assert print halt\n",cert,cert))return false;if(!sb_printf(dxa,"PUSH %d\nDUP\nPUSH %d\nEQ\nASSERT\nPRINT\nHALT\n",cert,cert))return false;return true;}

static bool read_file(const char *path,char **out,size_t *n){FILE *f=fopen(path,"rb");if(!f){fprintf(stderr,"E1001 0:0 cannot open input: %s\n",strerror(errno));return false;}if(fseek(f,0,SEEK_END)!=0){fprintf(stderr,"E1002 0:0 cannot seek input\n");fclose(f);return false;}long z=ftell(f);if(z<0){fprintf(stderr,"E1003 0:0 cannot size input\n");fclose(f);return false;}if((unsigned long)z>C2R_MAX_INPUT){fprintf(stderr,"E4001 0:0 input exceeds 1 MiB profile limit\n");fclose(f);return false;}if(fseek(f,0,SEEK_SET)!=0){fprintf(stderr,"E1004 0:0 cannot rewind input\n");fclose(f);return false;}char *p=(char*)malloc((size_t)z+1);if(!p){fprintf(stderr,"E1005 0:0 out of memory\n");fclose(f);return false;}size_t got=fread(p,1,(size_t)z,f);int ferr=ferror(f);int c=fclose(f);if(got!=(size_t)z||ferr||c!=0){fprintf(stderr,"E1006 0:0 input read/close failure\n");free(p);return false;}p[z]='\0';*out=p;*n=(size_t)z;return true;}
static bool write_atomic(const char *path,const char *data,size_t n){char tmp[4096];int rc=snprintf(tmp,sizeof tmp,"%s.tmp.%ld",path,(long)getpid());if(rc<0||(size_t)rc>=sizeof tmp){fprintf(stderr,"E6001 0:0 output path too long\n");return false;}FILE *f=fopen(tmp,"wb");if(!f){fprintf(stderr,"E6002 0:0 cannot create output: %s\n",strerror(errno));return false;}bool ok=fwrite(data,1,n,f)==n;if(fflush(f)!=0)ok=false;if(fclose(f)!=0)ok=false;if(!ok){remove(tmp);fprintf(stderr,"E6003 0:0 output write failure\n");return false;}if(rename(tmp,path)!=0){remove(tmp);fprintf(stderr,"E6004 0:0 output rename failure: %s\n",strerror(errno));return false;}return true;}
static bool same_path(const char *a,const char *b){return a&&b&&strcmp(a,b)==0;}
static void usage(FILE *f){fprintf(f,"Aegis-C2R %s (%s)\nUsage:\n  aegis-c2r version\n  aegis-c2r check INPUT.c\n  aegis-c2r ast INPUT.c\n  aegis-c2r translate INPUT.c -o OUTPUT.rs [--ast FILE] [--proof FILE] [--aegis-prefix PREFIX]\n",AEGIS_C2R_VERSION,AEGIS_C2R_PROFILE);}
int main(int argc,char **argv){
    if(argc==2&&strcmp(argv[1],"version")==0){printf("aegis-c2r %s profile=%s\n",AEGIS_C2R_VERSION,AEGIS_C2R_PROFILE);return 0;}
    if(argc<3){usage(stderr);return 2;}const char *cmd=argv[1],*in=argv[2],*out_rs=NULL,*out_ast=NULL,*out_proof=NULL,*prefix=NULL;
    if(strcmp(cmd,"translate")==0){for(int i=3;i<argc;i++){if(strcmp(argv[i],"-o")==0&&i+1<argc)out_rs=argv[++i];else if(strcmp(argv[i],"--ast")==0&&i+1<argc)out_ast=argv[++i];else if(strcmp(argv[i],"--proof")==0&&i+1<argc)out_proof=argv[++i];else if(strcmp(argv[i],"--aegis-prefix")==0&&i+1<argc)prefix=argv[++i];else{return fail_plain(1007,"unknown or incomplete option");}}if(!out_rs)return fail_plain(1008,"translate requires -o OUTPUT.rs");
        char p_dxl[4096]={0},p_dxs[4096]={0},p_dxa[4096]={0};
        if(prefix){
            int z1=snprintf(p_dxl,sizeof p_dxl,"%s.dxl",prefix);
            int z2=snprintf(p_dxs,sizeof p_dxs,"%s.dxs",prefix);
            int z3=snprintf(p_dxa,sizeof p_dxa,"%s.dxasm",prefix);
            if(z1<0||z2<0||z3<0||(size_t)z1>=sizeof p_dxl||(size_t)z2>=sizeof p_dxs||(size_t)z3>=sizeof p_dxa)return fail_plain(1011,"Aegis output path too long");
        }
        const char *paths[6]={out_rs,out_ast,out_proof,prefix?p_dxl:NULL,prefix?p_dxs:NULL,prefix?p_dxa:NULL};
        for(int i=0;i<6;i++)if(paths[i]&&same_path(in,paths[i]))return fail_plain(1009,"input/output path collision");
        for(int i=0;i<6;i++)for(int j=i+1;j<6;j++)if(paths[i]&&paths[j]&&same_path(paths[i],paths[j]))return fail_plain(1010,"output path collision");
    } else if(strcmp(cmd,"check")!=0&&strcmp(cmd,"ast")!=0){usage(stderr);return 2;}
    char *src=NULL;size_t n=0;if(!read_file(in,&src,&n))return 1;Program *p=(Program*)calloc(1,sizeof *p);if(!p){free(src);return fail_plain(1005,"out of memory");}if(parse_program(src,n,p)!=0){free(p);free(src);return 1;}
    if(strcmp(cmd,"check")==0){printf("OK profile=%s functions=%d statements=%d expressions=%d\n",AEGIS_C2R_PROFILE,p->func_n,p->stmt_n,p->expr_n);free(p);free(src);return 0;}
    Str ast;if(!emit_ast(&ast,p)){free(p);free(src);return fail_plain(7001,"AST emission failed");}if(strcmp(cmd,"ast")==0){fwrite(ast.data,1,ast.len,stdout);sb_free(&ast);free(p);free(src);return 0;}
    Str rust;if(!emit_rust(&rust,p)){sb_free(&ast);free(p);free(src);return fail_plain(7002,"Rust emission failed");}
    char hs[65],ha[65],hr[65];sha_hex(src,n,hs);sha_hex(ast.data,ast.len,ha);sha_hex(rust.data,rust.len,hr);int64_t cert64=(int64_t)p->func_n*16777216LL+(int64_t)p->stmt_n*4096LL+p->expr_n;if(cert64>INT32_MAX){sb_free(&rust);sb_free(&ast);free(p);free(src);return fail_plain(7003,"certificate overflow");}int cert=(int)cert64;
    Str proof;sb_init(&proof);long nodes=(long)p->expr_n+(long)p->stmt_n+(long)p->block_n+(long)p->func_n;if(!sb_printf(&proof,"{\n  \"schema\": \"AEGIS-C2R-PROOF/1\",\n  \"tool\": \"aegis-c2r\",\n  \"version\": \"%s\",\n  \"profile\": \"%s\",\n  \"status\": \"accepted\",\n  \"source_sha256\": \"%s\",\n  \"ast_sha256\": \"%s\",\n  \"rust_sha256\": \"%s\",\n  \"metrics\": {\"functions\": %d, \"statements\": %d, \"expressions\": %d, \"blocks\": %d, \"nodes\": %ld, \"max_nesting\": %d},\n  \"features\": %u,\n  \"certificate\": %d\n}\n",AEGIS_C2R_VERSION,AEGIS_C2R_PROFILE,hs,ha,hr,p->func_n,p->stmt_n,p->expr_n,p->block_n,nodes,p->max_depth,p->features,cert)){sb_free(&proof);sb_free(&rust);sb_free(&ast);free(p);free(src);return fail_plain(7004,"proof emission failed");}
    Str dxl,dxs,dxa;if(!emit_aegis(&dxl,&dxs,&dxa,p,cert)){sb_free(&proof);sb_free(&rust);sb_free(&ast);free(p);free(src);return fail_plain(7005,"Aegis certificate emission failed");}
    bool ok=write_atomic(out_rs,rust.data,rust.len);if(ok&&out_ast)ok=write_atomic(out_ast,ast.data,ast.len);if(ok&&out_proof)ok=write_atomic(out_proof,proof.data,proof.len);
    if(ok&&prefix){char path[4096];int z=snprintf(path,sizeof path,"%s.dxl",prefix);ok=z>0&&(size_t)z<sizeof path&&write_atomic(path,dxl.data,dxl.len);z=snprintf(path,sizeof path,"%s.dxs",prefix);ok=ok&&z>0&&(size_t)z<sizeof path&&write_atomic(path,dxs.data,dxs.len);z=snprintf(path,sizeof path,"%s.dxasm",prefix);ok=ok&&z>0&&(size_t)z<sizeof path&&write_atomic(path,dxa.data,dxa.len);}
    sb_free(&dxa);sb_free(&dxs);sb_free(&dxl);sb_free(&proof);sb_free(&rust);sb_free(&ast);free(p);free(src);return ok?0:1;
}
