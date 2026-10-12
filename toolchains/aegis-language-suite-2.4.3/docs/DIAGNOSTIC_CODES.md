# Diagnostic codes

New Aegis compiler components use stable identifiers in the form `AEGnnnn`. One identifier maps to one public failure condition and is not reassigned within the 2.4 line.

## Registry ranges

| Range | Area |
| --- | --- |
| `AEG1000–AEG1199` | Source loading and table-driven lexing |
| `AEG1200–AEG1399` | Focused parser arena and recovery foundations |
| `AEG1400–AEG1499` | Integrated frontend parser and recovery |
| `AEG1500–AEG1599` | Integrated frontend name/type analysis |
| `AEG1600–AEG1699` | Integrated frontend typed-IR lowering |
| `AEG2500–AEG2599` | Relocatable-object fixture |
| `AEG2700–AEG2799` | DXL native-core compiler and public driver |
| `AEG2800–AEG2899` | DXL native executable writer |
| `AEG3000–AEG3599` | Future project and developer tools |
| `AEG4000–AEG4799` | Reserved DXB3 diagnostic migration and future runtime profiles |
| `AEG9000–AEG9099` | Internal invariants |

## Authoritative registries

- The integrated frontend registry is [`compiler/dxl/selfhost/full/DIAGNOSTICS.md`](../compiler/dxl/selfhost/full/DIAGNOSTICS.md).
- The native compiler/public-driver registry is the machine-readable [`compiler/dxl/native/diagnostics.tsv`](../compiler/dxl/native/diagnostics.tsv).
- Focused lexer/parser/object identifiers remain declared in their DXL modules and summarized below.

The bundled native diagnostic table is byte-compared with the source table during static verification. The public wrapper renders the table's message for numeric compiler failures.

## Implemented focused codes

| Codes | Conditions |
| --- | --- |
| `AEG1001–AEG1008`, `AEG1010` | Invalid byte, unterminated string/comment, invalid escape/integer, overflow, table/diagnostic/token capacity |
| `AEG1202–AEG1207` | Expected declaration, statement, name, semicolon, opening brace, closing brace |
| `AEG1298–AEG1299` | Recovery progress guard and AST capacity |
| `AEG2501–AEG2503` | Object buffer, write, and argument failures |

## Integrated frontend codes

| Codes | Area |
| --- | --- |
| `AEG1401–AEG1408` | Expected grammar elements, unclosed block, and nesting limit |
| `AEG1498–AEG1499` | Recovery progress and bounded arena capacity |
| `AEG1501–AEG1509` | Duplicate/unknown name, type/condition/return/assert/call errors, unresolved type, inference limit |
| `AEG1601` | Typed-IR arena capacity |

## Native compiler and driver codes

The native registry includes:

- parser/type/capacity conditions `AEG2702–AEG2730`;
- `AEG2731` when `run` receives test blocks;
- `AEG2732` when `test` receives a `main` program;
- `AEG2733` when a test block attempts early `return`;
- public command/input/output conditions `AEG2790–AEG2797`;
- executable-writer conditions `AEG2801–AEG2802`.

Use the TSV registry for exact stable messages rather than duplicating them in tools.

## Runtime exit statuses

Native runtime statuses `70` (overflow/cast), `71` (assertion), `72` (loop fuel), and `73` (user return outside `0..63`) are process exit statuses, not `AEG` compiler diagnostics. DXB3 verifier/VM errors retain their profile-defined numeric representation; migration of every established runtime condition to a unique `AEG` message is incomplete.

The established compatibility frontend also still emits some human-readable diagnostics without numeric migration. Therefore 2.4.3 claims complete code/message coverage only for the new integrated and native-core registries, not for every older diagnostic surface.
