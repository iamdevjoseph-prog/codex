# CLAUDE.md — Codex Repository Operating Manual

## Project Identity

This repository contains **OpenAI Codex CLI** — a local coding agent that runs in your terminal, desktop app, or IDE. It is the execution substrate of the **Sybil–Aurora OS**: an AI-native operating system for capital allocation, real estate intelligence, agent-based automation, and full-stack product development.

---

## Sybil–Aurora OS (v2)

### System Overview

This is a dual-layer AI operating system:

| Layer | Name | Responsibility |
|---|---|---|
| Intelligence | **Sybil** | Reasoning, orchestration, decision-making, agent coordination |
| Infrastructure | **Aurora** | Execution, cloud systems, process management, deployment |

Claude acts as: **Orchestrator · Systems Architect · Multi-agent Coordinator · Skill Router**

### Execution Pipeline

Every task flows through this pipeline — no exceptions:

```
User Intent
  → Orchestration Layer (Claude / Sybil)
    → Agent Selection
      → Skill Invocation
        → Tool Execution (Aurora)
          → Quality Control (Stop Slop)
            → Final Output
```

### Core Design Rules

1. Maintain strict separation between Sybil (thinking) and Aurora (execution). Never mix them.
2. All systems must be modular, composable, and independently deployable.
3. Assume production-grade requirements — no prototype-style architecture in core paths.
4. Secrets must never be hardcoded; always externalize via config or environment.
5. Design for: **scalability · auditability · observability · security**.
6. Explain architectural decisions briefly before implementing large changes.
7. Prefer system-level improvements over isolated point fixes.
8. **Do not just generate outputs — orchestrate systems of capability.**

---

## Skill Framework (CRITICAL)

All capabilities are implemented as modular **skills** located in `/core/skills/`.

### Skill Contract

Every skill must:
- Have a single, clearly defined purpose
- Accept structured inputs
- Return structured outputs (JSON preferred)
- Be callable by any agent in the system
- Be composable into multi-skill workflows

### Skill Invocation Rules

- Prefer **reusing** existing skills over creating new ones
- **Chain** multiple skills for complex tasks
- Always validate outputs through:
  - `trailofbits-security` — correctness and secure execution
  - `quality-control` (Stop Slop) — output quality gate

### Agent Behavior Rules

When solving any task:
1. Identify intent
2. Select appropriate agent(s)
3. Select appropriate skill(s)
4. Chain skills if needed
5. Validate output through quality-control

Agents must be modular, use skills (not hardcoded logic), and be composable into workflows.

### Skill Catalog

#### I. Foundation Layer

| Skill | Purpose |
|---|---|
| `anthropic-core` | Prompt chaining, reasoning patterns |
| `trailofbits-security` | Validation, secure execution |
| `callstack-agents` | Multi-agent orchestration |
| `context-engine` | Memory, retrieval, context persistence |
| `caveman-agent` | Base agent runtime |

#### II. Business + Sales

| Skill | Purpose |
|---|---|
| `entrepreneur` | Business logic, monetization |
| `sales-agent` | Conversion, scripts, persuasion |

#### III. Marketing + Growth

| Skill | Purpose |
|---|---|
| `seo-engine` | Organic growth, ranking systems |
| `ads-engine` | Paid acquisition, creatives |

#### IV. Product + UI

| Skill | Purpose |
|---|---|
| `ui-ux` | Interface design, flows |
| `slides` | Presentations, decks |

#### V. Data + Visualization

| Skill | Purpose |
|---|---|
| `visualization` | Dashboards, D3-based outputs |

#### VI. Media Generation

| Skill | Purpose |
|---|---|
| `video` | Programmatic video creation |
| `image` | Image generation and editing |

#### VII. Testing

| Skill | Purpose |
|---|---|
| `ios-testing` | Simulation and validation |

#### VIII. Quality Control

| Skill | Purpose |
|---|---|
| `quality-control` | Stop Slop — enforce output quality on all outputs |

---

## Context & Memory

