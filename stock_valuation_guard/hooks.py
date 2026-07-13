from __future__ import unicode_literals

app_name = "stock_valuation_guard"
app_title = "Stock Valuation Guard"
app_publisher = "Havano"
app_description = (
	"Nightly auto-detection and correction of ERPNext stock valuation errors "
	"caused by negative stock, zero incoming_rate, and stuck Repost Item Valuation jobs."
)
app_email = "admin@havano.cloud"
app_license = "MIT"

# ---------------------------------------------------------------------------
# Scheduler Events
# ---------------------------------------------------------------------------
# daily_long runs once per day (around midnight UTC / 2 AM CEST).
# The job is long-running by design — it triggers the full repost engine.
scheduler_events = {
	"daily_long": [
		"stock_valuation_guard.tasks.run_nightly_guard"
	]
}

# ---------------------------------------------------------------------------
# Fixtures — ships the DocType JSON so it's auto-imported on migrate
# ---------------------------------------------------------------------------
fixtures = [
	{
		"doctype": "Custom DocPerm",
		"filters": [["parent", "in", ["Valuation Guard Log"]]]
	}
]
