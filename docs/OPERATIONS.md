# Operations Runbook

This document records the operational steps used to run and maintain the Personal CI/CD Platform.

## Hosts

### REACTOR

Development workstation. Source changes are made here and pushed to GitHub.

Repository:

```text
~/projects/my-cicd-project
```

Normal developer flow:

```bash
git status
git pull origin main
# make changes
git add .
git commit -m "Describe the change"
git push origin main
```

### AI-LAB

Deployment host running the application container and the GitHub Actions self-hosted runner.

Application deployment directory used during manual setup:

```text
/home/kevin-ai/my-cicd-project
```

Runner directory:

```text
~/actions-runner
```

The application is exposed on TCP port `8080`.

## Self-hosted runner service

The runner is named `kevin-ai` and uses the labels `self-hosted`, `Linux`, and `X64`.

The runner was configured with GitHub's Linux runner package and then installed as a systemd service.

### Check status

On AI-LAB:

```bash
cd ~/actions-runner
sudo ./svc.sh status
```

A healthy service should show:

```text
Loaded: loaded ...; enabled
Active: active (running)
```

The runner should also appear as **Idle** in the repository's GitHub Settings → Actions → Runners page when it is not processing a job.

### Start/stop/restart

```bash
cd ~/actions-runner
sudo ./svc.sh start
sudo ./svc.sh stop
sudo ./svc.sh status
```

If the service needs to be restarted:

```bash
sudo ./svc.sh stop
sudo ./svc.sh start
sudo ./svc.sh status
```

Do not run `./run.sh` interactively while the systemd service is already running. That would attempt to start a second runner process.

### View systemd logs

Use the service name displayed by `sudo ./svc.sh status` and inspect it with:

```bash
sudo journalctl -u '<runner-service-name>' -f
```

The runner should report that it is connected to GitHub and listening for jobs.

## Application container

Container name:

```text
my-cicd-project
```

Port mapping:

```text
8080:8080
```

Restart policy:

```text
unless-stopped
```

### Check container

```bash
docker ps
```

### Check application

```bash
curl http://localhost:8080/
curl http://localhost:8080/health
```

Expected health response:

```json
{"status":"healthy"}
```

### View application logs

```bash
docker logs my-cicd-project
```

Follow logs live:

```bash
docker logs -f my-cicd-project
```

## Automated deployment behavior

The GitHub Actions deployment job runs only for a push to `main` and only after the test and Docker jobs succeed.

The deployment runner:

1. Pulls `ghcr.io/<owner>/my-cicd-project:<commit-sha>`.
2. Stops `my-cicd-project` if it exists.
3. Removes the old container if it exists.
4. Starts the new image.
5. Waits three seconds.
6. Runs the `/health` endpoint with `curl --fail`.

Because the image tag is the Git commit SHA, the deployed artifact can be traced to the source revision that produced it.

## Manual recovery

If an automated deployment leaves the application unavailable, first inspect the runner and container:

```bash
cd ~/actions-runner
sudo ./svc.sh status
docker ps -a
docker logs --tail 100 my-cicd-project
curl --fail http://localhost:8080/health
```

If the current container must be stopped manually:

```bash
docker stop my-cicd-project || true
docker rm my-cicd-project || true
```

A previous known-good image can be pulled by its immutable Git SHA and started manually. Keep the exact SHA of the desired rollback image before replacing the current deployment.

Example pattern:

```bash
docker pull ghcr.io/marcottejkevin-art/my-cicd-project:<known-good-sha>

docker run -d \
  --name my-cicd-project \
  --restart unless-stopped \
  -p 8080:8080 \
  ghcr.io/marcottejkevin-art/my-cicd-project:<known-good-sha>

curl --fail http://localhost:8080/health
```

## GHCR

The container image is published to GitHub Container Registry under:

```text
ghcr.io/marcottejkevin-art/my-cicd-project
```

The package is public, so AI-LAB can pull images without a personal access token.

The GitHub Actions workflow uses the built-in `GITHUB_TOKEN` for publishing rather than storing a registry password in the repository.

Do not place GitHub tokens, passwords, or other credentials in this repository or in workflow output.

## Trivy security gate

The Docker image is scanned before it is published. The workflow checks `CRITICAL` and `HIGH` vulnerabilities and fails on findings that have a fix available.

The runtime image was changed from Debian-based Python to Alpine after operating-system vulnerabilities were found during development. The final Docker build performs:

```text
apk upgrade --no-cache
```

before the runtime image is published.

Python build tooling that is unnecessary at runtime is removed after dependency installation.

## Incident notes from initial setup

### GHCR authentication

A personal access token was initially attempted for pulling the image. Authentication failed, but the GHCR package was subsequently confirmed to be public and the image could be pulled anonymously. No PAT is needed for the current deployment.

### Trivy findings from Python tooling

The initial scan detected HIGH findings associated with `msgpack` and `setuptools` through Python tooling/vendor metadata. Instead of weakening the security gate, the runtime image was changed so `pip` and `setuptools` are removed after dependencies are installed.

### Runner startup

The runner was first tested with `./run.sh`. That requires an interactive terminal and stops when the process is stopped. Installing the runner with `svc.sh` changed the deployment to a persistent systemd service that starts at boot.

## Public-repository runner warning

This repository uses a self-hosted runner while the repository is public. GitHub warns that self-hosted runners attached to public repositories carry additional risk because untrusted workflow code may execute on the runner.

The workflow limits deployment to pushes on `main`, while pull-request test/build jobs use GitHub-hosted runners. This reduces exposure but does not eliminate the underlying risk.

For a hardened environment, consider making the repository private and protecting `main` with required reviews and status checks.
