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
        const data = this._parse(this.props.record.data[this.props.name]);
        this.state = useState({
            lines: data.lines,
            summary: data.summary,
            expanded: {},
        });
        onWillUpdateProps((next) => {
            const d = this._parse(next.record.data[next.name]);
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
            if (!value || value === "false") return empty;
            const parsed = JSON.parse(value);
            return {
                lines: parsed.lines || [],
                summary: Object.assign(this._defaultSummary(), parsed.summary || {}),
            };
        } catch {
            return empty;
        }
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