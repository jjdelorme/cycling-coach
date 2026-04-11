You are managing a release for the cycling-coach project. The user has invoked `/release` with an argument: `beta`, `patch`, or `minor`.

Parse the argument from `$ARGUMENTS`. If no argument is provided or it's not one of `beta`, `patch`, `minor`, explain the three options and stop — do not proceed.

## Step 1 — Determine the current version

Run `git describe --tags --abbrev=0` to get the latest tag (e.g. `v1.7.3` or `v1.7.4-beta`).
Parse it into `major`, `minor`, `patch`, and whether it has a `-beta` suffix.

Also run `git tag --points-at HEAD` to check if the current HEAD already has a beta tag on it.

## Step 2 — Compute the next version

**`/release beta`**
- Always bumps patch by 1, adds `-beta` suffix.
- If HEAD already has a `-beta` tag (e.g. `v1.7.4-beta`), stop and say: "HEAD is already tagged `{tag}` and the build should have triggered when this commit was pushed. If you need to re-trigger the test deployment, push an empty commit or manually submit: `gcloud builds submit . --config=cloudbuild-test.yaml --substitutions=BRANCH_NAME={branch},SHORT_SHA={short_sha} --project=jasondel-cloudrun10`"
- Example: `v1.7.3` → `v1.7.4-beta`

**`/release patch`**
- If the most recent tag is a `-beta` AND HEAD has that beta tag: **promote** — strip `-beta`, keep the same version number. No version bump.
  - Example: `v1.7.4-beta` → `v1.7.4` (same commit, new clean tag)
- Otherwise: bump patch by 1, no suffix.
  - Example: `v1.7.3` → `v1.7.4`

**`/release minor`**
- If the most recent tag is a `-beta` AND HEAD has that beta tag: **promote with minor bump** — strip `-beta`, bump minor, reset patch to 0.
  - Example: `v1.7.4-beta` → `v1.8.0`
- Otherwise: bump minor by 1, reset patch to 0, no suffix.
  - Example: `v1.7.3` → `v1.8.0`

## Step 2.5 — Check for uncommitted migration files

Run `git status --short migrations/` to check whether any files under `migrations/` are new or modified but not yet committed.

If any migration files are untracked (`??`) or modified (`M`), **stop** and tell the user:

> "There are uncommitted migration files: {list}. Stage and commit them before releasing — Cloud Build will apply pending migrations on deploy, but they must be in the tagged commit."

Only proceed to Step 3 if all migration files are clean (committed or the directory doesn't exist yet).

## Step 3 — Confirm with the user

Before making any changes, state clearly:
- The current tag
- The new version that will be created
- Whether this is a promotion (beta → prod) or a fresh release
- What branch you are on

Ask: "Proceed with this release? (yes/no)"

Wait for confirmation. If the user says anything other than yes/y/proceed, stop.

## Step 4 — Update CHANGELOG.md

Read the current CHANGELOG.md. Insert a new section immediately after the `# Changelog` header line (and any blank lines following it), before the first existing `## [` entry.

**For beta releases**, the section header is:
```
## [vX.Y.Z-beta] - YYYY-MM-DD
```

**For prod releases (fresh or promotion)**, consolidate all beta entries since the last prod release into a single clean entry:

1. Find the last prod release section in CHANGELOG.md (the most recent `## [vX.Y.Z]` header that has no `-beta` suffix).
2. Collect every `## [vX.Y.Z-beta]` section that appears *above* that last prod entry (i.e., all betas released since then). Gather all their bullet points / notes.
3. **Remove** all those individual beta sections from CHANGELOG.md.
4. Insert one new consolidated prod section immediately after the `# Changelog` header:

```
## [vX.Y.Z] - YYYY-MM-DD

{consolidated bullet points from all collected beta sections, de-duplicated and lightly edited for clarity}
```

If there are no meaningful beta notes (e.g., only "Promoted from ..." lines), summarize what's in the release based on recent commits since the last prod tag: `git log {last_prod_tag}..HEAD --oneline`.

Use today's date (from the system context) in `YYYY-MM-DD` format.

## Step 5 — Commit, tag, and push

Run these commands in order. Do not skip any. Do not use `--no-verify`.

```bash
# Stage only the changelog
git add CHANGELOG.md

# Commit
git commit -m "chore(release): v{NEW_VERSION}"

# Annotated tag
git tag -a v{NEW_VERSION} -m "Release v{NEW_VERSION}"
```

**For beta releases** (non-main branch) — push branch and tag in a single atomic push. Cloud Build 2nd gen only fetches refs from the triggering push event; a separately-pushed tag is NOT visible to `git describe`. Pushing both together ensures the tag is present when Cloud Build runs:
```bash
git push origin HEAD v{NEW_VERSION}
```

**For prod releases** (on `main`) — push commit and tag together to avoid a race condition with the tag guard in `cloudbuild.yaml`:
```bash
git push origin main --tags
```

## Step 6 — Report result

After all commands succeed, report:
- The new tag created
- The git push output (branch + tag)

**For beta releases** (non-main branch): the `cycling-coach-test-branches` Cloud Build trigger fires automatically on the branch push, runs `cloudbuild-test.yaml`, and deploys to the `test` Cloud Run tag at `https://test---cycling-coach-kk35opvuza-uc.a.run.app`.

**For prod releases** (`patch` or `minor` on `main`): the `cycling-coach-main-trigger` Cloud Build trigger fires automatically on the main branch push, runs `cloudbuild.yaml`, and deploys to production. Note: the prod build requires an exact tag on HEAD — push the branch and tag together (`git push origin main --tags`) to avoid a race condition with the tag guard. Cloud Build runs `python -m server.migrate` as a pre-deploy step before routing any traffic to the new revision — pending migrations are applied automatically.

If any step fails, stop immediately, show the error, and do not proceed to the next step.

## Important guardrails

- **Never push to main from a feature branch.** If the user is on a branch other than `main` and runs `/release patch` or `/release minor` (non-beta), warn them: "You are on branch `{branch}`, not main. Prod releases should be tagged on main. Continue anyway? (yes/no)"
- **Never force-push or amend published commits.**
- **Never tag the same version twice.** If the computed tag already exists, stop and report it.
- Check for an existing tag before proceeding: `git tag -l v{NEW_VERSION}`
