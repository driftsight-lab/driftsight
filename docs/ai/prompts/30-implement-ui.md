# 30. Implementation — frontend (UI)

## Purpose

Implement a confirmed issue scope in `frontend/` one commit at a time, with approval for each commit.

## When to use

After the user approves the stage 00 report and the stage 10 plan. Used by both AI-SVC (operations UI) and AI-MDL (experiment UI) — App Router is common to both.

## Inputs

- The issue number and confirmed scope from stages 00 and 10
- The ADRs and reference documents chosen in stage 00
- `frontend/CLAUDE.md` — tech conventions
- `docs/specs/api.md` — API types and endpoints
- `docs/ui/README.md` and the screen's mockup — layout reference only. Data and behavior follow `docs/specs/api.md` and the ADRs; known differences are listed in the README
- Check existing code for precedents before planning:
  - `src/app/` — existing route and layout patterns
  - `src/components/` — existing shared component patterns
  - `src/lib/` — existing API client patterns

## Steps — A. Plan

1. Output the implementation plan first. Do not write code yet.
   - Order commits so that each one builds independently: shared types and components before the features that use them.
   - For each file, decide: Server Component (default) or Client Component (`"use client"` required only for browser APIs, event handlers, or React hooks).
   - Tests go in the same commit as the code they test.
   - Follow `frontend/CLAUDE.md` §3 for directory placement.
   - For each commit, list the files, the component type (Server/Client), and the commit message (`{type}({domain}): {subject}` from `CONTRIBUTING.md`).
   - Cite grounds for each decision as `document > section`.
2. List the following as option tables only. Do not decide.
   - Component decomposition not settled by the specification
   - State placement choices (URL state, server state, client state)
   - UI behaviors or values not in the documents
3. If an ADR and a reference document differ, follow the ADR and list the difference.
4. If the work requires a new endpoint or type change in `docs/specs/api.md`, stop planning and propose the document change first.
5. For Stack PRs, note the base branch. Branch creation: `git switch -c {branch} {base}`.
6. Output the plan and wait for approval.

## Steps — B. Each commit

1. Write or change only the files in the plan for this commit. If another file is needed, say so and wait for approval.
2. Run the pre-commit routine and show results:
   ```bash
   npm run lint
   ```
3. Show `git diff --stat` and the commit message, and wait for approval.
4. Commit only after the user says to commit. Output the push command; do not run it.
5. Before committing, verify:
   - API calls use `/api/v1` as the base path — no hardcoded host.
   - `NEXT_PUBLIC_` environment variables contain no secrets.
   - Recharts components that render in a flexible container are wrapped in `<ResponsiveContainer>`.
   - Time-series charts with version change events use `<ReferenceLine>` to mark the timestamps.
   - No `any` types — use `unknown` and narrow with type guards.
   - No inline `style={{}}` — Tailwind utility classes only.
   - No new package installed without explanation and approval.
6. If something fails during implementation, go to stage 60 (troubleshoot). Apply the fix through this step B after returning.

## Output format

```markdown
### 커밋 계획
| # | 구분 | 파일 | Server/Client | 커밋 메시지 | 근거 |
| --- | --- | --- | --- | --- | --- |

### 결정 필요
| 판단 | 선택지 | 장점 | 단점 | 근거 문서 |
| --- | --- | --- | --- | --- |

### ADR과 기준 문서의 차이
-
```

## Do not

- Write code before the plan is approved.
- Change files outside the plan without approval.
- Use `any` — use `unknown` with a type guard.
- Add inline `style={{}}` or CSS Modules.
- Use a hardcoded API host instead of `/api/v1`.
- Put secrets in `NEXT_PUBLIC_` variables.
- Create a `pages/` directory — App Router only.
- Install a new package without explaining why and getting approval.
- Commit while `npm run lint` fails.
- Push — output the push command for the user to run.

## Human gate

- Approve the plan; decide items under 결정 필요; create a document issue when a contract change is needed.
- Review `git diff --stat` and the commit message for each commit, then say to commit.

---

end.