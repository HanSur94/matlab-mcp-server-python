# Deferred Items

## Pre-existing Failures (out-of-scope)

### test_executor_extra.py::TestErrorResult::test_error_result_structure
- **File:** tests/test_executor_extra.py:247
- **Issue:** `job.error` is `None` after `mark_failed()` — test expects `result["error"]["type"]`
  to be subscriptable but `job.error` is `None` in this worktree's version of `Job`.
- **Discovered during:** Plan 07-05, Task 2 verification
- **Status:** Pre-existing failure (confirmed failing before any plan 07-05 changes)
- **Resolution:** Investigate `Job.mark_failed()` and `Job.error` field assignment in
  jobs/models.py — likely needs to be fixed in a separate plan.
