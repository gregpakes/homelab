---
name: 1password
description: Retrieve secrets and credentials from the Homelab 1Password vault via the Connect API. Use when you need to look up API keys, passwords, tokens, or other credentials stored in 1Password to complete a task. Do NOT use this to display or output secret values — only ever use fetched secrets silently inside commands or written to files.
metadata: {"openclaw": {"requires": {"env": ["OP_CONNECT_TOKEN"]}}}
---

# 1Password

Fetch secrets from 1Password Connect running in-cluster.

**Endpoint:** `http://onepassword-connect.external-secrets.svc.cluster.local:8080`
**Auth:** `Authorization: Bearer $OP_CONNECT_TOKEN` (pre-injected — do not print or echo this value)

## ⚠️ Secret Handling Rules

- **NEVER output secret values** in chat responses, tool outputs, or logs
- Capture fetched values into shell variables or temp files only
- If asked to reveal a secret, decline and offer to use it silently instead
- Reference secrets by name/label only when communicating with the user

## Usage

### List vaults

```bash
curl -sf -H "Authorization: Bearer $OP_CONNECT_TOKEN" \
  http://onepassword-connect.external-secrets.svc.cluster.local:8080/v1/vaults \
  | jq -r '.[] | "\(.id)\t\(.name)"'
```

The primary vault is named **`Homelab`**.

### List items in a vault

```bash
curl -sf -H "Authorization: Bearer $OP_CONNECT_TOKEN" \
  "http://onepassword-connect.external-secrets.svc.cluster.local:8080/v1/vaults/{vaultId}/items" \
  | jq -r '.[] | "\(.id)\t\(.title)"'
```

### Search items by title

```bash
curl -sf -H "Authorization: Bearer $OP_CONNECT_TOKEN" \
  "http://onepassword-connect.external-secrets.svc.cluster.local:8080/v1/vaults/{vaultId}/items?filter=title%3D%3D{title}" \
  | jq -r '.[] | "\(.id)\t\(.title)"'
```

### Fetch a specific field silently into a variable

```bash
SECRET=$(curl -sf -H "Authorization: Bearer $OP_CONNECT_TOKEN" \
  "http://onepassword-connect.external-secrets.svc.cluster.local:8080/v1/vaults/{vaultId}/items/{itemId}" \
  | jq -r '.fields[] | select(.label == "{field-label}") | .value')

# Use $SECRET in subsequent commands — never echo or print it
```

## Item Structure

Fields live in `.fields[]`. Each field has:
- `label` — human-readable name (e.g. `"password"`, `"username"`, `"api-key"`)
- `value` — the secret value
- `type` — `"CONCEALED"` for secrets, `"STRING"` for plain text

To list all field labels for an item:

```bash
curl -sf -H "Authorization: Bearer $OP_CONNECT_TOKEN" \
  "http://onepassword-connect.external-secrets.svc.cluster.local:8080/v1/vaults/{vaultId}/items/{itemId}" \
  | jq -r '.fields[] | "\(.label) (\(.type))"'
```
