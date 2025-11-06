# Release Process

This document describes the release process for Alloy Dynamic Processors, including versioning, building, testing, and publishing releases.

## Table of Contents

- [Versioning](#versioning)
- [Release Types](#release-types)
- [Pre-Release Checklist](#pre-release-checklist)
- [Release Steps](#release-steps)
- [Post-Release Tasks](#post-release-tasks)
- [Rollback Procedure](#rollback-procedure)
- [Hotfix Process](#hotfix-process)

## Versioning

We follow [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR** version: Incompatible API changes
- **MINOR** version: Backwards-compatible functionality additions
- **PATCH** version: Backwards-compatible bug fixes

### Version Format

```
v<MAJOR>.<MINOR>.<PATCH>[-<PRERELEASE>]

Examples:
v1.0.0          # Stable release
v1.1.0-rc.1     # Release candidate
v1.1.0-beta.1   # Beta release
v1.1.0-alpha.1  # Alpha release
```

## Release Types

### Stable Release (vX.Y.Z)
- Production-ready
- Fully tested
- Complete documentation
- Security scanned
- Signed images

### Release Candidate (vX.Y.Z-rc.N)
- Feature complete
- Undergoing final testing
- Documentation nearly complete
- For staging environments

### Beta Release (vX.Y.Z-beta.N)
- Major features implemented
- May have known issues
- For testing environments

### Alpha Release (vX.Y.Z-alpha.N)
- Early development
- Experimental features
- For development environments only

## Pre-Release Checklist

### Code Quality
- [ ] All tests passing (`make test`)
- [ ] Code coverage ≥80%
- [ ] No critical/high security vulnerabilities
- [ ] Pre-commit hooks passing
- [ ] Linting clean (`make lint`)
- [ ] Code formatted (`make fmt`)

### Documentation
- [ ] CHANGELOG.md updated with all changes
- [ ] README.md reflects current features
- [ ] All docs/*.md files updated
- [ ] API documentation current
- [ ] Migration guide updated (if needed)
- [ ] Breaking changes documented

### Configuration
- [ ] .env.example updated with new variables
- [ ] Helm values.yaml reflects defaults
- [ ] All configuration options documented
- [ ] Docker Compose tested locally

### Testing
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] End-to-end tests passing (`make test-e2e`)
- [ ] Load testing completed (if applicable)
- [ ] Smoke tests in staging

### Security
- [ ] No secrets in code
- [ ] Dependencies updated
- [ ] Security scan clean
- [ ] SBOM generation verified
- [ ] Image signing tested

### Infrastructure
- [ ] Helm chart lints (`make helm-lint`)
- [ ] Kubernetes manifests valid
- [ ] Docker images build successfully
- [ ] Multi-arch builds tested

## Release Steps

### 1. Prepare Release Branch

```bash
# Create release branch from main
git checkout main
git pull origin main
git checkout -b release/v1.0.0

# Update version numbers
# Edit: alloy/helm/alloy-dynamic-processors/Chart.yaml
# Edit: alloy/processors/ai_sorter/ai_sorter.py (version string)
```

### 2. Update CHANGELOG.md

```markdown
## [1.0.0] - 2025-01-15

### Added
- Feature A
- Feature B

### Changed
- Update X

### Fixed
- Bug Y
```

### 3. Update Documentation

```bash
# Review and update
docs/overview.md
docs/ARCHITECTURE.md
docs/DEPLOYMENT_GUIDE.md
README.md
```

### 4. Run Full Test Suite

```bash
# Lint and format
make fmt
make lint

# Run tests
make test
make test-coverage

# Build images
make build

# Security scan
make scan

# End-to-end test
make up
make test-e2e
make down
```

### 5. Create Pull Request

```bash
git add -A
git commit -m "chore: prepare release v1.0.0"
git push origin release/v1.0.0

# Create PR to main
# Title: "Release v1.0.0"
# Use PR template, mark all items
```

### 6. Merge and Tag

```bash
# After PR approval and merge
git checkout main
git pull origin main

# Create annotated tag
git tag -a v1.0.0 -m "Release v1.0.0

See CHANGELOG.md for details."

# Push tag (triggers release workflow)
git push origin v1.0.0
```

### 7. Monitor Release Workflow

GitHub Actions will automatically:

1. **Build multi-arch images** (amd64, arm64)
2. **Run security scans** (Trivy)
3. **Generate SBOM** (syft)
4. **Sign images** (cosign keyless OIDC)
5. **Push to GHCR** (ghcr.io/chaoskyle/alloy-dynamic-processors)
6. **Create GitHub Release** with notes
7. **Attach artifacts** (SBOM, SARIF reports)

Monitor at: `https://github.com/ChaosKyle/alloy-dynamic-processors/actions`

### 8. Verify Release

```bash
# Verify images published
docker pull ghcr.io/chaoskyle/alloy-dynamic-processors/ai-sorter:v1.0.0

# Verify signature
COSIGN_EXPERIMENTAL=1 cosign verify \
  ghcr.io/chaoskyle/alloy-dynamic-processors/ai-sorter:v1.0.0

# Verify SBOM
cosign download sbom \
  ghcr.io/chaoskyle/alloy-dynamic-processors/ai-sorter:v1.0.0 | jq
```

### 9. Test Helm Chart

```bash
# Add Helm repo (if published)
helm repo add alloy-processors <repo-url>
helm repo update

# Install in test cluster
helm install test-release alloy-processors/alloy-dynamic-processors \
  --version 1.0.0 \
  --namespace test \
  --create-namespace

# Verify
kubectl get pods -n test
kubectl logs -n test -l app.kubernetes.io/name=alloy-dynamic-processors
```

## Post-Release Tasks

### Immediate (Within 1 Hour)

- [ ] Verify GitHub Release created
- [ ] Test image pulls from GHCR
- [ ] Verify image signatures
- [ ] Check release notes accuracy
- [ ] Announce in team channels

### Short-term (Within 1 Day)

- [ ] Update project README badges (if applicable)
- [ ] Post announcement (social media, blog, etc.)
- [ ] Update external documentation sites
- [ ] Notify dependent projects
- [ ] Monitor error rates and metrics

### Follow-up (Within 1 Week)

- [ ] Collect user feedback
- [ ] Create issues for reported bugs
- [ ] Plan next release
- [ ] Review release process
- [ ] Update release documentation

## Rollback Procedure

If critical issues are discovered post-release:

### 1. Immediate Actions

```bash
# Stop promoting the release
# Communicate issue to users
# Assess severity and impact
```

### 2. Quick Fix (Patch Release)

If fixable quickly (< 2 hours):

```bash
# Create hotfix branch
git checkout -b hotfix/v1.0.1 v1.0.0

# Fix issue
# Test thoroughly
# Create patch release v1.0.1
```

### 3. Revert Release

If fix takes longer:

```bash
# Revert to previous stable version
# Update documentation
# Create incident report

# Mark release as pre-release in GitHub
# Add warning in release notes
```

### 4. Communication

```markdown
# Incident Communication Template

**Issue**: Brief description
**Impact**: What users are affected
**Status**: Investigating / Fix in progress / Resolved
**Workaround**: Temporary mitigation steps
**Timeline**: Expected resolution time
**Action**: What users should do
```

## Hotfix Process

For urgent production fixes:

### 1. Create Hotfix Branch

```bash
# Branch from affected release tag
git checkout -b hotfix/v1.0.1 v1.0.0
```

### 2. Implement Fix

```bash
# Make minimal changes
# Add tests
# Update CHANGELOG.md

git commit -m "fix: critical bug in X

Fixes #123"
```

### 3. Test Thoroughly

```bash
make test
make test-e2e
make scan
```

### 4. Fast-track Review

```bash
# Create PR with HOTFIX label
# Expedited review (1 reviewer minimum)
# Merge to main
```

### 5. Release

```bash
# Tag and release immediately
git tag -a v1.0.1 -m "Hotfix v1.0.1

Fixes critical issue in v1.0.0"

git push origin v1.0.1
```

### 6. Backport if Needed

```bash
# Cherry-pick to other maintained branches
git checkout release/v1.1
git cherry-pick <hotfix-commit>
```

## Release Checklist Template

Copy this checklist for each release:

```markdown
## Release vX.Y.Z Checklist

### Pre-Release
- [ ] All tests passing
- [ ] CHANGELOG.md updated
- [ ] Documentation updated
- [ ] Security scan clean
- [ ] Version numbers updated

### Release
- [ ] Release branch created
- [ ] PR created and approved
- [ ] Tag created and pushed
- [ ] GitHub Actions completed
- [ ] Images published to GHCR

### Verification
- [ ] Images pull successfully
- [ ] Signatures verified
- [ ] SBOM available
- [ ] Helm chart installs
- [ ] End-to-end tests pass

### Post-Release
- [ ] Release notes reviewed
- [ ] Announcement posted
- [ ] Metrics monitored
- [ ] Feedback collected
```

## Automation

Our release process is heavily automated via GitHub Actions:

### `.github/workflows/release.yml`

Triggers on tag push (`v*.*.*`) and automatically:
1. Builds multi-arch images
2. Runs security scans
3. Generates SBOM
4. Signs images with cosign
5. Pushes to GHCR
6. Creates GitHub Release

### Manual Override

To manually trigger release:

```bash
# Via GitHub CLI
gh workflow run release.yml -f tag=v1.0.0

# Via GitHub UI
Actions → Release → Run workflow
```

## Support Policy

- **Latest Major Version**: Full support
- **Previous Major Version**: Security fixes only (6 months)
- **Older Versions**: No support (upgrade recommended)

## Questions?

- **Technical Issues**: Create GitHub Issue
- **Security Issues**: See [SECURITY.md](../SECURITY.md)
- **Process Questions**: Contact @ChaosKyle

---

**Last Updated**: 2025-01-06
**Next Review**: Every 6 months or after major release
