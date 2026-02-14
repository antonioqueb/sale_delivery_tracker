/** @odoo-module **/

import { Component, useState, onWillUpdateProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// ============================================
// DELIVERY TRACKER WIDGET (full cards view)
// ============================================

class DeliveryTrackerWidget extends Component {
    static template = "sale_delivery_tracker.DeliveryTrackerWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.actionService = useService("action");
        this.state = useState({
            lines: this._parseData(this.props.record.data[this.props.name]),
        });
        onWillUpdateProps((nextProps) => {
            this.state.lines = this._parseData(nextProps.record.data[nextProps.name]);
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

    getProgressClass(line) {
        if (line.state === 'done') return 'fill-success';
        if (line.state === 'assigned') return 'fill-primary';
        return 'fill-warning';
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


// ============================================
// DELIVERY SUMMARY BADGE (header indicator)
// ============================================

class DeliverySummaryBadge extends Component {
    static template = "sale_delivery_tracker.DeliverySummaryBadge";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            summary: this.props.record.data[this.props.name] || '',
        });
        onWillUpdateProps((nextProps) => {
            this.state.summary = nextProps.record.data[nextProps.name] || '';
        });
    }

    get badgeClass() {
        const s = this.state.summary;
        if (!s || s === 'Sin entregas') return 'summary-empty';
        if (s.startsWith('✓')) return 'summary-done';
        return 'summary-progress';
    }

    get badgeIcon() {
        const s = this.state.summary;
        if (!s || s === 'Sin entregas') return 'fa-clock-o';
        if (s.startsWith('✓')) return 'fa-check-circle';
        return 'fa-spinner fa-pulse';
    }
}


// Register widgets
registry.category("fields").add("delivery_tracker_widget", {
    component: DeliveryTrackerWidget,
});

registry.category("fields").add("delivery_summary_badge", {
    component: DeliverySummaryBadge,
});
