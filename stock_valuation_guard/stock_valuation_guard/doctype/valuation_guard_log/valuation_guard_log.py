# Copyright (c) 2026, Havano and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ValuationGuardLog(Document):
	"""
	Audit log for each nightly run of the Stock Valuation Guard.
	Documents are created programmatically by reporter.py — not by users.
	"""

	def get_status_indicator(self):
		return {
			"Success": "green",
			"Partial": "orange",
			"Failed": "red",
		}.get(self.status, "gray")
