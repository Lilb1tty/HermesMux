# Domain Docs

How engineering skills should consume this repository's domain documentation when exploring the codebase.

## Before exploring, read these

- `CONTEXT.md` at the repository root, or
- `CONTEXT-MAP.md` at the repository root if it exists; it points at one `CONTEXT.md` per context.
- `docs/adr/` for decisions that touch the area being changed.

If these files do not exist, proceed silently. The domain-modeling skill creates them lazily when terms or decisions need recording.

## File structure

This is a single-context repository:

```
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Use the glossary's vocabulary

When naming a domain concept in issues, refactor proposals, hypotheses, or tests, use the term defined in `CONTEXT.md`. If a needed concept is absent, reconsider the terminology or note the gap for domain modeling.

## Flag ADR conflicts

When output contradicts an existing ADR, surface it explicitly rather than silently overriding it.
