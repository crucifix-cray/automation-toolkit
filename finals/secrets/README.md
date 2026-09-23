# Encrypted GitHub PAT for Holy farm workers (ciphertext only).

Create / refresh:
```bash
HOLY_SECRET_KEY='…' GITHUB_TOKEN='ghp_…' \
  python3 -m src.utils.secret_box encrypt --out finals/secrets/gh_token.enc
```

Runtime (Railway sandbox / cell): inject **only** `HOLY_SECRET_KEY`
(see local `holy_secret_key.local` — gitignored, never commit).

Optional: `GH_TOKEN_ENC=<ciphertext>` instead of the file.
Disable push: `GH_PUSH=0`.
