# Personal CI/CD Platform

A personal end-to-end CI/CD demonstration built with Flask, Python, Docker, GitHub Actions, Trivy, GitHub Container Registry (GHCR), and a self-hosted GitHub Actions runner on AI-LAB.

The goal of this project is to demonstrate a complete software delivery path:

```text
Developer workstation (REACTOR)
        |
        | git push
        v
GitHub repository (main)
        |
        v
GitHub Actions
   |       |       |
   |       |       +--> Deploy to AI-LAB
   |       |
   |       +----------> Trivy security scan
   |
   +------------------> pytest
        |
        v
GHCR container image
        |
        v
AI-LAB self-hosted runner
        |
        v
docker pull -> replace container -> health check
        |
        v
Running Flask application
```

## Project status

The pipeline has been successfully tested end-to-end. A code change committed as `454dc57` triggered the complete workflow:

- Test Application: passed
- Build, Scan and Publish Docker Image: passed
- Deploy to AI-LAB: passed
- AI-LAB health check: passed
- The updated API response was verified directly on AI-LAB

The self-hosted runner is installed as a systemd service and is enabled to start automatically at boot.

## Repository layout

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml              # CI, container build/scan/publish, deployment
├── app/
│   └── main.py                 # Flask application
├── tests/
│   └── test_main.py            # Application tests
├── Dockerfile                  # Production container definition
├── requirements.txt             # Python runtime dependencies
├── .dockerignore
├── .gitignore
├── README.md
└── docs/
    └── OPERATIONS.md           # Deployment and operations notes
```

## Application

The application is a small Flask API served by Gunicorn.

### Endpoints

`GET /`

Returns the application name, deployment message, and running status.

`GET /health`

Returns a simple health response used by the deployment workflow.

Example successful health response:

```json
{"status":"healthy"}
```

## CI/CD workflow

The workflow is defined in `.github/workflows/ci.yml`.

### 1. Test

Triggered on pushes to `main` and pull requests.

The test job:

1. Checks out the repository.
2. Installs Python 3.14.
3. Installs application dependencies.
4. Installs pytest.
5. Runs `python -m pytest`.

The application currently has tests covering `/` and `/health`.

### 2. Build and security scan

After tests pass, the Docker job builds the image using:

```text
python:3.14-alpine
```

The image is tagged with the immutable GitHub commit SHA:

```text
ghcr.io/<owner>/my-cicd-project:<github-sha>
```

Trivy scans the built image for `CRITICAL` and `HIGH` vulnerabilities. The scan fails the workflow when a fixed vulnerability is detected; unfixed findings are ignored with `ignore-unfixed: true`.

### 3. Publish to GHCR

For pushes to `main`, GitHub Actions authenticates to GitHub Container Registry using the workflow's built-in `GITHUB_TOKEN` and publishes the commit-tagged image.

The package is public, so the AI-LAB host can pull the deployment image without a personal access token.

### 4. Deploy to AI-LAB

The deployment job runs only for pushes to `main` and uses the self-hosted runner labels:

```yaml
runs-on: [self-hosted, Linux, X64]
```

The deployment performs:

1. Pull the new commit-tagged image from GHCR.
2. Stop the existing `my-cicd-project` container.
3. Remove the old container.
4. Start the new image on port `8080`.
5. Wait three seconds.
6. Run `curl --fail http://localhost:8080/health`.

A failed health check fails the deployment job.

## Docker image

The Dockerfile uses Alpine to keep the runtime image small and reduce the operating-system vulnerability surface.

The final image contains the application and runtime dependencies, while build tooling that is not needed at runtime is removed. In particular, `pip` and `setuptools` are uninstalled from the final image after dependency installation.

The container runs Gunicorn:

```text
gunicorn --bind 0.0.0.0:8080 app.main:app
```

The container exposes port `8080`.

## Security scanning troubleshooting

During development, the first Trivy scan found two HIGH findings associated with packages that were not direct application requirements:

- `msgpack` — `GHSA-6v7p-g79w-8964`
- `setuptools` — `CVE-2025-47273`

