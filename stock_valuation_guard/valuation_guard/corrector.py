"""
corrector.py — Creates and triggers Repost Item Valuation jobs.

ERPNext's repost engine (erpnext.stock.doctype.repost_item_valuation) is the
official mechanism for recalculating valuation_rate across the stock ledger.
We create entries for each problem item/warehouse pair and then call the engine
directly so fixes happen within the nightly window.
"""

from __future__ import unicode_literals

import traceback
from datetime import datetime, timedelta

import frappe

from stock_valuation_guard.valuation_guard.detector import get_current_repost_queue


def requeue_stuck_jobs(stuck_jobs: list) -> int:
	"""
	Reset Failed and perpetually-In-Progress jobs back to Queued so the
	repost engine will re-attempt them.

	Returns the number of jobs successfully requeued.
	"""
	requeued = 0
	for job in stuck_jobs:
		try:
			doc = frappe.get_doc("Repost Item Valuation", job["name"])
			if doc.status in ("Failed", "In Progress", "Queued"):
				doc.status = "Queued"
				doc.error_log = ""
				# Clear any stale lock timestamp
				if hasattr(doc, "repost_time_slot_start"):
					doc.repost_time_slot_start = None
				doc.save(ignore_permissions=True)
				requeued += 1
				frappe.logger("valuation_guard").info(
					f"Requeued stuck job: {job['name']} "
					f"(was {job['status']}, item={job.get('item_code')})"
				)
		except Exception:
			frappe.logger("valuation_guard").warning(
				f"Could not requeue job {job['name']}: {traceback.format_exc()}"
			)
	return requeued


def create_repost_entries(item_warehouse_pairs: list) -> int:
	"""
	For each (item_code, warehouse) pair not already in the Repost queue,
	create a new 'Repost Item Valuation' document.

	Uses 'based_on = Item and Warehouse' so the repost is scoped and fast.
	Posting date is set to 90 days ago to catch the full problem window.

	Returns the number of new entries created.
	"""
	existing_queue = get_current_repost_queue()
	created = 0

	# Lookback date — repost from 90 days before today to cover all affected SLEs
	posting_date = (datetime.today() - timedelta(days=90)).strftime("%Y-%m-%d")

	for pair in item_warehouse_pairs:
		item_code = pair.get("item_code", "")
		warehouse = pair.get("warehouse", "")

		if not item_code:
			continue

		key = (item_code, warehouse)
		if key in existing_queue:
			frappe.logger("valuation_guard").debug(
				f"Skipping {item_code}/{warehouse} — already in repost queue"
			)
			continue

		try:
			doc = frappe.get_doc(
				{
					"doctype": "Repost Item Valuation",
					"based_on": "Item and Warehouse",
					"item_code": item_code,
					"warehouse": warehouse or None,
					"posting_date": posting_date,
					"posting_time": "00:00:00",
					"status": "Queued",
					"allow_zero_rate": 0,
					"via_landed_cost_voucher": 0,
				}
			)
			doc.insert(ignore_permissions=True)
			created += 1
			frappe.logger("valuation_guard").info(
				f"Created repost entry for: {item_code} / {warehouse or 'ALL'}"
			)
		except frappe.exceptions.DuplicateEntryError:
			# Already exists — safe to ignore
			frappe.db.rollback()
		except Exception:
			frappe.logger("valuation_guard").warning(
				f"Could not create repost entry for {item_code}/{warehouse}: "
				+ traceback.format_exc()
			)
			frappe.db.rollback()

	return created


def trigger_repost_engine(timeout_minutes: int = 45) -> tuple:
	"""
	Directly invoke ERPNext's repost engine, which drains the Repost Item
	Valuation queue. This is identical to what the ERPNext scheduler calls
	hourly, but we call it immediately so the fix happens tonight.

	Returns (completed_count, failed_count) after the engine exits.
	"""
	try:
		from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import (
			repost_entries,
		)

		frappe.logger("valuation_guard").info(
			f"Triggering repost engine with timeout={timeout_minutes}min"
		)
		repost_entries(timeout=timeout_minutes * 60)

	except Exception:
		frappe.logger("valuation_guard").error(
			"repost_entries() raised an exception:\n" + traceback.format_exc()
		)

	# Count results after the engine finishes
	completed = frappe.db.count("Repost Item Valuation", filters={"status": "Completed"}) or 0
	failed = frappe.db.count("Repost Item Valuation", filters={"status": "Failed"}) or 0
	queued = frappe.db.count("Repost Item Valuation", filters={"status": "Queued"}) or 0

	frappe.logger("valuation_guard").info(
		f"Repost engine finished. Completed={completed}, Failed={failed}, "
		f"Still Queued={queued}"
	)
	return completed, failed
