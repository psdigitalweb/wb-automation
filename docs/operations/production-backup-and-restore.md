# Production backup and restore verification

Use this workflow immediately before migrations that change product identity,
financial links, credentials, or other foundational data contracts.

## What the backup contains

- PostgreSQL custom-format dump (`database.dump`);
- exact row counts for critical tables;
- current Git commit, Alembic revision, and Docker image IDs;
- compressed archives of `internal_data` and `wb_content_history` volumes;
- SHA-256 checksums for every artifact;
- SHA-256 fingerprints of encryption key files.

Encryption key material is deliberately not copied into the backup directory. Keep
the matching key files in the approved secrets recovery storage. A database backup
without the matching keys cannot restore encrypted marketplace credentials.

## 1. Prepare secure storage

Create a root-only directory outside the Git checkout, preferably on encrypted or
off-host storage. Do not store the output under the repository.

```bash
sudo install -d -m 0700 /srv/ecomcore-backups
```

Record or snapshot the currently deployed API and frontend images before replacing
them. The backup manifest includes their exact image IDs, but the registry or host
must still retain those images for application rollback.

## 2. Create the backup

Run from the repository root on the production host:

```bash
python scripts/production_backup.py \
  --output-dir /srv/ecomcore-backups \
  --compose-file infra/docker/docker-compose.prod.yml \
  --env-file .env \
  --repo-root . \
  --project-name ecomcore
```

By default the script gracefully stops API, worker, and beat while capturing the
database and file volumes, then starts the same services again. This gives the
database and uploaded files one coherent recovery point. Use `--online` only when a
brief maintenance window is impossible; the PostgreSQL dump remains consistent,
but files written during the backup may not correspond to the same instant.

The script never deletes older backups and never copies `.env` or encryption keys.

## 3. Prove that the backup restores

```bash
python scripts/verify_production_backup.py \
  /srv/ecomcore-backups/ecomcore-pre-migration-YYYYMMDDTHHMMSSZ
```

Verification:

1. checks every SHA-256;
2. validates volume archives and rejects unsafe paths;
3. starts an isolated, unpublished PostgreSQL 16 container;
4. restores the complete dump with `--exit-on-error`;
5. compares exact critical-table row counts and Alembic revision;
6. checks that the number of pre-existing unvalidated foreign keys exactly matches
   the source database;
7. removes only its generated temporary container.

Do not deploy if this command does not finish with `"status": "verified"`.

## 4. Preserve the recovery set

Copy the verified backup directory to independent storage and retain:

- the backup directory and checksums;
- the exact application images or an immutable release tag;
- the matching secret key files in secrets storage;
- the commit SHA printed in `metadata.json`.

Do not place any of these artifacts in Git.

## Rollback order

1. Stop API, worker, and beat.
2. Restore the application version recorded in `metadata.json`.
3. Restore the PostgreSQL dump into an empty PostgreSQL 16 database.
4. Restore both persistent volume archives.
5. Mount the secret keys whose SHA-256 fingerprints match `metadata.json`.
6. Start API and verify the recorded Alembic revision before starting worker/beat.
7. Run health checks and narrow product/review/financial smoke tests.

Never combine a restored encrypted database with different secret keys.
