## ./__init__.py
```py
from . import models
```

## ./__manifest__.py
```py
{
    'name': 'Sale Delivery Tracker',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'summary': 'Track delivery status directly from Sale Orders with visual indicators',
    'description': """
        Shows the last relevant delivery document per flow in the sale order,
        with a visual progress indicator showing delivery stages and quantities.
        Supports multi-step delivery (Pick → Pack → Ship) and partial deliveries.
    """,
    'author': 'Alphaqueb Consulting',
    'website': 'https://www.alphaqueb.com',
    'depends': ['sale_stock', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_delivery_tracker/static/src/css/delivery_tracker.css',
            'sale_delivery_tracker/static/src/js/delivery_tracker.js',
            'sale_delivery_tracker/static/src/xml/delivery_tracker.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

## ./models/__init__.py
```py
from . import sale_order
```

## ./models/sale_order.py
```py
from odoo import models, fields, api
import json


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delivery_tracker_data = fields.Text(
        string='Delivery Tracker Data',
        compute='_compute_delivery_tracker_data',
    )
    delivery_tracker_summary = fields.Char(
        string='Delivery Status Summary',
        compute='_compute_delivery_tracker_data',
    )

    @api.depends(
        'picking_ids',
        'picking_ids.state',
        'picking_ids.move_ids',
        'picking_ids.move_ids.quantity',
        'picking_ids.move_ids.product_uom_qty',
        'picking_ids.move_ids.move_dest_ids',
        'picking_ids.move_ids.move_orig_ids',
    )
    def _compute_delivery_tracker_data(self):
        for order in self:
            pickings = order.picking_ids.filtered(lambda p: p.state != 'cancel')
            if not pickings:
                order.delivery_tracker_data = json.dumps({
                    'lines': [],
                    'summary': {
                        'total': 0,
                        'done': 0,
                        'active': 0,
                        'draft': 0,
                        'all_done': False,
                    },
                })
                order.delivery_tracker_summary = ''
                continue

            tracker_lines = order._get_tracker_lines(pickings)
            summary_data = order._get_summary_data(tracker_lines)
            order.delivery_tracker_data = json.dumps({
                'lines': tracker_lines,
                'summary': summary_data,
            })
            order.delivery_tracker_summary = order._get_summary_text(tracker_lines)

    def _get_summary_data(self, tracker_lines):
        done = len([l for l in tracker_lines if l['state'] == 'done'])
        active = len([l for l in tracker_lines if l['state'] in ('assigned', 'confirmed', 'waiting')])
        draft = len([l for l in tracker_lines if l['state'] == 'draft'])
        total = len(tracker_lines)
        return {
            'total': total,
            'done': done,
            'active': active,
            'draft': draft,
            'all_done': done == total and total > 0,
        }

    def _get_tracker_lines(self, pickings):
        all_moves = pickings.mapped('move_ids').filtered(lambda m: m.state != 'cancel')

        picking_next = {}
        for picking in pickings:
            next_pickings = self.env['stock.picking']
            for move in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
                for dest_move in move.move_dest_ids:
                    if dest_move.picking_id and dest_move.picking_id.state != 'cancel':
                        next_pickings |= dest_move.picking_id
            picking_next[picking.id] = next_pickings

        result = []
        shown_picking_ids = set()

        sorted_pickings = pickings.sorted(
            key=lambda p: (
                0 if p.picking_type_id.code == 'outgoing' else
                1 if p.picking_type_id.code == 'internal' else 2,
                p.scheduled_date or fields.Datetime.now(),
            )
        )

        for picking in sorted_pickings:
            if picking.id in shown_picking_ids:
                continue

            next_picks = picking_next.get(picking.id, self.env['stock.picking'])

            if picking.state == 'done' and next_picks:
                fully_consumed = True
                for move in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
                    dest_moves = move.move_dest_ids.filtered(
                        lambda m: m.state != 'cancel' and m.picking_id and m.picking_id.state != 'cancel'
                    )
                    if not dest_moves:
                        fully_consumed = False
                        break
                    dest_qty = sum(dest_moves.mapped('product_uom_qty'))
                    if dest_qty < move.quantity:
                        fully_consumed = False
                        break

                if fully_consumed:
                    for np in next_picks:
                        shown_picking_ids.add(np.id)
                        result.append(self._picking_to_tracker_line(np))
                    shown_picking_ids.add(picking.id)
                    continue

            if picking.id not in shown_picking_ids:
                shown_picking_ids.add(picking.id)
                result.append(self._picking_to_tracker_line(picking))

        seen = set()
        unique_result = []
        for line in result:
            if line['id'] not in seen:
                seen.add(line['id'])
                unique_result.append(line)

        unique_result.sort(key=lambda x: (
            0 if x['state'] == 'done' else 1 if x['state'] == 'assigned' else 2,
            x['name'],
        ))

        return unique_result

    def _picking_to_tracker_line(self, picking):
        total_demand = sum(picking.move_ids.filtered(
            lambda m: m.state != 'cancel'
        ).mapped('product_uom_qty'))
        total_done = sum(picking.move_ids.filtered(
            lambda m: m.state != 'cancel'
        ).mapped('quantity'))

        picking_type = picking.picking_type_id
        stage_label = picking_type.name or 'Transfer'
        type_code = picking_type.code or 'internal'

        state_map = {
            'draft': {'label': 'Borrador', 'color': 'secondary'},
            'waiting': {'label': 'En espera', 'color': 'warning'},
            'confirmed': {'label': 'Confirmado', 'color': 'info'},
            'assigned': {'label': 'Listo', 'color': 'primary'},
            'done': {'label': 'Realizado', 'color': 'success'},
        }
        state_info = state_map.get(picking.state, {'label': picking.state, 'color': 'secondary'})

        progress = 0
        if total_demand > 0:
            progress = round((total_done / total_demand) * 100, 1)
        if picking.state == 'done':
            progress = 100

        icon_map = {
            'internal': 'fa-exchange',
            'outgoing': 'fa-truck',
            'incoming': 'fa-arrow-down',
        }
        icon = icon_map.get(type_code, 'fa-box')

        products = []
        for move in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
            prod_progress = 0
            if move.product_uom_qty > 0:
                prod_progress = round((move.quantity / move.product_uom_qty) * 100, 1)
            if move.state == 'done':
                prod_progress = 100

            products.append({
                'name': move.product_id.display_name,
                'demand': move.product_uom_qty,
                'done': move.quantity,
                'uom': move.product_uom.name,
                'progress': prod_progress,
            })

        return {
            'id': picking.id,
            'name': picking.name,
            'stage': stage_label,
            'type_code': type_code,
            'state': picking.state,
            'state_label': state_info['label'],
            'state_color': state_info['color'],
            'scheduled_date': picking.scheduled_date.strftime('%d/%m/%Y') if picking.scheduled_date else '',
            'date_done': picking.date_done.strftime('%d/%m/%Y %H:%M') if picking.date_done else '',
            'progress': progress,
            'total_demand': total_demand,
            'total_done': total_done,
            'icon': icon,
            'products': products,
            'partner': picking.partner_id.name or '',
        }

    def _get_summary_text(self, tracker_lines):
        if not tracker_lines:
            return 'Sin entregas'

        done_count = len([l for l in tracker_lines if l['state'] == 'done'])
        total = len(tracker_lines)

        if done_count == total:
            return f'✓ {total} entrega(s) completada(s)'

        in_progress = len([l for l in tracker_lines if l['state'] in ('assigned', 'confirmed', 'waiting')])
        parts = []
        if done_count:
            parts.append(f'{done_count} completada(s)')
        if in_progress:
            parts.append(f'{in_progress} en proceso')
        pending = total - done_count - in_progress
        if pending:
            parts.append(f'{pending} pendiente(s)')

        return ' | '.join(parts)

