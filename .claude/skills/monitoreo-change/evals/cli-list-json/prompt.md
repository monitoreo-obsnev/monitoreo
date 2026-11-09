---
tags: [monitoreo-change]
max_turns: 60
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Add a --json option to the `monitoreo list` command so it prints the variables of the catalog as JSON instead of the table. I want to pipe it into jq.
