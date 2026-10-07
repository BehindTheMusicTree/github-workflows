# Input: GET /api/v1/deployments (active deployments, array or id-keyed object).
# Emits this app's (or this PR preview's) queued/in_progress deployments older than $max_age
# seconds, with age_seconds added — null when created_at can't be parsed, so the caller can
# report it instead of one bad row aborting the whole filter.
def age_seconds:
  try (now - (.created_at | sub("\\.[0-9]+"; "") | sub(" "; "T") | sub("(Z|[+-]00:?00)$"; "") | . + "Z" | fromdateiso8601))
  catch null;

.[]?
| select((.deployment_url // "") | contains("/application/\($app)/"))
| select((.pull_request_id | tostring) == $pr and (.status == "queued" or .status == "in_progress"))
| . + {age_seconds: age_seconds}
| select(.age_seconds == null or .age_seconds > $max_age)
