# Copyright (c) 2025, Samuel Helbling and contributors
# For license information, please see license.txt

import frappe
import requests
import json
import base64
from io import BytesIO
from frappe.model.document import Document
from frappe.utils import now_datetime


class EANScanner(Document):
	def validate(self):
		# Make sure a warehouse is selected
		if not self.warehouse:
			frappe.throw("Please select a warehouse")

	def on_update(self):
		# Process scan input when fields are updated
		if self.check_in_scan:
			self._process_scan(self.check_in_scan, "in")
			self.check_in_scan = ""  # Clear the field after processing
		
		if self.check_out_scan:
			self._process_scan(self.check_out_scan, "out")
			self.check_out_scan = ""  # Clear the field after processing
			
	def _process_scan(self, barcode, scan_type):
		"""Process a barcode scan and create appropriate stock entries"""
		item_code = self._get_item_code_from_barcode(barcode)
		
		if not item_code:
			# Item doesn't exist yet, get info from API and create it
			if self.create_not_existing_item:
				item_code = self._create_item_from_api(barcode)
				if not item_code:
					frappe.msgprint(f"Could not create item for barcode {barcode}")
					return
			else:
				frappe.msgprint(f"No item found for barcode {barcode}")
				return
		
		# Create stock entry based on scan type
		if scan_type == "in":
			self._create_stock_entry(item_code, "Material Receipt")
			frappe.msgprint(f"Item {item_code} added to stock in {self.warehouse}")
		else:
			self._create_stock_entry(item_code, "Material Issue")
			frappe.msgprint(f"Item {item_code} removed from stock in {self.warehouse}")
	
	def _get_item_code_from_barcode(self, barcode):
		"""Get item code from barcode"""
		item_code = frappe.db.get_value("Item Barcode", {"barcode": barcode}, "parent")
		return item_code
	
	def _create_item_from_api(self, barcode):
		"""Create a new item using data from Open Food Facts API"""
		try:
			# Call Open Food Facts API
			api_url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
			response = requests.get(api_url, headers={"User-Agent": "EANScanner/1.0 (eanscanner@example.com)"})
			
			if response.status_code != 200:
				frappe.log_error(f"API returned status code {response.status_code}", "EAN Scanner Error")
				return None
			
			data = response.json()
			
			# Check if the product was found
			if data.get("status") != 1:
				frappe.msgprint(f"Product not found in Open Food Facts database: {barcode}")
				return None
			
			product = data.get("product", {})
			
			# Create item
			item = frappe.new_doc("Item")
			item.item_code = barcode
			item.item_name = product.get("product_name") or f"Product {barcode}"
			item.description = product.get("generic_name") or product.get("product_name") or f"Product {barcode}"
			
			# Process category hierarchy if available
			if product.get("categories_hierarchy"):
				item_group = self._process_category_hierarchy(product["categories_hierarchy"])
				item.item_group = item_group
			else:
				item.item_group = "All Item Groups"  # Default item group
				
			item.stock_uom = "Nos"  # Default UOM
			
			# Add barcode
			item.append("barcodes", {
				"barcode": barcode,
				"barcode_type": "EAN"
			})
			
			# Set item defaults
			item.append("item_defaults", {
				"default_warehouse": self.warehouse,
				"company": frappe.defaults.get_user_default("Company")
			})
			
			# Add additional product information if available
			if product.get("brands"):
				brand_name = product.get("brands").split(",")[0].strip()
				# Check if brand exists, create it if it doesn't
				if not frappe.db.exists("Brand", brand_name):
					self._create_brand(brand_name)
				item.brand = brand_name
			
			# Set default valuation rate to prevent valuation errors
			item.valuation_rate = 1.0
			item.standard_rate = 1.0
			
			# Attach product image if available
			if product.get("image_url"):
				self._attach_image_to_item(item, product["image_url"])
			
			# Save the item
			item.insert(ignore_permissions=True)
			
			frappe.msgprint(f"New item created: {item.item_name}")
			return item.item_code
			
		except Exception as e:
			frappe.log_error(f"Error creating item: {e}", "EAN Scanner Error")
			return None
	
	def _process_category_hierarchy(self, categories):
		"""
		Process category hierarchy from Open Food Facts and create item groups if needed.
		Returns the name of the most specific (last) category to use as item group.
		"""
		if not categories or not isinstance(categories, list):
			return "All Item Groups"
		
		parent_group = "All Item Groups"
		last_group = parent_group
		
		for category in categories:
			# Clean up category name
			category_name = category.replace("en:", "").replace("-", " ").title()
			
			# Check if this item group exists
			if not frappe.db.exists("Item Group", category_name):
				# Create the item group
				try:
					item_group = frappe.new_doc("Item Group")
					item_group.item_group_name = category_name
					item_group.parent_item_group = parent_group
					item_group.is_group = 1  # It's a group that can have children
					item_group.insert(ignore_permissions=True)
					frappe.msgprint(f"Created new Item Group: {category_name}")
				except Exception as e:
					frappe.log_error(f"Error creating Item Group {category_name}: {e}", "EAN Scanner Error")
					continue
			
			# Update parent for next iteration
			parent_group = category_name
			last_group = category_name
		
		return last_group
	
	def _attach_image_to_item(self, item, image_url):
		"""Download and attach image to the item"""
		try:
			# Download the image
			response = requests.get(image_url, timeout=10)
			if response.status_code != 200:
				return
			
			# Set the image field to the downloaded image URL
			item.image = image_url
			
			# Additionally store image as a file attachment
			file_name = f"item_{item.item_code}_image.jpg"
			
			# Create file doc and attach it to the item
			file_doc = frappe.get_doc({
				"doctype": "File",
				"file_name": file_name,
				"content": response.content,
				"attached_to_doctype": "Item",
				"attached_to_name": item.item_code,
				"attached_to_field": "image",
				"is_private": 0
			})
			file_doc.save(ignore_permissions=True)
			
		except Exception as e:
			frappe.log_error(f"Error attaching image: {e}", "EAN Scanner Error")
	
	def _create_brand(self, brand_name):
		"""Create a new brand if it doesn't exist"""
		try:
			brand = frappe.new_doc("Brand")
			brand.brand = brand_name
			brand.description = f"Auto-created by EAN Scanner from Open Food Facts data"
			brand.insert(ignore_permissions=True)
			frappe.msgprint(f"New brand created: {brand_name}")
			return brand.name
		except Exception as e:
			frappe.log_error(f"Error creating brand: {e}", "EAN Scanner Error")
			return None
	
	def _create_stock_entry(self, item_code, purpose):
		"""Create a stock entry to add or remove item from inventory"""
		stock_entry = frappe.new_doc("Stock Entry")
		stock_entry.purpose = purpose
		stock_entry.company = frappe.defaults.get_user_default("Company")
		stock_entry.set_stock_entry_type()
		stock_entry.posting_date = now_datetime().date()
		stock_entry.posting_time = now_datetime().time()
		
		# Add item to stock entry
		item_row = stock_entry.append("items", {
			"item_code": item_code,
			"qty": 1,
			"allow_zero_valuation_rate": 1  # Allow zero valuation rate to avoid errors
		})
		
		# Set source/target warehouse based on purpose
		if purpose == "Material Receipt":
			item_row.t_warehouse = self.warehouse
			# For incoming items, set a basic rate to establish valuation
			item_row.basic_rate = 1.0
		else:
			item_row.s_warehouse = self.warehouse
		
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		
		return stock_entry.name