Investigation showed these were being detected through Python tooling/vendor metadata rather than the application's declared runtime dependencies. The solution was not to weaken the vulnerability gate, but to remove `pip` and `setuptools` from the runtime image after installing the required application dependencies.

The Debian-based Python image also exposed operating-system vulnerabilities during the scan. The runtime image was therefore changed to `python:3.14-alpine`, followed by `apk upgrade --no-cache` so the Alpine packages were current during the image build.

The resulting image passed the configured Trivy gate.

## Self-hosted runner

The deployment host is **AI-LAB**.

Runner details:

- Runner name: `kevin-ai`
- OS: Linux
- Architecture: x64
- Labels: `self-hosted`, `Linux`, `X64`
- Runner version at setup: `2.337.0`
- Work directory: `~/actions-runner`

The runner was initially tested interactively with `./run.sh`. It was then installed as a systemd service using the runner-provided `svc.sh` script.

The service is enabled and running, so the runner starts automatically after a reboot.

The service name is generated by GitHub and is based on the repository and runner name.

## Deployment verification

The final end-to-end test changed the application message to:

```text
Hello from my CI/CD pipeline — automated deployment works!
```

After pushing commit `454dc57`, GitHub Actions completed all three jobs successfully. The running application on AI-LAB was then checked directly:

```bash
curl http://localhost:8080/
curl http://localhost:8080/health
```

The first endpoint returned the updated deployment message and the second returned:

```json
{"status":"healthy"}
```

This verified that the newly built container, rather than the previous container, was running on AI-LAB.

## Design decisions

### Immutable image tags

Images are tagged with the Git commit SHA rather than relying only on `latest`. This makes every deployed container traceable to a specific source revision and avoids ambiguity about which version is running.

### Deployment only from `main`

The deploy job is explicitly restricted to pushes to `main`. Pull requests run the test and Docker validation stages on GitHub-hosted runners but do not deploy to AI-LAB.

### Health check after replacement

The deployment does not stop after `docker run`. It verifies the HTTP health endpoint before the workflow reports success.

### No runtime Docker build on AI-LAB

AI-LAB only pulls the already-built and scanned image from GHCR. This keeps the deployment host focused on running the artifact produced by CI.

## Security considerations

This repository currently uses a self-hosted runner attached to a public GitHub repository. GitHub warns that self-hosted runners for public repositories have additional security risk because untrusted workflow code can potentially execute on the runner.

The current workflow reduces exposure by keeping pull-request jobs on GitHub-hosted runners and allowing deployment only from `main`, but this does not eliminate the general risk.

For a more hardened setup, consider:

- Making the repository private if appropriate.
- Protecting `main` with branch rules requiring review and successful checks.
- Keeping the self-hosted runner dedicated to this repository.
- Avoiding secrets on the self-hosted runner unless absolutely necessary.
- Keeping Docker, Ubuntu, the GitHub runner, and application dependencies updated.
- Adding a controlled rollback procedure before treating the host as production infrastructure.

No personal access token is required for the current public GHCR deployment path.

## Known workflow warnings

GitHub Actions currently reports Node.js 20 deprecation warnings for some actions used by the workflow. These are warnings rather than failures, and the pipeline currently succeeds. The action versions can be updated as their maintainers publish Node.js 24-compatible releases.

## Future improvements

Potential next steps:

1. Add branch protection/rules for `main`.
2. Add a documented rollback procedure using a previous SHA-tagged image.
3. Add a `latest` or environment-specific convenience tag in addition to immutable SHA tags.
4. Add deployment metadata showing the deployed Git SHA.
5. Expand the application and test suite.
6. Add dependency pinning and automated dependency updates.
7. Add container runtime hardening such as a non-root user and read-only filesystem where practical.
8. Update GitHub Actions as Node.js 24-compatible releases become available.

## Example developer workflow

From the development machine:

```bash
git checkout main
git pull origin main
# edit application code
git add .
git commit -m "Describe the change"
git push origin main
```

After the push, the automated path is:

```text
git push
  -> pytest
  -> docker build
  -> Trivy scan
  -> GHCR push
  -> AI-LAB runner
  -> docker pull
  -> container replacement
  -> health check
```

The developer does not need to manually build the container or restart the application on AI-LAB.
