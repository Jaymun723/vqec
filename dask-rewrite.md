# Goal

The goal is to migrate from

```text
workers <- HTTP -> server
```

to

```text
workers <- Dask -> server
```

The server should no longer schedule individual tasks. Its role is to:

* expose the REST API,
* validate experiment submissions,
* build the experiment DAG,
* submit the DAG to Dask,
* maintain experiment metadata,
* expose experiment status.

Dask should become the scheduler responsible for task execution and dependency resolution.

---

# Database

The database has three purposes only.

## Experiment metadata

```python
Experiment
----------
id
status      # IN_FLIGHT | DONE | ERROR | CANCELLED
submitted_at
result_path
error
```

## Generated data cache

This is used to deduplicate data tasks.

The database stores

* task hash
* output path
* metadata

## Generated decode cache

This is used to deduplicate decode tasks.

The database stores

* task hash
* output path
* metadata

The database is **not** intended to mirror the Dask scheduler.

---

# Experiment submission

When a user submits an experiment:

1. Validate the experiment.

2. Insert the experiment into the database with status `IN_FLIGHT`.

3. Generate every data task.

4. For each data task:

   * if already cached, create a Dask Future using the cached value
   * otherwise create a Dask Future executing the generation activity

5. Generate every decode task.

6. For each decode task:

   * determine the required data Futures
   * if already cached, create a Future containing the cached result
   * otherwise create a Future depending on the required data Futures

7. Create a final consolidation task depending on every decode Future.

8. Submit the entire graph to Dask.

The important requirement is that decode tasks must begin execution as soon as **their own dependencies** are satisfied. There must be **no barrier** waiting for every data task to finish.

The graph should look like

```text
Data A --------\
                \
                 Decode X ----\
Data B ----------/             \
                                \
                                 Consolidate

Data A ---------------- Decode Y /
```

not

```text
All Data

↓

All Decode

↓

Consolidate
```

---

# Cache behavior

The cache is content-addressable.

A task is uniquely identified by a deterministic hash.

When a cached artifact exists:

* no computation should be submitted,
* the workflow should use the cached output immediately.

This applies independently to data tasks and decode tasks.

---

# Monitoring

The server should **not** maintain lists of every Future or implement a polling scheduler.

Instead, the design should use Dask's APIs to monitor the submitted graph.

The server should only keep enough information to retrieve the state of an experiment.

---

# Completion

The server keeps only one Future per experiment: the consolidation Future.
Completion and failure are handled via add_done_callback on that Future.
Status for IN_FLIGHT experiments is derived from that single Future's status.

When the final consolidation task completes:

* save the result to disk,
* update the experiment status to `DONE`,
* save the result path.

If any task ultimately fails:

* update the experiment status to `ERROR`,
* store the error.

---

# REST API

Implement:

```
POST   /tasks/experiment
GET    /tasks/experiment
GET    /tasks/experiment/{id}
DELETE /tasks/experiment/{id}
POST   /tasks/experiment/{id}/cancel
POST   /tasks/experiment/{id}/retry
GET    /tasks/experiment/{id}/download
```

---

# Cancellation

Cancelling an experiment should cancel the submitted Dask graph.

The server should not manually walk every task unless required by Dask.

---

# Retry

Retry should submit a new graph using the same experiment definition.

Previously cached data and decode artifacts must be reused.

---

# Server restart

The implementation should minimize in-memory state.

After restart:

* completed experiments remain completed,
* failed experiments remain failed,
* If an experiment is marked `IN_FLIGHT` but no corresponding Dask computation exists, it should transition to `ERROR` so it can later be retried.

---

# Design requirements

The implementation should:

* leverage Dask's DAG scheduler rather than reimplementing one,
* avoid maintaining a registry of thousands of Futures in the server whenever possible,
* allow thousands of data and decode tasks,
* maximize parallel execution,
* start decode tasks immediately when their dependencies are satisfied,
* support multiple decode tasks depending on the same data task,
* support decode tasks depending on multiple data tasks,
* keep orchestration logic simple and avoid a background polling scheduler if Dask already provides equivalent functionality.