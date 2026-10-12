# Integrated Frontend Profile

This file defines exactly what the integrated frontend recognizes today. It is
an acceptance profile for continuing the self-hosting work, not the complete
DXL language specification.

## Grammar

The notation uses `*` for repetition, `?` for an optional item, and `|` for a
choice.

```text
program       := declaration* EOF
declaration   := modifier? (import | const | function | struct | enum)
               | test | comptime-block
modifier      := "comptime" | "export" | "extern"
import        := "import" STRING ";"
const         := "const" IDENT (":" type)? "=" expression ";"
function      := "fn" IDENT "(" parameters? ")" ("->" type)? block
parameters    := parameter ("," parameter)*
parameter     := IDENT ":" type
struct        := "struct" IDENT "{" (IDENT ":" type ","?)* "}"
enum          := "enum" IDENT "{" (IDENT ","?)* "}"
test          := "test" STRING block
comptime-block:= "comptime" block
type          := "i64" | "i32" | "bool" | "void"
               | "array_i64" | "slice_i64" | "result_i64" | IDENT
block         := "{" statement* "}"
statement     := let | assignment | return | assert | while | if | expr-stmt
let           := "let" IDENT (":" type)? "=" expression ";"
assignment    := expression "=" expression ";"
return        := "return" expression ";"
assert        := "assert" "(" expression ")" ";"
while         := "while" expression block
if            := "if" expression block ("else" (block | if))?
expr-stmt     := expression ";"
expression    := primary postfix* binary-expression*
primary       := INTEGER | "true" | "false" | IDENT | call | cast
               | struct-literal | "(" expression ")" | unary
call          := IDENT "(" arguments? ")"
cast          := "as" "(" type "," expression ")"
unary         := ("-" | "!") expression
postfix       := "[" expression "]" | "." IDENT
struct-literal:= IDENT "{" (IDENT ":" expression ","?)* "}"
binary        := "||" | "&&" | "==" | "!=" | "<" | "<=" | ">" | ">="
               | "+" | "-" | "*" | "/" | "%"
```

Binary precedence is, from lowest to highest: Boolean OR, Boolean AND,
equality, ordering, addition/subtraction, multiplication/division/remainder.
All binary operators are left-associative. Unary operators bind more tightly.
Expression and statement/block recursion are independently limited to 128
levels. Inputs beyond either limit reject with diagnostic `1408`.

## Semantic coverage

The semantic pass currently provides:

- unique lexical scope identifiers and explicit parent-scope traversal;
- duplicate value/function detection in one scope;
- forward visibility for functions and declared constants;
- deterministic fixed-point inference for unannotated constants and lets,
  bounded by `AST count + 1` monotonic rounds and 4,194,304 node visits;
- primitive arithmetic, comparison, and Boolean operator checking;
- assignment, condition, assertion, and function-return checking;
- user-function name/callability resolution;
- primitive casts and `array_i64`/`slice_i64` index-result typing.

Named aggregate syntax is parsed, but aggregate declarations are not yet
interned into a semantic type graph. Therefore field access and named aggregate
operations deliberately remain unresolved.

## Typed-IR record

The driver prints one signed decimal integer per line. The first 13 records are:

| Line | Meaning |
|---:|---|
| 1 | Record format identifier (`24301`) |
| 2 | Token count |
| 3 | Lexer diagnostic count |
| 4 | Lexer fatal code |
| 5 | AST node count |
| 6 | Parser diagnostic count |
| 7 | Scope count |
| 8 | Symbol count |
| 9 | Typed-expression count |
| 10 | Total frontend diagnostic count |
| 11 | Typed-IR instruction count |
| 12 | Input-derived typed-IR digest |
| 13 | Frontend fatal code |

Lexer diagnostics follow as `(code, line, column)` triples, then frontend
diagnostics in the same form. Typed-IR instructions follow as six values:
`(opcode, AST node, type, value, parent AST node, lexical scope)`.

## Self-source acceptance

The generated frontend accepts `model.dxl` end-to-end. It also accepts the
complete new frontend source lexically and syntactically. Semantic closure of
the multi-file compiler is intentionally not accepted yet because imports are
not recursively loaded and named aggregate/builtin signatures are unresolved.
That rejected gate is executed twice by the test runner and its output must be
byte-identical.

## Deliberately unsupported

- recursive import loading, cycle detection, and cross-module symbol identity;
- generic parameter lists and monomorphization;
- enum payload syntax and exhaustive matching;
- strings as general expressions and validated string typing;
- field schemas, aggregate layout, and complex-lvalue semantic checking;
- builtin signatures and ownership effects for arrays, slices, results, file
  arguments, and output;
- extern declarations without bodies;
- empty `return;`, comptime evaluation, and ownership/borrow checking;
- native executable emission from this frontend's typed IR.

These omissions are blockers, not implicit extensions.
