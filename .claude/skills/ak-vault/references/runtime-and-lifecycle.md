# Runtime use and lifecycle

## Use a secret in a command

On runtimes that run AgentKit's core PreToolUse hooks, a `${secret:NAME}`
reference is replaced with the stored value just before the tool runs, and
only in three fields: a shell command, a PowerShell command, and a web-fetch
URL. Anywhere else (file contents, prompts, commit messages) it stays literal
text. Confirm the current runtime supports it before relying on it (AgentKit's
runtime support matrix tracks this); Pi, for example, does not resolve
references.

```text
curl -H "Authorization: Bearer ${secret:STRIPE_API_KEY}" https://api.stripe.com/v1/balance
```

What blocks the call instead of running it:

- the ref does not exist, or its name is not `[A-Za-z0-9][A-Za-z0-9_.-]*`;
- in a shell field, the value contains whitespace, quotes, or shell
  metacharacters (PowerShell refuses a few more), because substituting it would
  change the command. Store such a value as a file and point the tool at it, or
  have the program read it from the vault-backed environment instead;
- no grant covers this agent, project, and purpose (`resolve` exits 8). The
  request waits for the user: tell them to run `ak secrets approve` in their own
  terminal, choosing once, a TTL, persist, or deny. Then retry the same call.

An agent cannot grant or approve: `ak secrets grant` and `ak secrets approve`
both exit 6 when a coding agent sits above the process. Do not retry them or
look for another route.

Never write a reference into text that a hook would resolve by accident, such
as a heredoc that builds documentation. Author that text with the file-editing
tools.

## Grants and trust (user-run)

| Command | Purpose |
|---|---|
| `ak secrets grants --json` | List current allows and blocks. |
| `ak secrets grant <REF> --agent sha256:<hex> [--ttl 30d \| --persist \| --block] [--allow-host <host>]` | Pre-authorize or block an agent. |
| `ak secrets revoke <REF> --agent sha256:<hex>` | Remove one grant. |
| `ak secrets revoke --agent sha256:<hex> --all` | Panic button: revoke every grant that agent holds. |
| `ak secrets trust <adapter> [--refresh]` | Show or re-pin a runtime binary after an upgrade. |

## Rotate

```bash
printf '%s' "$new_value" | ak secrets rotate <REF> --value=- --no-interactive
ak secrets sync now --json
```

Run the pipe from a script, as in [store-and-sync.md](store-and-sync.md).
`rotate` requires the ref to exist and keeps its profile. Rotate at the
provider first, store the new value, sync, then revoke the old credential at the
provider; report each step's outcome, never the value.

After a suspected leak: `ak secrets revoke --agent sha256:<hex> --all` (user),
rotate at the provider, `ak secrets rotate`, then `ak secrets audit --secret <REF>`
to see who used it.

## Delete

`ak secrets delete <REF>` permanently removes the value and its metadata on
this device; with sync enabled, the next `sync now` carries the deletion to the
other devices. Confirm with the user first; it is irreversible.

## Audit

```bash
ak secrets audit --secret <REF> --json
ak secrets audit --decision deny --since 24h --json
```

## Export and backup

```bash
ak secrets export --json                             # metadata inventory, no values
ak secrets export --include-values --out backup.age  # values, age-encrypted, mode 0600
```

`--include-values` requires an `--out` ending in `.age` and prompts; it is a
user-run backup. A file-backend vault can be made recoverable with
`ak secrets recovery init --label <label>` and extra keys via
`ak secrets recovery add`; `ak secrets recovery list` shows labels and
fingerprints, never keys.
