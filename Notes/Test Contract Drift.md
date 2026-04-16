# Test Contract Drift

## Meaning
Tests failed because backend contracts evolved:
- detector reasoning text changed
- dispatcher reasoning text changed
- execution schema gained required trace fields

## Lesson
When explainability fields are upgraded, test assertions must be updated to match the new contract.

## Rule
Do not weaken backend semantics just to satisfy stale tests.
Update tests when the new contract is more precise and intentional.

## Related
- [[Decision Trace Model]]
- [[Audit Trail Design]]
- [[Testing Strategy]]