```

## ./static/src/js/delivery_tracker.js
```js
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
});```

## ./static/src/xml/delivery_tracker.xml
```xml
<?xml version="1.0" encoding="UTF-8"?>
<templates xml:space="preserve">

    <t t-name="sale_delivery_tracker.DeliveryTrackerWidget">
        <div class="dt-root">

            <t t-if="!state.lines.length">
                <div class="dt-empty">
                    <i class="fa fa-truck dt-empty-icon"></i>
                    <span>Sin entregas programadas</span>
                </div>
            </t>

            <t t-if="state.lines.length">

                <!-- Summary -->
                <div class="dt-summary">
                    <span class="dt-summary-label">Entregas</span>
                    <t t-if="state.summary.all_done">
                        <span class="dt-badge bg-done"><i class="fa fa-check"/> Todo entregado</span>
                    </t>
                    <t t-else="">
                        <t t-if="state.summary.done">
                            <span class="dt-badge bg-done"><t t-esc="state.summary.done"/> completada(s)</span>
                        </t>
                        <t t-if="state.summary.active">
                            <span class="dt-badge bg-active"><t t-esc="state.summary.active"/> en proceso</span>
                        </t>
                        <t t-if="state.summary.draft">
                            <span class="dt-badge bg-draft"><t t-esc="state.summary.draft"/> borrador</span>
                        </t>
                    </t>
                </div>

                <!-- Table -->
                <table class="dt-table">
                    <thead>
                        <tr>
                            <th class="dt-th-toggle"></th>
                            <th>Documento</th>
                            <th>Tipo</th>
                            <th>Estado</th>
                            <th class="dt-th-progress">Progreso</th>
                            <th class="dt-th-num">Demanda</th>
                            <th class="dt-th-num">Hecho</th>
                            <th>Fecha</th>
                            <th class="dt-th-action"></th>
                        </tr>
                    </thead>
                    <tbody>
                        <t t-foreach="state.lines" t-as="line" t-key="line.id">

                            <tr t-attf-class="dt-row #{line.state === 'done' ? 'dt-row-done' : ''}">
                                <td class="dt-td-toggle" t-on-click.stop="() => this.toggle(line.id)">
                                    <i t-attf-class="fa #{this.isOpen(line.id) ? 'fa-caret-down' : 'fa-caret-right'} dt-caret"></i>
                                </td>
                                <td class="dt-td-doc" t-on-click="() => this.openPicking(line.id)">
                                    <span class="dt-doc-link" t-esc="line.name"/>
                                </td>
                                <td>
                                    <span t-attf-class="dt-type tp-#{line.type_code}">
                                        <i t-attf-class="fa #{this.getTypeIcon(line.type_code)}"></i>
                                        <t t-esc="this.getTypeLabel(line.type_code)"/>
                                    </span>
                                </td>
                                <td>
                                    <span t-attf-class="dt-state #{this.getStateClass(line.state)}">
                                        <t t-esc="line.state_label"/>
                                    </span>
                                </td>
                                <td class="dt-td-progress">
                                    <div class="dt-bar-wrap">
                                        <div class="dt-bar">
                                            <div t-attf-class="dt-bar-fill #{this.getProgressClass(line.state)}"
                                                 t-attf-style="width:#{line.progress}%"></div>
                                        </div>
                                        <span class="dt-bar-pct"><t t-esc="line.progress"/>%</span>
                                    </div>
                                </td>
                                <td class="dt-td-num" t-esc="line.total_demand"/>
                                <td t-attf-class="dt-td-num #{line.total_done >= line.total_demand and line.total_demand > 0 ? 'dt-num-ok' : line.total_done > 0 ? 'dt-num-partial' : ''}">
                                    <t t-esc="line.total_done"/>
                                </td>
                                <td class="dt-td-date">
                                    <t t-if="line.date_done">
                                        <i class="fa fa-check-circle dt-icon-done"></i>
                                        <t t-esc="line.date_done"/>
                                    </t>
                                    <t t-else="">
                                        <i class="fa fa-calendar-o dt-icon-sched"></i>
                                        <t t-esc="line.scheduled_date"/>
                                    </t>
                                </td>
                                <td class="dt-td-action">
                                    <button class="dt-btn-open" t-on-click.stop="() => this.openPicking(line.id)" title="Abrir">
                                        <i class="fa fa-external-link"></i>
                                    </button>
                                </td>
                            </tr>

                            <!-- Expanded products -->
                            <t t-if="this.isOpen(line.id)">
                                <t t-foreach="line.products" t-as="p" t-key="p.name + '_' + p_index">
                                    <tr class="dt-sub-row">
                                        <td></td>
                                        <td class="dt-sub-product" t-att-title="p.name">
                                            <i class="fa fa-cube dt-sub-icon"></i>
                                            <t t-esc="p.name"/>
                                        </td>
                                        <td class="dt-sub-muted" t-esc="p.uom"/>
                                        <td></td>
                                        <td class="dt-td-progress">
                                            <div class="dt-bar-wrap">
                                                <div class="dt-bar dt-bar-sm">
                                                    <div t-attf-class="dt-bar-fill #{this.getProgressClass(line.state)}"
                                                         t-attf-style="width:#{p.progress}%"></div>
                                                </div>
                                            </div>
                                        </td>
                                        <td class="dt-td-num" t-esc="p.demand"/>
                                        <td t-attf-class="dt-td-num #{p.done >= p.demand and p.demand > 0 ? 'dt-num-ok' : p.done > 0 ? 'dt-num-partial' : ''}">
                                            <t t-esc="p.done"/>
                                        </td>
                                        <td colspan="2"></td>
                                    </tr>
                                </t>
                            </t>

                        </t>
                    </tbody>
                </table>

            </t>
        </div>
    </t>

</templates>```

## ./views/sale_order_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="view_order_form_delivery_tracker" model="ir.ui.view">
        <field name="name">sale.order.form.delivery.tracker</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="priority">50</field>
        <field name="arch" type="xml">
            <xpath expr="//notebook" position="after">
                <div class="o_group" style="width: 100%;">
                    <field name="delivery_tracker_data" widget="delivery_tracker_widget" nolabel="1"/>
                </div>
            </xpath>
        </field>
    </record>

</odoo>```

