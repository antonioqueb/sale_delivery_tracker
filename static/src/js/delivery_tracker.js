/** @odoo-module **/

import { Component, useState, onWillUpdateProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class DeliveryTrackerWidget extends Component {
    static template = "sale_delivery_tracker.DeliveryTrackerWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.actionService = useService("action");

        // Debug: log all available data
        console.log("=== DELIVERY TRACKER DEBUG ===");
        console.log("props.name:", this.props.name);
        console.log("record.data keys:", Object.keys(this.props.record.data));
        console.log("raw value:", this.props.record.data[this.props.name]);
        console.log("typeof:", typeof this.props.record.data[this.props.name]);

        const data = this._parse(this.props.record.data[this.props.name]);
        console.log("parsed data:", JSON.stringify(data));

        this.state = useState({
            lines: data.lines,
            summary: data.summary,
            expanded: {},
        });
        onWillUpdateProps((next) => {
            console.log("=== TRACKER UPDATE ===");
            console.log("new raw value:", next.record.data[next.name]);
            const d = this._parse(next.record.data[next.name]);
            console.log("new parsed:", JSON.stringify(d));
            this.state.lines = d.lines;
            this.state.summary = d.summary;
        });
    }

    _defaultSummary() {
        return { total: 0, done: 0, active: 0, draft: 0, all_done: false };
    }

    _parse(value) {
        const empty = { lines: [], summary: this._defaultSummary() };
        try {
            console.log("_parse input:", value);
            if (!value || value === "false" || value === false) return empty;

            // Si ya es un objeto (Odoo a veces parsea automáticamente)
            let parsed = value;
            if (typeof value === "string") {
                parsed = JSON.parse(value);
            }

            console.log("_parse parsed type:", typeof parsed, Array.isArray(parsed));
            console.log("_parse parsed:", JSON.stringify(parsed).substring(0, 500));

            // Si es un array directo (por si el backend manda lista plana)
            if (Array.isArray(parsed)) {
                console.log("_parse: got array, wrapping");
                return {
                    lines: parsed,
                    summary: this._buildSummary(parsed),
                };
            }

            // Si es objeto con lines
            if (parsed && parsed.lines) {
                console.log("_parse: got object with lines:", parsed.lines.length);
                return {
                    lines: parsed.lines,
                    summary: Object.assign(this._defaultSummary(), parsed.summary || {}),
                };
            }

            console.log("_parse: no lines found, returning empty");
            return empty;
        } catch (e) {
            console.error("_parse error:", e);
            return empty;
        }
    }

    _buildSummary(lines) {
        const done = lines.filter(l => l.state === "done").length;
        const active = lines.filter(l => ["assigned", "confirmed", "waiting"].includes(l.state)).length;
        const draft = lines.filter(l => l.state === "draft").length;
        const total = lines.length;
        return { total, done, active, draft, all_done: done === total && total > 0 };
    }

    toggle(id) {
        this.state.expanded[id] = !this.state.expanded[id];
    }

    isOpen(id) {
        return !!this.state.expanded[id];
    }

    async openPicking(id) {
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "stock.picking",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    getProgressClass(state) {
        const map = { done: "pg-done", assigned: "pg-ready", confirmed: "pg-confirmed", waiting: "pg-waiting" };
        return map[state] || "pg-draft";
    }

    getStateClass(state) {
        const map = { done: "st-done", assigned: "st-ready", confirmed: "st-confirmed", waiting: "st-waiting", draft: "st-draft" };
        return map[state] || "st-draft";
    }

    getTypeIcon(code) {
        const map = { outgoing: "fa-truck", internal: "fa-exchange", incoming: "fa-arrow-down" };
        return map[code] || "fa-arrows-h";
    }

    getTypeLabel(code) {
        const map = { outgoing: "Salida", internal: "Interno", incoming: "Entrada" };
        return map[code] || code;
    }
}

registry.category("fields").add("delivery_tracker_widget", {
    component: DeliveryTrackerWidget,
});