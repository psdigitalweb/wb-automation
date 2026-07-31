# PROJECT_SECRETS_KEY rotation runbook

## Why rotation is required

The production `PROJECT_SECRETS_KEY` was previously tracked in Git. Removing the
file from the current tree prevents future accidental inclusion, but it does not
remove the key from existing Git history. Treat the current key as compromised.

Verified production state on 2026-07-31:

- the API reads the primary key from `/app/.project_secrets_key`;
- 3 `project_marketplaces.api_token_encrypted` values exist;
- all 3 values decrypt with the current key;
- no legacy `api_token`, `token`, or `analytics_token` fields exist in
  `settings_json`.

Do not place key values, token values, database dumps, or key fingerprints in
Git, task logs, or this document.

## Safety model

Rotation uses a two-key Fernet ring:

1. The new key is first and is used for all new encryption.
2. The previous key is second and is accepted only for decryption.
3. Existing database values are rotated transactionally to the new key.
4. The previous key is removed only after every value is verified with the new
   key and production health checks pass.

This follows the `MultiFernet` rotation model. A single-key swap is forbidden:
changing the application key before or after a database-only rewrite creates a
window where tokens cannot be decrypted.

## Preconditions

- The production source and database have fresh recovery backups.
- The current key still decrypts every encrypted token.
- The compatibility code supporting `PROJECT_SECRETS_PREVIOUS_KEY_FILE` has
  passed tests and has been deployed to API, worker, and beat.
- A new Fernet key has been generated on the production host with restrictive
  file permissions and stored outside the repository and Docker build context.
- The expected encrypted-token count has been recorded immediately before
  rotation.
- No marketplace credential update is running during the short rotation
  transaction.

## Phase 1: deploy compatibility without changing keys

Deploy the key-ring-capable application with the existing primary key only.
There must be no behavior change.

Verify:

- API, worker, and beat start normally;
- all encrypted tokens remain decryptable;
- marketplace status and one narrow WB API check succeed;
- no decryption errors appear in logs.

## Phase 2: configure the transition key ring

On the production host:

1. Generate a new Fernet key.
2. Store the new key in a root/deploy-owned file with mode `0600`.
3. Preserve the current key in a separate previous-key file with mode `0600`.
4. Mount both files read-only into API, worker, and beat.
5. Configure:

```text
PROJECT_SECRETS_KEY_FILE=/run/secrets/project_secrets_key
PROJECT_SECRETS_PREVIOUS_KEY_FILE=/run/secrets/project_secrets_previous_key
```

The production compose file always mounts the primary key. Set
`PROJECT_SECRETS_KEY_HOST_PATH` to its absolute host path. During the transition,
also set `PROJECT_SECRETS_PREVIOUS_KEY_HOST_PATH` and include the rotation
override:

```text
docker compose \
  --env-file ../../.env \
  -f docker-compose.prod.yml \
  -f docker-compose.secrets-rotation.yml \
  config
```

Inspect the rendered service names, mounts, and key-file variable names without
printing or copying the file contents. Use the same pair of compose files for
the transition deployment.

The new key must be the primary file. The exposed old key must be the previous
file. Neither file may live inside the repository or Docker image.

Restart the services and verify that all existing values still decrypt. New
writes will now use the new primary key.

## Phase 3: dry-run the database rotation

Run inside the API container:

```text
python /app/scripts/rotate_project_secrets_key.py --expected-count <count>
```

Expected result:

- `invalid` is `0`;
- `total` equals the recorded count;
- existing old-key values appear as `requires_rotation`;
- any credentials updated after Phase 2 may already appear as
  `encrypted_with_primary`.

The command is read-only unless `--apply` is supplied.

## Phase 4: create backup and apply

Create and verify a database backup immediately before applying. Then run:

```text
python /app/scripts/rotate_project_secrets_key.py \
  --apply \
  --expected-count <count> \
  --confirm ROTATE_PROJECT_SECRETS_KEY
```

The script:

- locks the selected rows;
- refuses to continue if the count changed;
- refuses to continue if any token is not decryptable;
- rotates only values not already encrypted with the primary key;
- verifies every result with the primary key;
- commits all changes together or rolls the entire transaction back.

## Phase 5: production verification

Before retiring the old key:

- repeat the dry-run and require `requires_rotation=0` and `invalid=0`;
- verify marketplace connection status;
- execute one narrow read-only WB request for every configured project;
- confirm API, worker, and beat have no decryption errors;
- observe at least one normal ingestion cycle.

## Phase 6: retire the exposed key

After the observation window:

1. Remove `PROJECT_SECRETS_PREVIOUS_KEY_FILE` from API, worker, and beat.
2. Restart the services.
3. Repeat the production verification.
4. Securely remove the previous-key file from the production host and recovery
   locations that are no longer required.

Only after the key is retired should Git-history cleanup be considered. History
rewriting requires separate approval and coordination because it changes commit
identities and affects every clone and remote branch.

## Rollback

Before database rotation, restore the previous service configuration.

After database rotation, do not roll back to an application configuration that
knows only the old key. Either:

- keep the new key available to the rolled-back application as primary or
  fallback; or
- restore the pre-rotation database backup together with the old-key
  configuration.

Never restore only one side of the key/database pair.