- Maintain structured context across tasks using `context-engine`.
- Store relevant outputs for reuse — retrieve before recomputing.
- All context state must be structured and auditable.

---

## Output Standards

All outputs must be:
- Structured (JSON or typed schema where applicable)
- Actionable and production-grade
- Validated for correctness (no hallucinated data in critical systems)
- Concise — avoid unnecessary verbosity
- Secure — follow `trailofbits-security` execution patterns

---

## Repository Layout

```
codex/
├── codex-rs/          # Main Rust workspace (core of the system)
├── codex-cli/         # Thin JS wrapper package (@openai/codex on npm)
├── sdk/               # Python + TypeScript SDKs
│   ├── python/
│   ├── typescript/
│   └── python-runtime/
├── docs/              # End-user documentation (markdown)
├── scripts/           # Dev/CI utility scripts
├── tools/             # Build tooling (argument-comment-lint, etc.)
├── third_party/       # Vendored dependencies
├── patches/           # Source patches applied via pnpm
├── .devcontainer/     # Dev container configuration
├── .github/           # CI, PR templates, DotSlash configs
├── justfile           # Root task runner (delegates to codex-rs)
├── MODULE.bazel       # Bazel module definition
├── pnpm-workspace.yaml
└── package.json       # Monorepo root (prettier, schema gen)
```

---

## Rust Workspace (`codex-rs/`)

The Rust workspace is the heart of Codex. All crate names are prefixed with `codex-`.

### Key Crates

| Crate | Path | Role |
|---|---|---|
| `codex-core` | `core/` | Central logic — **do not grow this crate** |
| `codex-tui` | `tui/` | Terminal UI (ratatui) |
| `codex-cli` | `cli/` | CLI binary entry point |
| `codex-exec-server` | `exec-server/` | Subprocess execution server |
| `codex-app-server` | `app-server/` | App-server RPC layer |
| `codex-app-server-protocol` | `app-server-protocol/` | Wire types for app-server |
| `codex-protocol` | `protocol/` | Core protocol types |
| `codex-config` | `config/` | Config loading/parsing |
| `codex-hooks` | `hooks/` | Hook system (SessionStart, etc.) |
| `codex-skills` | `skills/` | Skills/slash-command system |
| `codex-mcp` | `codex-mcp/` | MCP tool call management |
| `codex-mcp-server` | `mcp-server/` | Standalone MCP server binary |
| `codex-execpolicy` | `execpolicy/` | Execution policy rules |
| `codex-features` | `features/` | Feature flags / rollout |
| `codex-model-provider-info` | `model-provider-info/` | Model metadata/tiers |
| `codex-thread-store` | `thread-store/` | Thread persistence |
| `codex-otel` | `otel/` | OpenTelemetry tracing |

### The `codex-core` Rule

`codex-core` has grown too large. **Resist adding code to it.** Before placing anything in `core/`:
1. Check if an existing non-core crate fits.
2. Consider introducing a new crate for the concept.

Reviewers should push back on PRs that unnecessarily expand `codex-core`.

### Rust Toolchain

- Version pinned in `codex-rs/rust-toolchain.toml` (currently `1.93.0`).
- Required components: `clippy`, `rustfmt`, `rust-src`.

---

## Development Workflow

### Prerequisites

```bash
# Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
rustup component add rustfmt clippy

# Helper tools
cargo install just
cargo install --locked cargo-nextest  # optional, speeds up `just test`
```

### Common Commands (run from `codex-rs/`)

| Command | What it does |
|---|---|
| `just fmt` | Format all Rust code (run after every change) |
| `just fix -p <crate>` | Run clippy --fix on a specific crate |
| `just fix` | Run clippy --fix workspace-wide (slow) |
| `just test` | Run full test suite via cargo-nextest |
| `cargo test -p codex-<name>` | Run tests for a single crate |
| `just write-config-schema` | Regenerate `core/config.schema.json` |
| `just write-app-server-schema` | Regenerate app-server protocol fixtures |
| `just write-hooks-schema` | Regenerate hooks JSON schema fixtures |
| `just argument-comment-lint` | Run Bazel-based argument comment linter |
| `just bazel-lock-update` | Refresh `MODULE.bazel.lock` after dep changes |
| `just bazel-lock-check` | Verify lockfile isn't drifted |

