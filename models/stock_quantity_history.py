from odoo import models, fields, api, _
from odoo.tools.misc import format_datetime
from odoo.osv import expression

class StockQuantityHistoryExtended(models.TransientModel):
    _inherit = 'stock.quantity.history'

    location_id = fields.Many2one(
        'stock.location', string="Ubicación",
        domain="[('usage', 'in', ['internal', 'transit'])]"
    )

    def open_at_date(self):
        active_model = self.env.context.get('active_model')

        if active_model == 'stock.valuation.layer':
            # Obtener la acción original
            action = self.env["ir.actions.actions"]._for_xml_id("stock_account.stock_valuation_layer_action")

            # Configuración de vistas
            tree_view = self.env.ref('your_module.stock_valuation_layer_valuation_at_date_tree_extended', raise_if_not_found=False)
            graph_view = self.env.ref('stock_account.stock_valuation_layer_graph', raise_if_not_found=False)
            action['views'] = [
                (tree_view.id if tree_view else False, 'tree'),
                (self.env.ref('stock_account.stock_valuation_layer_form').id, 'form'),
                (self.env.ref('stock_account.stock_valuation_layer_pivot').id, 'pivot'),
                (graph_view.id if graph_view else False, 'graph')
            ]

            # Modificar el dominio para incluir `location_id` si está especificado
            domain = [('create_date', '<=', self.inventory_datetime), ('product_id.type', '=', 'product')]
            if self.location_id:
                domain.append(('location_id', '=', self.location_id.id))

            action['domain'] = domain
            action['display_name'] = format_datetime(self.env, self.inventory_datetime)
            action['context'] = {"to_date": self.inventory_datetime}

            return action

        # Comportamiento original para otros modelos
        return super(StockQuantityHistoryExtended, self).open_at_date()



class ProductProduct(models.Model):
    _inherit = 'product.product'

    location_ids = fields.Many2many(
        'stock.location', string='Ubicaciones',
        compute='_compute_location_ids', store=False
    )
    last_move_date = fields.Datetime(
        string='Fecha Último Movimiento',
        compute='_compute_last_move_info', store=False
    )

    move_type = fields.Selection(
        [('purchase', 'Compra'), ('internal', 'Transferencia Interna')],
        string='Tipo Movimiento',
        compute='_compute_last_move_info', store=False
    )

    valuation_value = fields.Float(
        string='Valorizado',
        compute='_compute_valuation_value', store=False
    )

    def _compute_location_ids(self):
        """Computa las ubicaciones donde está disponible el producto hasta la fecha consultada."""
        to_date = self.env.context.get('to_date')  # Fecha límite para consultar disponibilidad
        for product in self:
            domain = [('product_id', '=', product.id), ('quantity', '>', 0)]
            if to_date:
                domain.append(('in_date', '<=', to_date))  # Considerar solo movimientos hasta la fecha
            quants = self.env['stock.quant'].search(domain)
            product.location_ids = quants.mapped('location_id')



    def _compute_last_move_info(self):
        for product in self:
            last_move = self.env['stock.move'].search(
                [('product_id', '=', product.id)],
                order='date desc',
                limit=1
            )
            if last_move:
                product.last_move_date = last_move.date
                product.move_type = 'purchase' if last_move.picking_type_id.code == 'incoming' else 'internal'
            else:
                product.last_move_date = False
                product.move_type = False

    def _compute_valuation_value(self):
        for product in self:
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id)])
            quantity = sum(quant_records.mapped('quantity'))
            product.valuation_value = quantity * product.standard_price



class StockQuant(models.Model):
    _inherit = 'stock.quant'

    weighted_average_price = fields.Float(
        string='Precio Unitario',
        compute='_compute_weighted_average_price', store=False
    )

    def _compute_weighted_average_price(self):
        """Calcula el precio promedio ponderado para las existencias hasta la fecha consultada."""
        to_date = self.env.context.get('to_date')
        for quant in self:
            product = quant.product_id
            total_value = 0.0
            total_quantity = 0.0

            domain = [('product_id', '=', product.id), ('state', '=', 'done')]
            if to_date:
                domain.append(('date', '<=', to_date))  # Limitar movimientos hasta la fecha especificada

            moves = self.env['stock.move'].search(domain)
            for move in moves:
                if move.picking_type_id.code in ['incoming', 'inventory']:
                    total_value += move.price_unit * move.product_qty
                    total_quantity += move.product_qty
                elif move.picking_type_id.code == 'outgoing':
                    total_quantity -= move.product_qty

            quant.weighted_average_price = total_value / total_quantity if total_quantity > 0 else product.standard_price

        for quant in self:
            price_unit = quant.weighted_average_price if quant.weighted_average_price > 0 else quant.product_id.standard_price
            quant.valuation_value = max(quant.quantity, 0) * price_unit

        for quant in self:
            # Obtener la cuenta contable de valorización desde la categoría del producto
            quant.account_valuation_id = quant.product_id.categ_id.property_stock_valuation_account_id



class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    location_id = fields.Many2one('stock.location', string='Ubicación', readonly=True)
    last_move_date = fields.Datetime(string='Último Movimiento', readonly=True)
    move_type = fields.Selection(
        [('purchase', 'Compra'), ('internal', 'Transferencia Interna')],
        string='Tipo Movimiento', readonly=True
    )
    valuation_value = fields.Float(string='Valorizado', readonly=True)

    @api.depends('product_id')
    def _compute_location_ids(self):
        for record in self:
            # Busca las ubicaciones donde hay disponibilidad del producto
            quants = self.env['stock.quant'].search([
                ('product_id', '=', record.product_id.id),
                ('quantity', '>', 0),
            ])
            record.location_ids = quants.mapped('location_id')

