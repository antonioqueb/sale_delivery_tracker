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