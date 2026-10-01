# Changelog

Release notes for every version are on [GitHub Releases](https://github.com/icranet/astro-mmdc/releases).

## 0.2.11

- `wait_for_batch()` asks the server to hold each request until the fit ends (`Prefer: wait`, up to 25 s), so it returns about a second after the fit finishes instead of up to 30 s later.
- Against a server that does not wait, it polls after the server's `Retry-After`, at most `poll_interval`; the backoff and the 30 s jump while queued are gone.
- A done fit without a PDF now returns instead of polling until the deadline.
- Request retries inside `wait_for_batch()` stop at its deadline.

## 0.2.10

- Undated catalogue values are at MJD 50000 (both ends) instead of `None`/NaN, matching the server.
- `SED.table` and `SED.to_pandas()` gain an `undated` column; new `SED.is_undated`.
- Behaviour change: `SED.between()`, and `client.sed.csv()`/`client.sed.get()` with an MJD window, now leave undated points out unless `undated=True` (previously they were kept).

## 0.2.9

- Relicensed from MIT to BSD-3-Clause.
- The source moved to the public repository [github.com/icranet/astro-mmdc](https://github.com/icranet/astro-mmdc).
