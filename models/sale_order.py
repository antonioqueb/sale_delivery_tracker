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
                order.delivery_tracker_data = json.dumps([])
                order.delivery_tracker_summary = ''
                continue

            tracker_lines = order._get_tracker_lines(pickings)
            order.delivery_tracker_data = json.dumps(tracker_lines)
            order.delivery_tracker_summary = order._get_summary_text(tracker_lines)

    def _get_tracker_lines(self, pickings):
        """
        Core logic: For each delivery flow, only show the LAST document.
        
        A "flow" is a chain of pickings linked by move_dest_ids/move_orig_ids.
        For each chain, we only show the most advanced picking (the one closest
        to the customer). If a picking is fully transferred and its moves have
        all been consumed by a next-step picking, we skip it and show the next one.
        
        For partial deliveries, we show:
        - The last document in each completed/in-progress chain
        - Any pending picking that still has remaining qty to process
        """
        # Build chains: group pickings by their flow
        # A chain is: pick -> pack -> ship (or any subset)
        # We want the "leaf" pickings - those whose moves don't feed into another picking
        # OR those that still have pending quantities

        all_moves = pickings.mapped('move_ids').filtered(lambda m: m.state != 'cancel')
        
        # Build a map of picking -> next pickings (via move_dest_ids)
        picking_next = {}
        for picking in pickings:
            next_pickings = self.env['stock.picking']
            for move in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
                for dest_move in move.move_dest_ids:
                    if dest_move.picking_id and dest_move.picking_id.state != 'cancel':
                        next_pickings |= dest_move.picking_id
            picking_next[picking.id] = next_pickings

        # Find "leaf" pickings per flow: pickings that have no next picking,
        # OR pickings where not all qty has been consumed by next step
        result = []
        shown_picking_ids = set()

        # Strategy: walk from the end (outgoing/customer pickings) backwards
        # Sort pickings by sequence/type to process outgoing first
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

            # Check if this picking has a "next" picking that already handles its qty
            next_picks = picking_next.get(picking.id, self.env['stock.picking'])
            
            if picking.state == 'done' and next_picks:
                # This picking is done and has a next step
                # Check if ALL its quantity was consumed by next pickings
                fully_consumed = True
                for move in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
                    dest_moves = move.move_dest_ids.filtered(
                        lambda m: m.state != 'cancel' and m.picking_id and m.picking_id.state != 'cancel'
                    )
                    if not dest_moves:
                        fully_consumed = False
                        break
                    # Check if destination moves account for the full qty
                    dest_qty = sum(dest_moves.mapped('product_uom_qty'))
                    if dest_qty < move.quantity:
                        fully_consumed = False
                        break

                if fully_consumed:
                    # Skip this picking, show the next ones instead
                    for np in next_picks:
                        shown_picking_ids.add(np.id)
                        result.append(self._picking_to_tracker_line(np))
                    shown_picking_ids.add(picking.id)
                    continue

            # This picking is either:
            # - A leaf (no next picking)
            # - Partially consumed (show it for remaining qty)
            # - Not yet done
            if picking.id not in shown_picking_ids:
                shown_picking_ids.add(picking.id)
                result.append(self._picking_to_tracker_line(picking))

        # Deduplicate by picking id
        seen = set()
        unique_result = []
        for line in result:
            if line['id'] not in seen:
                seen.add(line['id'])
                unique_result.append(line)

        # Sort: done first, then by type (outgoing before internal), then by name
        unique_result.sort(key=lambda x: (
            0 if x['state'] == 'done' else 1 if x['state'] == 'assigned' else 2,
            x['name'],
        ))

        return unique_result

    def _picking_to_tracker_line(self, picking):
        """Convert a picking to a tracker line dict for the widget."""
        # Calculate quantities
        total_demand = sum(picking.move_ids.filtered(
            lambda m: m.state != 'cancel'
        ).mapped('product_uom_qty'))
        total_done = sum(picking.move_ids.filtered(
            lambda m: m.state != 'cancel'
        ).mapped('quantity'))

        # Determine stage label
        picking_type = picking.picking_type_id
        stage_label = picking_type.name or 'Transfer'
        type_code = picking_type.code or 'internal'

        # State mapping for display
        state_map = {
            'draft': {'label': 'Borrador', 'color': 'secondary'},
            'waiting': {'label': 'En espera', 'color': 'warning'},
            'confirmed': {'label': 'Confirmado', 'color': 'info'},
            'assigned': {'label': 'Listo', 'color': 'primary'},
            'done': {'label': 'Realizado', 'color': 'success'},
        }
        state_info = state_map.get(picking.state, {'label': picking.state, 'color': 'secondary'})

        # Progress percentage
        progress = 0
        if total_demand > 0:
            progress = round((total_done / total_demand) * 100, 1)
        if picking.state == 'done':
            progress = 100

        # Icon based on type
        icon_map = {
            'internal': 'fa-exchange',
            'outgoing': 'fa-truck',
            'incoming': 'fa-arrow-down',
        }
        icon = icon_map.get(type_code, 'fa-box')

        # Product details
        products = []
        for move in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
            products.append({
                'product': move.product_id.display_name,
                'demand': move.product_uom_qty,
                'done': move.quantity,
                'uom': move.product_uom.name,
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
        """Generate a human-readable summary."""
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