### After Making Changes

1. Run `just fmt` (no approval needed).
2. Run `just fix -p <crate-you-touched>` for the specific crate.
3. Run `cargo test -p codex-<crate>` for the crate you changed.
4. If you changed `core/`, `protocol/`, or other shared crates, ask before running `just test` (full suite).
5. If you changed `Cargo.toml`/`Cargo.lock`, run `just bazel-lock-update` and commit the lockfile.
6. If you changed `ConfigToml` or nested config types, run `just write-config-schema`.
7. If you changed app-server protocol shapes, run `just write-app-server-schema`.

**Never kill long-running `cargo` or `just` commands by PID** — Rust's file locking makes them appear slow but they will finish.

---

## Rust Coding Conventions

### Format and Style

- Use `format!` with inlined variables: `format!("{x}")` not `format!("{}", x)`.
- Collapse nested `if` statements (clippy `collapsible_if`).
- Use method references over redundant closures (`|x| x.foo()` → `Foo::foo`).
- Make `match` exhaustive — avoid wildcard `_` arms when possible.
- Prefer `enum`, named methods, or newtypes over `bool`/ambiguous `Option` parameters that produce unreadable callsites like `foo(false)`.

### Argument Comment Convention

When an API can't be changed and you must pass opaque literals (`None`, `true`, `false`, numbers) by position, add an `/*param_name*/` comment:

```rust
do_thing(/*dry_run=*/ false, /*retries=*/ 3);
```

- Run `just argument-comment-lint` to verify locally (CI checks all platforms).
- Do **not** add these comments for string/char literals.

### Async Traits

Do **not** use `#[async_trait]` or `#[allow(async_fn_in_trait)]`. Use native RPITIT:

```rust
// Preferred trait shape
fn process(&self, input: Input) -> impl std::future::Future<Output = Result<Output>> + Send;

// Implementations may use async fn
async fn process(&self, input: Input) -> Result<Output> { ... }
```

### Module Size

- Target modules under 500 LoC (excluding tests).
- If a file exceeds ~800 LoC, add new functionality in a new module.
- High-touch files to watch: `tui/src/app.rs`, `tui/src/chatwidget.rs`, `tui/src/bottom_pane/mod.rs`.
- Move related tests and docs toward the new implementation when extracting.

### Other Rules

- Newly added traits must have doc comments explaining their role.
- Prefer private modules with explicitly exported public API.
- Do not create small helper methods referenced only once.
- When writing tests: compare entire objects, not individual fields.
- Avoid mutating process environment in tests — pass flags/dependencies from above.
- Use `pretty_assertions::assert_eq!` in tests for clearer diffs.

---

## TUI Conventions (`codex-tui`)

### Color / Style Guide

Follow `codex-rs/tui/styles.md`:

| Use case | Style |
|---|---|
| Headers | `bold` |
| Primary text | default (no color) |
| Secondary / hints | `dim` |
| User input tips, selection, status | `cyan` |
| Success / additions | `green` |
| Errors / failures / deletions | `red` |
| Codex-branded elements | `magenta` |

**Avoid:** `Rgb`, `Indexed`, `white`, `black`, `blue`, `yellow` (enforced by `clippy.toml`).

### Ratatui Stylize API

- Basic spans: `"text".into()`
- Styled spans: `"text".red()`, `"text".dim()`, `"text".cyan().underlined()`
- Build lines: `vec![span1, span2].into()` when target type is obvious; `Line::from(vec![...])` otherwise.
- Use `Span::styled` only when the style is computed at runtime.
- Don't refactor between equivalent forms without a functional gain — follow file-local conventions.

### Snapshot Tests

When UI or text output changes intentionally:

```bash
cargo test -p codex-tui          # generates *.snap.new files
cargo insta pending-snapshots -p codex-tui
cargo insta accept -p codex-tui  # only if accepting all changes
```

---

## App-Server API Conventions

