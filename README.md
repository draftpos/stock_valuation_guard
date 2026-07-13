# Stock Valuation Guard

A Frappe app that runs nightly to automatically detect and correct ERPNext stock valuation errors caused by:

- Negative stock transactions (backdated entries, wrong posting order)
- Sales Invoices with `incoming_rate = 0` (cost not captured at time of sale)
- Stuck `Repost Item Valuation` jobs that never auto-processed

## What it does

Every night at midnight UTC (2 AM CEST), the app:

1. **Detects** — SQL scans for problem item/warehouse pairs and stuck jobs
2. **Corrects** — Creates/requeues `Repost Item Valuation` docs and triggers the engine inline
3. **Reports** — Saves a `Valuation Guard Log` in ERPNext and emails a summary to all System Managers

## Installation

```bash
cd ~/frappe-bench
bench --site <your-site> install-app stock_valuation_guard
bench --site <your-site> migrate
bench restart
```

## Manual trigger

```bash
bench --site <your-site> execute stock_valuation_guard.tasks.run_nightly_guard
```

## License

MIT
