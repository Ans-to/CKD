# Using this from a private GitHub repository

Two separate things: (1) getting the code into Colab, (2) keeping the repository private without
leaking credentials. Do them in this order.

## 1 · Put the code in a private repo (once, from any browser)

1. On GitHub: **New repository** → name it, choose **Private**, create it (no README needed if you
   already have this one).
2. Upload without a terminal: on the empty repo page click **uploading an existing file**, then drag
   the project ZIP contents in, or upload the ZIP and unzip it in Colab later.
3. Or with git, if you have a shell:

```bash
git init && git add . && git commit -m "CKD video studio"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Nothing in this repository needs a secret. `.gitignore` already excludes `projects/`, `_cache/`,
`models/`, `*.wav` and Python caches, so rendered media and voice models never get committed.

## 2 · Get a private repo into Colab — three options, safest first

### Option A — Colab's built-in GitHub support (recommended for a private repo)

1. In Colab: **File ▸ Open notebook ▸ GitHub**.
2. Tick **Include private repos**, authorise Colab's GitHub app for that repository.
3. Open `notebooks/CKD_Video_Studio.ipynb` directly from the repo.

This uses OAuth through Colab; no token is typed anywhere, and nothing is stored in the notebook.
The notebook's cell 0 then just does `%cd /content/CKD` **if** you also clone, or you can run it
straight from the Drive-backed copy Colab makes.

### Option B — a fine-grained token in a *hidden* Colab form field

Use this only if Option A is unavailable. A fine-grained token scoped to **one repository**,
**read-only contents**, expiring in 7 days:

```python
from getpass import getpass
token = getpass("GitHub token (not stored): ")          # ⚠️ input is not echoed, not saved
user  = "<your-github-username>"
repo  = "<your-repo>"
!git clone https://{user}:{token}@github.com/{user}/{repo}.git /content/CKD
```

Then **immediately** run a cleanup cell so the token is not left in the shell history or in
`.git/config` of a copied project:

```python
!git -C /content/CKD remote set-url origin https://github.com/{user}/{repo}.git
del token
```

Never paste a token into a notebook cell's source, a commit, a screenshot, or a chat message.
If a token is ever exposed, revoke it in GitHub settings immediately — a revoked token cannot be
"cleaned up" after the fact.

### Option C — ZIP upload (works for private repos, no auth at all)

1. Download the repository ZIP from GitHub (private repos allow this while signed in).
2. In Colab: the **folder icon** in the left sidebar ▸ upload ▸ select the ZIP.
3. Run:

```python
!unzip -q /content/CKD.zip -d /content
%cd /content/CKD
```

Uploading a ZIP is the simplest path from a phone, and involves no credentials in the runtime at all.

## 3 · Keeping it private

- Do not fork a public copy "just to try it" — a fork of a public repo is public.
- Do not enable GitHub Pages or publish releases with the source if you want it private.
- `samples/*.mp4` contains your rendered output; keep it or delete it, but remember it will be in the
  repo history once committed.
- If you later make the repo public, scan the history first:

```bash
git log --all -p | grep -nE "(ghp_|github_pat_|AKIA|BEGIN [A-Z ]*PRIVATE KEY)" || echo "no obvious secrets"
```

- The tests include `tests/test_security.py`, which fails if a committed file contains something that
  looks like a credential.

## 4 · What the repo will never contain

- API keys, tokens, or account identifiers.
- Voice model binaries (they are downloaded into `~/.cache/ckd` at run time).
- Rendered projects (`projects/`), which can be gigabytes.

That is also what `tools/make_zip.py` leaves out when it builds the portable ZIP.