Active API development happens in **v2 only**. Do not add new surface area to v1.

### Naming

- Request payloads: `*Params`
- Responses: `*Response`
- Notifications: `*Notification`
- RPC methods: `<resource>/<method>` with singular `<resource>` (e.g., `thread/read`, `app/list`)

### Serialization

- Wire format: `camelCase` via `#[serde(rename_all = "camelCase")]`
  - Exception: config RPC payloads use `snake_case` to mirror `config.toml` keys.
- TypeScript export: always set `#[ts(export_to = "v2/")]` on v2 types.
- Keep Rust and TS renames aligned — if `#[serde(rename = "...")]`, also add `#[ts(rename = "...")]`.
- Discriminated unions: `#[serde(tag = "type")]` + `#[ts(tag = "type")]`.
- Never use `#[serde(skip_serializing_if = "Option::is_none")]` on v2 payload fields (with one specific exception for no-param requests).
- ID fields: plain `String` at the boundary; parse internally as needed.
- Timestamps: `i64` Unix seconds, named `*_at`.

### Optional Fields (`*Params` only)

- Every optional field: `#[ts(optional = nullable)]`
- Optional collections (`Vec`, `HashMap`): use `Option<...>` + `#[ts(optional = nullable)]` — do **not** use `#[serde(default)]`.
- Boolean fields where omission means `false`: `#[serde(default, skip_serializing_if = "std::ops::Not::not")] pub field: bool`.

### Pagination

New list methods must implement cursor pagination:
- Request: `cursor: Option<String>`, `limit: Option<u32>`
- Response: `data: Vec<...>`, `next_cursor: Option<String>`

### Schema Regeneration

After changing protocol shapes:
```bash
just write-app-server-schema
just write-app-server-schema --experimental  # when experimental fields changed
cargo test -p codex-app-server-protocol
```

---

## Integration Testing (`codex-core`)

Use `core_test_support::responses` helpers for end-to-end tests:

```rust
let mock = responses::mount_sse_once(&server, responses::sse(vec![
    responses::ev_response_created("resp-1"),
    responses::ev_function_call(call_id, "shell", &serde_json::to_string(&args)?),
    responses::ev_completed("resp-1"),
])).await;

codex.submit(Op::UserTurn { ... }).await?;
let request = mock.single_request();
// assert using request.function_call_output(call_id) or request.input() etc.
```

- Prefer `mount_sse_once` over `mount_sse_once_match` or `mount_sse_sequence`.
- Prefer `wait_for_event` over `wait_for_event_with_timeout`.
- Use `ResponseMock::single_request()` for single-POST tests; `ResponseMock::requests()` to inspect all captures.

### Spawning Binaries in Tests

- Use `codex_utils_cargo_bin::cargo_bin("...")` — not `assert_cmd::Command::cargo_bin` or `escargot`.
- Locate test resources with `codex_utils_cargo_bin::find_resource!` — not `env!("CARGO_MANIFEST_DIR")`.

---

## Sandbox & Environment Constraints

- `CODEX_SANDBOX_NETWORK_DISABLED=1` is set whenever the `shell` tool is used in the sandbox. **Never add or modify** code touching `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR` or `CODEX_SANDBOX_ENV_VAR`.
- Tests that detect `CODEX_SANDBOX_NETWORK_DISABLED` are intentionally exiting early — do not remove those guards.
- Seatbelt spawn (`/usr/bin/sandbox-exec`) sets `CODEX_SANDBOX=seatbelt` on the child. Integration tests that spawn Seatbelt themselves detect this and skip.

---

## MCP (Model Context Protocol)

- For mutations to tools and tool calls, prefer `codex-rs/codex-mcp/src/mcp_connection_manager.rs`.
- Minimize the footprint of MCP changes; leverage existing abstractions rather than plumbing through multiple function call levels.

---

## Bazel Build

Bazel is used for hermetic builds, cross-platform CI, and release artifacts.

