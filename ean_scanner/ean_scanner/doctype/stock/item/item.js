// Copyright (c) 2025, Samuel Helbling and contributors
// For license information, please see license.txt

frappe.ui.form.on('Item', {
    refresh: function(frm) {
        // Check if the item has at least one EAN barcode
        const hasEanBarcode = frm.doc.barcodes && frm.doc.barcodes.some(b => 
            b.barcode && b.barcode_type === 'EAN');

        if (hasEanBarcode) {
            frm.add_custom_button(__('Update from Open Food Facts'), function() {
                frappe.call({
                    method: 'ean_scanner.ean_scanner.doctype.ean_scanner.ean_scanner.update_item_from_off',
                    args: {
                        item_code: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __('Fetching data from Open Food Facts...'),
                    callback: function(r) {
                        if (r.message) {
                            frappe.show_alert({
                                message: __('Item updated successfully'),
                                indicator: 'green'
                            });
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Actions'));
        }
    }
}); 