# Install WorxDB as a Portainer Stack

Use your **Docker Standalone** environment in Portainer. This installs the web app and its own MariaDB container. No SSH commands, manually built image, registry account or pre-created host directories are needed. Portainer builds the app from the repository during deployment.

## 1. Add the stack

Open **Stacks → Add stack** and enter:

| Setting | Value |
| --- | --- |
| Name | `worxdb` |
| Build method | **Repository** / **Git repository** |
| Repository URL | `https://github.com/bl1tzkr13g/WorxDB` |
| Repository reference | `refs/heads/main` |
| Compose path | `portainer-stack.yml` |
| Authentication | Off while the repository is public; if you make it private, use a Portainer-stored Git credential with repository read access |

Use Repository mode so Portainer obtains the Dockerfile, Python requirements and application source. Pasting this Compose file into the Web editor alone does not provide its build context.

## 2. Set environment variables

Under **Environment variables**, add these before deploying:

| Variable | Value |
| --- | --- |
| `APP_USER` | `admin` (or your preferred login name) |
| `APP_PASSWORD` | Your chosen strong WorxDB login password |
| `SECRET_KEY` | A random secret of at least 64 characters; keep it unchanged on updates |
| `DB_PASSWORD` | A separate strong database password |
| `DB_ROOT_PASSWORD` | A different strong root database password |
| `APP_PORT` | `8097` |

Use your password manager to generate these values. Do not paste them into chat or commit them to GitHub. Required secrets have no fallback defaults: deployment stops if they are missing.

Optional `APP_BIND` defaults to `0.0.0.0`, exposing the app on the Docker host's interfaces. You can set it to your Docker server's LAN address, or `127.0.0.1` if a reverse proxy on that same host will provide access. MariaDB is not published to a host port.

## 3. Deploy and open

Click **Deploy the stack**. The first installation downloads base images and builds the application; allow several minutes. The host needs outbound access to GitHub, Docker Hub, Debian package mirrors and PyPI. MariaDB initializes first; the app starts after its health check succeeds.

Open:

```text
http://YOUR-DOCKER-SERVER-IP:8097
```

Log in using `APP_USER` and `APP_PASSWORD`. If port 8097 is already occupied, change only `APP_PORT`; the app's internal port remains 8080. Use an HTTPS reverse proxy before exposing it outside your trusted LAN.

## Persistent data

Portainer creates stack-scoped named volumes, normally:

- `worxdb_database`: MariaDB records, field definitions, reports and workspace settings.
- `worxdb_imports`: original uploaded files and import previews.

Keep the same stack name and volumes on updates. Do not remove volumes when redeploying. Original uploads and imported records remain on your Docker server; they are not sent to the GitHub repository.

Changing MariaDB password variables after first initialization does not change existing MariaDB user passwords. Keep the original values when updating, or rotate database passwords through MariaDB and then update the app settings to match.

## Updates

Open the existing `worxdb` stack and use its Git redeploy/update action. Retain all environment values and volumes. Ensure your Portainer version rebuilds the app image from the updated source; if it offers a build/rebuild option, enable it. If a redeploy retains an old image, use a current Portainer release or rebuild the repository stack through its supported build workflow. Back up the database before updates.

## Troubleshooting

- **Dockerfile not found:** use Repository mode with the exact Compose path above.
- **Missing environment variable:** add the named variable in Portainer and redeploy.
- **Port already allocated:** change `APP_PORT` to an unused host port.
- **MariaDB Access denied after changing passwords:** restore the original variable values. Existing database volumes retain their original credentials.
- **Build fails fetching packages:** check the Docker host's outbound access and the app build log.
- **Swarm environment:** this installer uses Compose builds and `depends_on` health checks. It is not a Docker Swarm stack; select Docker Standalone.

The GitHub Actions Docker integration job uses this exact Stack file with a test port and temporary credentials, builds it, and exercises the running app against real MariaDB.
