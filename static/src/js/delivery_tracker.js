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
        const parsed = this._parseData(this.props.record.data[this.props.name]);
        this.state = useState({
            lines: parsed,
            summaryParts: this._buildSummary(parsed),
            expandedRows: {},
        });
        onWillUpdateProps((nextProps) => {
            const data = this._parseData(nextProps.record.data[nextProps.name]);
            this.state.lines = data;
            this.state.summaryParts = this._buildSummary(data);
        });
    }

    _parseData(value) {
        try {
            if (!value) return [];
            return JSON.parse(value);
        } catch (e) {
            return [];
        }
    }

    _buildSummary(lines) {
        if (!lines.length) return [];
        const done = lines.filter(l => l.state === 'done').length;
        const inProgress = lines.filter(l => ['assigned', 'confirmed', 'waiting'].includes(l.state)).length;
        const draft = lines.filter(l => l.state === 'draft').length;
        const parts = [];
        if (done) parts.push({ count: done, label: 'completada(s)', cls: 'chip-done' });
        if (inProgress) parts.push({ count: inProgress, label: 'en proceso', cls: 'chip-progress' });
        if (draft) parts.push({ count: draft, label: 'borrador', cls: 'chip-draft' });
        return parts;
    }

    toggleExpand(lineId) {
        this.state.expandedRows[lineId] = !this.state.expandedRows[lineId];
    }

    isExpanded(lineId) {
        return !!this.state.expandedRows[lineId];
    }

    async onClickPicking(pickingId) {
        await this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'stock.picking',
            res_id: pickingId,
            views: [[false, 'form']],
            target: 'current',
        });
    }
}

registry.category("fields").add("delivery_tracker_widget", {
    component: DeliveryTrackerWidget,
});