| Command | What it does |
|---|---|
| `just bazel-test` | Run all Bazel tests |
| `just bazel-clippy` | Run Clippy via Bazel |
| `just bazel-lock-update` | Update `MODULE.bazel.lock` |
| `just bazel-lock-check` | Verify lockfile consistency |
| `just build-for-release` | Build release binaries (requires remote exec) |

**Bazel + `include_str!`**: if you add `include_str!`, `include_bytes!`, `sqlx::migrate!`, or other build-time file reads, update the crate's `BUILD.bazel` (`compile_data`, `build_script_data`, or test data attributes) — Bazel does not automatically expose source files to compile-time access.

---

## JavaScript / pnpm

The `codex-cli/` package (`@openai/codex`) is a thin JS wrapper that ships the Rust binary.

Root-level scripts (run from repo root):
```bash
pnpm format        # check prettier
pnpm format:fix    # auto-fix prettier
pnpm write-hooks-schema  # regenerate hooks schema
```

Node ≥ 22 and pnpm ≥ 10.33.0 are required.

---

## SDK (`sdk/`)

| Directory | Language | Role |
|---|---|---|
| `sdk/python/` | Python | Python SDK for Codex agent API |
| `sdk/typescript/` | TypeScript | TypeScript SDK for Codex agent API |
| `sdk/python-runtime/` | Python | Runtime support library |

---

## Contribution Rules

**External contributions are by invitation only.** Do not open unsolicited PRs — they will be closed without review. Report bugs and propose features via Issues instead.

If invited to contribute:
1. Create a topic branch from `main` (e.g., `feat/my-feature`).
2. Keep changes focused — separate PRs for unrelated fixes.
3. Run `just fmt`, `just fix -p <crate>`, and relevant tests before opening.
4. Ensure branch is up to date with `main` and merge conflicts are resolved.
5. Sign the CLA (bot-assisted in the PR).

### Pull Request Guidelines

- Fill in the PR template: **What? Why? How?**
- Link the related issue.
- Mark **Ready for review** only when the PR is merge-ready.
- CI checks argument-comment-lint across all three platforms — run locally first with `just argument-comment-lint`.

### Model Metadata Changes

When updating model catalogs or metadata:
- Set `input_modalities` explicitly for models that do not support images.
- Keep compatibility defaults in mind (omitted `input_modalities` implies text + image support).
- Update all client surfaces that consume the capability signal.
- Add/update tests covering unsupported-image behavior.

---

## Logging & Observability

- TUI default log level: `codex_core=info,codex_tui=info,codex_rmcp_client=info`
- TUI logs written to `~/.codex/log/codex-tui.log`; override per-run with `-c log_dir=<path>`.
- `codex exec` (non-interactive) defaults to `RUST_LOG=error`; messages print inline.
- Configure via standard `RUST_LOG` env var syntax.

---

## Security

Report vulnerabilities to **security@openai.com**. Do not open public issues for security findings.

---

## Quick Reference: Where Does New Code Belong?

### Sybil (Intelligence) Layer

| Change type | Target |
|---|---|
| New reasoning / agent logic | New crate (avoid `codex-core`); or `/core/skills/` as a skill |
| New skill capability | `/core/skills/<skill-name>/` following the skill contract |
| Skill orchestration / chaining | `codex-skills`, `codex-core-skills`, or `callstack-agents` skill |
| Context / memory management | `context-engine` skill or `codex-thread-store` |
| Hook system | `codex-hooks` |
| Model metadata | `codex-model-provider-info` |

### Aurora (Infrastructure) Layer

| Change type | Target |
|---|---|
| TUI feature | `codex-tui` |
| New CLI flag | `codex-cli` (Rust crate) |
| App-server API (v2) | `codex-app-server` + `codex-app-server-protocol` |
| Execution / process management | `codex-exec-server` or `codex-execpolicy` |
| Config schema | `codex-config` (then run `just write-config-schema`) |
| MCP tool management | `codex-mcp` |
| Cloud / infrastructure | `cloud-tasks`, `cloud-requirements` |
| Auth / identity | `codex-agent-identity`, `codex-login` |
| JS wrapper / npm package | `codex-cli/` (JavaScript) |
