# CI recipes

Drop-in configurations for gating a data pipeline on Shuddhi. They all do the
same two things, because those are the two things worth automating:

1. **Gate the registry.** `shuddhi check` exits non-zero when any shard is
   untagged or carries a customer data class. Run it on every pull request
   and an unreviewed dataset cannot merge — the rule is enforced by the
   pipeline instead of by someone remembering.
2. **Build and keep the receipt.** On merge, build the corpus and publish
   `BUILD-MANIFEST.json` (and the HTML receipt) as an artefact, so every
   corpus your team trains on has a retrievable, recomputable identity.

| platform | file |
|---|---|
| GitHub Actions | [`github-actions.yml`](github-actions.yml) |
| GitLab CI | [`gitlab-ci.yml`](gitlab-ci.yml) |
| Azure Pipelines | [`azure-pipelines.yml`](azure-pipelines.yml) |
| Bitbucket Pipelines | [`bitbucket-pipelines.yml`](bitbucket-pipelines.yml) |
| CircleCI | [`circleci.yml`](circleci.yml) |
| Jenkins | [`Jenkinsfile`](Jenkinsfile) |

Each runs the container image, so no Python setup is needed on the runner.

**Pin the image.** Use `ghcr.io/agentanywhere/shuddhi:1.2.0`, not `:latest` —
a receipt whose engine version can drift is a weaker receipt.
