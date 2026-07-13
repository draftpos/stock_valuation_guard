"""
tasks.py — Entry point for the nightly Stock Valuation Guard job.

Called by Frappe scheduler via hooks.py:
    scheduler_events = {"daily_long": ["stock_valuation_guard.tasks.run_nightly_guard"]}

Can also be triggered manually:
    bench --site <site> execute stock_valuation_guard.tasks.run_nightly_guard
"""

from __future__ import unicode_literals

import traceback
from datetime import datetime

import frappe

from stock_valuation_guard.valuation_guard.detector import (
	find_negative_stock_items,
	find_stuck_repost_jobs,
	find_zero_valuation_items,
)
from stock_valuation_guard.valuation_guard.corrector import (
	create_repost_entries,
	requeue_stuck_jobs,
	trigger_repost_engine,
)
from stock_valuation_guard.valuation_guard.reporter import (
	save_log,
	send_summary_email,
)


def run_nightly_guard():
	"""
	Main nightly job. Detects valuation problems, queues corrections,
	triggers the repost engine, and sends a summary email.
	"""
	frappe.logger("valuation_guard").info("=== Stock Valuation Guard: starting nightly run ===")

	run_start = datetime.now()
	result = {
		"run_date": run_start.strftime("%Y-%m-%d"),
		"run_time": run_start.strftime("%H:%M:%S"),
		"negative_stock_items": 0,
		"zero_valuation_invoices": 0,
		"repost_jobs_created": 0,
		"repost_jobs_requeued": 0,
		"repost_jobs_completed": 0,
		"repost_jobs_failed": 0,
		"status": "Success",
		"summary": "",
		"errors": [],
	}

	try:
		# ------------------------------------------------------------------
		# PHASE 1: Detection
		# ------------------------------------------------------------------
		frappe.logger("valuation_guard").info("Phase 1: Detection")

		negative_items = find_negative_stock_items(days_back=90)
		result["negative_stock_items"] = len(negative_items)

		zero_valuation = find_zero_valuation_items(days_back=90)
		result["zero_valuation_invoices"] = len(zero_valuation)

		stuck_jobs = find_stuck_repost_jobs(days_back=14)

		frappe.logger("valuation_guard").info(
			f"Detected: {len(negative_items)} negative-stock items, "
			f"{len(zero_valuation)} zero-valuation invoice rows, "
			f"{len(stuck_jobs)} stuck repost jobs"
		)

		# ------------------------------------------------------------------
		# PHASE 2: Correction
		# ------------------------------------------------------------------
		frappe.logger("valuation_guard").info("Phase 2: Correction")

		# Requeue any Failed/stuck jobs
		if stuck_jobs:
			requeued = requeue_stuck_jobs(stuck_jobs)
			result["repost_jobs_requeued"] = requeued

		# Combine item+warehouse pairs from both detection sources
		all_pairs = _merge_item_pairs(negative_items, zero_valuation)

		# Create new Repost Item Valuation docs for pairs not already queued
		created = create_repost_entries(all_pairs)
		result["repost_jobs_created"] = created

		frappe.db.commit()

		# ------------------------------------------------------------------
		# PHASE 3: Trigger repost engine (inline, up to 45 min)
		# ------------------------------------------------------------------
		frappe.logger("valuation_guard").info("Phase 3: Triggering repost engine (timeout=45min)")
		completed, failed = trigger_repost_engine(timeout_minutes=45)
		result["repost_jobs_completed"] = completed
		result["repost_jobs_failed"] = failed

		frappe.db.commit()

	except Exception:
		err = traceback.format_exc()
		frappe.logger("valuation_guard").error(f"Nightly guard error:\n{err}")
		result["status"] = "Failed"
		result["errors"].append(err)

	else:
		# Partial success if some repost jobs still failed
		if result["repost_jobs_failed"] > 0:
			result["status"] = "Partial"

	# ------------------------------------------------------------------
	# PHASE 4: Report
	# ------------------------------------------------------------------
	result["summary"] = _build_summary(result)
	frappe.logger("valuation_guard").info(result["summary"])

	try:
		save_log(result)
		send_summary_email(result)
	except Exception:
		frappe.logger("valuation_guard").error(
			"Failed to save log or send email:\n" + traceback.format_exc()
		)

	frappe.logger("valuation_guard").info("=== Stock Valuation Guard: run complete ===")


def _merge_item_pairs(negative_items, zero_valuation):
	"""Deduplicate (item_code, warehouse) pairs from both detection sources."""
	seen = set()
	pairs = []
	for row in negative_items:
		key = (row["item_code"], row["warehouse"])
		if key not in seen:
			seen.add(key)
			pairs.append({"item_code": row["item_code"], "warehouse": row["warehouse"]})
	for row in zero_valuation:
		key = (row["item_code"], row.get("warehouse", ""))
		if key not in seen:
			seen.add(key)
			pairs.append({"item_code": row["item_code"], "warehouse": row.get("warehouse", "")})
	return pairs


def _build_summary(r):
	lines = [
		"Stock Valuation Guard — Nightly Run Report",
		f"Date/Time : {r['run_date']} {r['run_time']} UTC",
		f"Status    : {r['status']}",
		"",
		"DETECTION",
		f"  Negative-stock item/warehouse pairs : {r['negative_stock_items']}",
		f"  Zero incoming_rate invoice rows     : {r['zero_valuation_invoices']}",
		"",
		"CORRECTION",
		f"  Repost jobs created                 : {r['repost_jobs_created']}",
		f"  Repost jobs requeued (was stuck)    : {r['repost_jobs_requeued']}",
		f"  Repost jobs completed this run      : {r['repost_jobs_completed']}",
		f"  Repost jobs still failing           : {r['repost_jobs_failed']}",
	]
	if r["errors"]:
		lines += ["", "ERRORS"] + [f"  {e}" for e in r["errors"]]
	return "\n".join(lines)
