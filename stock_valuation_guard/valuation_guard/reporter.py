"""
reporter.py — Saves the run result to the Valuation Guard Log DocType only.
No emails are sent; results are visible in the ERPNext UI under Valuation Guard Log.
"""

from __future__ import unicode_literals

import traceback

import frappe


def save_log(result: dict):
	"""
	Persist the nightly run result to the `Valuation Guard Log` DocType.
	Provides a visible audit trail in the ERPNext UI.
	"""
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Valuation Guard Log",
				"run_date": result.get("run_date"),
				"run_time": result.get("run_time"),
				"negative_stock_items": result.get("negative_stock_items", 0),
				"zero_valuation_invoices": result.get("zero_valuation_invoices", 0),
				"repost_jobs_created": result.get("repost_jobs_created", 0),
				"repost_jobs_requeued": result.get("repost_jobs_requeued", 0),
				"repost_jobs_completed": result.get("repost_jobs_completed", 0),
				"repost_jobs_failed": result.get("repost_jobs_failed", 0),
				"status": result.get("status", "Unknown"),
				"summary": result.get("summary", ""),
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger("valuation_guard").info(f"Saved Valuation Guard Log: {doc.name}")
	except Exception:
		frappe.logger("valuation_guard").error(
			"Failed to save Valuation Guard Log:\n" + traceback.format_exc()
		)


def send_summary_email(result: dict):
	"""No-op — email notifications disabled. Logs are in Valuation Guard Log DocType."""
	pass
