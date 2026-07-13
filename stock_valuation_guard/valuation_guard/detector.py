"""
detector.py — SQL-based detection of stock valuation problems.

All queries are read-only and target the active Frappe DB connection.
"""

from __future__ import unicode_literals

import frappe


def find_negative_stock_items(days_back: int = 90) -> list:
	"""
	Return all (item_code, warehouse, first_negative_date) tuples where the
	running qty_after_transaction went below zero within the last `days_back` days.

	These are the items most likely to have corrupted valuation_rate values
	because ERPNext cannot calculate a proper FIFO/Moving Average cost when
	stock doesn't exist at the time of the outbound transaction.
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			item_code,
			warehouse,
			MIN(posting_date) AS first_negative,
			COUNT(*)          AS occurrences
		FROM `tabStock Ledger Entry`
		WHERE qty_after_transaction < 0
		  AND is_cancelled = 0
		  AND posting_date >= DATE_SUB(CURDATE(), INTERVAL %(days_back)s DAY)
		GROUP BY item_code, warehouse
		ORDER BY occurrences DESC
		""",
		{"days_back": days_back},
		as_dict=True,
	)

	frappe.logger("valuation_guard").debug(
		f"find_negative_stock_items: found {len(rows)} item/warehouse pairs"
	)
	return rows


def find_zero_valuation_items(days_back: int = 90) -> list:
	"""
	Return all Sales Invoice rows where incoming_rate = 0 within the last
	`days_back` days. A zero incoming_rate means cost was not captured at the
	time of sale — this directly causes Gross Profit to show 0 or negative.
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			sii.item_code,
			COALESCE(sii.warehouse, si.set_warehouse, 'Unknown') AS warehouse,
			MIN(si.posting_date) AS first_zero_date,
			COUNT(*)             AS occurrences,
			AVG(sii.rate)        AS avg_selling_rate
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
		  AND sii.incoming_rate = 0
		  AND si.posting_date >= DATE_SUB(CURDATE(), INTERVAL %(days_back)s DAY)
		GROUP BY sii.item_code, COALESCE(sii.warehouse, si.set_warehouse, 'Unknown')
		ORDER BY occurrences DESC
		""",
		{"days_back": days_back},
		as_dict=True,
	)

	frappe.logger("valuation_guard").debug(
		f"find_zero_valuation_items: found {len(rows)} item/warehouse pairs"
	)
	return rows


def find_stuck_repost_jobs(days_back: int = 14) -> list:
	"""
	Return names of Repost Item Valuation documents stuck in Queued, In Progress,
	or Failed status. ERPNext's scheduler should drain these automatically, but
	bulk imports and worker crashes often leave them orphaned.
	"""
	rows = frappe.db.sql(
		"""
		SELECT name, item_code, warehouse, status, error_log, creation
		FROM `tabRepost Item Valuation`
		WHERE status IN ('Queued', 'In Progress', 'Failed')
		  AND creation >= DATE_SUB(NOW(), INTERVAL %(days_back)s DAY)
		ORDER BY creation DESC
		""",
		{"days_back": days_back},
		as_dict=True,
	)

	frappe.logger("valuation_guard").debug(
		f"find_stuck_repost_jobs: found {len(rows)} stuck jobs"
	)
	return rows


def get_current_repost_queue() -> dict:
	"""
	Return a dict of (item_code, warehouse) -> repost_doc_name for all jobs
	currently Queued or In Progress, so corrector.py can skip duplicates.
	"""
	rows = frappe.db.sql(
		"""
		SELECT name, item_code, warehouse
		FROM `tabRepost Item Valuation`
		WHERE status IN ('Queued', 'In Progress')
		""",
		as_dict=True,
	)
	return {(r["item_code"], r.get("warehouse", "")): r["name"] for r in rows}
