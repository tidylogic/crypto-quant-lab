# Agent Folder Rules

`.agents` is the source of truth for agent-owned project assets.

Use this layout:

```text
.agents/
  skills/
  rules/
```

Compatibility paths should be symbolic links, not duplicate directories:

```text
.claude/skills -> ../.agents/skills
.claude/rules -> ../.agents/rules
CLAUDE.md -> AGENTS.md
```

Do not create a root-level `skills` path. When adding a new skill or rule, write it under `.agents` first, then add or update agent-specific symlinks only when a tool needs a compatibility path.
