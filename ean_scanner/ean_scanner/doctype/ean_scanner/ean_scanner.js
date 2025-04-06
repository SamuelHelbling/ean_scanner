// Copyright (c) 2025, Samuel Helbling and contributors
// For license information, please see license.txt

frappe.ui.form.on("EAN Scanner", {
	refresh(frm) {
		frm.disable_save();
		
		// Focus on check-in field by default
		setTimeout(() => {
			frm.fields_dict.check_in_scan.df.hidden = 0;
			frm.refresh_field("check_in_scan");
			frm.fields_dict.check_in_scan.set_focus();
		}, 200);
	},
	
	check_in_scan(frm) {
		if (frm.doc.check_in_scan && frm.doc.check_in_scan.length > 7) {
			frm.save();
		}
	},
	
	check_out_scan(frm) {
		if (frm.doc.check_out_scan && frm.doc.check_out_scan.length > 7) {
			frm.save();
		}
	}
});
