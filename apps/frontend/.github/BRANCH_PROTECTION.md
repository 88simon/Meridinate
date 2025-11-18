# Branch Protection Recommendations - Frontend

This document outlines recommended branch protection rules for Meridinate Web (frontend) to maintain code quality and security.

## Overview

Branch protection rules prevent direct pushes to critical branches and ensure all changes go through proper review and automated checks before merging.

## Recommended Settings for `main` Branch

Navigate to: **Settings → Branches → Branch protection rules → Add rule**

### Basic Settings

- **Branch name pattern:** `main`
- **Lock branch:** ❌ (not recommended for active development)
- **Do not allow bypassing the above settings:** ✅ (enforces rules for everyone, including admins)

### Required Reviews

- ✅ **Require a pull request before merging**
  - **Required approvals:** 1 (increase to 2 for stricter review)
  - ✅ **Dismiss stale pull request approvals when new commits are pushed**
  - ❌ **Require review from Code Owners** (optional - enable if you have a CODEOWNERS file)
  - ❌ **Restrict who can dismiss pull request reviews** (optional)
  - ✅ **Allow specified actors to bypass required pull requests** (optional - for hotfixes)
  - ❌ **Require approval of the most recent reviewable push**

### Status Checks

- ✅ **Require status checks to pass before merging**

  - ✅ **Require branches to be up to date before merging** (ensures no merge conflicts)

  **Required status checks:**

  - `Lint & Format` (from CI workflow)
  - `TypeScript` (from CI workflow)
  - `Build` (from CI workflow)
  - `Analyze JavaScript/TypeScript Code` (from CodeQL workflow)
  - `Build Docker Image` (from Docker Build workflow - optional)

### Additional Settings

- ✅ **Require conversation resolution before merging** (all review comments must be resolved)
- ✅ **Require signed commits** (optional but highly recommended for security)
- ❌ **Require linear history** (optional - prevents merge commits, forces squash or rebase)
- ❌ **Require merge queue** (optional - for high-traffic repos)
- ✅ **Require deployments to succeed before merging** (optional - if you have deployment workflows)

### Force Push & Deletion Protection

- ✅ **Do not allow force pushes** (prevents rewriting history)
- ✅ **Do not allow deletions** (prevents accidental branch deletion)

### Rules Applied to Everyone

- ✅ **Include administrators** (admins must follow the same rules)

## Recommended Settings for `develop` Branch

Use similar settings to `main` but with slightly relaxed requirements:

- **Branch name pattern:** `develop`
- ✅ **Require a pull request before merging**
  - **Required approvals:** 1
- ✅ **Require status checks to pass before merging**
  - Same status checks as `main`
- ✅ **Require conversation resolution before merging**
- ✅ **Do not allow force pushes** (except for specific users/teams)
- ✅ **Do not allow deletions**

## Feature Branch Protection (Optional)

For feature branches, you can use a wildcard pattern:

- **Branch name pattern:** `feature/*`
- ✅ **Require status checks to pass before merging**
  - Only require critical checks (linting, type-check, build)
- ❌ Do not require pull request reviews (since feature branches typically merge to `develop`)

## Implementing Branch Protection via GitHub CLI

You can also configure branch protection rules using GitHub CLI:

```bash
# Install GitHub CLI if not already installed
# https://cli.github.com/

# Authenticate
gh auth login

# Set branch protection for main
gh api repos/88simon/gun_del_sol_web/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["Lint & Format","TypeScript","Build","Analyze JavaScript/TypeScript Code","Build Docker Image"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field restrictions=null
```

## CODEOWNERS File (Optional)

Create a `.github/CODEOWNERS` file to automatically request reviews from specific people or teams:

```
# Default owner for everything in the repo
* @88simon

# Frontend source code
/src/ @88simon @frontend-team

# CI/CD workflows
/.github/workflows/ @88simon @devops-team

# Docker configuration
/Dockerfile @88simon @devops-team
/docker-compose.yml @88simon @devops-team

# Configuration files
/*.config.* @88simon
/package.json @88simon
/pnpm-lock.yaml @88simon
```

## Testing Branch Protection

After setting up branch protection:

1. **Test direct push prevention:**

   ```bash
   git checkout main
   git commit --allow-empty -m "test"
   git push  # Should fail with protection error
   ```

2. **Test PR workflow:**

   ```bash
   git checkout -b test-branch
   # Make changes
   git add .
   git commit -m "test changes"
   git push -u origin test-branch
   # Create PR via GitHub UI or gh CLI
   gh pr create --base main --head test-branch
   ```

3. **Verify status checks run:**
   - Check that all required workflows execute
   - Ensure merge button is disabled until checks pass

## Rollback Plan

If branch protection causes issues:

1. Go to **Settings → Branches**
2. Find the protection rule
3. Click **Edit** or **Delete**
4. Temporarily disable specific requirements
5. Document the issue and fix underlying problems
6. Re-enable protection when resolved

## Monitoring and Maintenance

- **Review protection rules quarterly** to ensure they match your workflow
- **Update required status checks** when adding/removing CI workflows
- **Monitor failed status checks** and address common failures
- **Educate team members** on PR workflow and protection rules

## Additional Resources

- [GitHub Branch Protection Documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub CLI Branch Protection](https://cli.github.com/manual/gh_api)
- [Code Owners Documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)

---

**Last Updated:** 2025-11-11
**Maintained by:** Meridinate Team
