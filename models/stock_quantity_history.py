from odoo import models, fields, api, _
from odoo.tools.misc import format_datetime
from odoo.osv import expression

class StockQuantityHistory(models.TransientModel):
    _inherit = 'stock.quantity.history'

    def open_at_date(self):
        """
        Modificación del método `open_at_date` para agrupar primero por ubicación y luego por producto.
        """
        # Obtenemos la vista tree de `stock.quant` que contiene información sobre las ubicaciones y productos
        tree_view_id = self.env.ref('stock.view_stock_quant_tree').id

        # Definimos la acción para abrir los resultados en la vista tree
        action = {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id, 'tree')],
            'view_mode': 'tree',
            'name': _('Product Quantities by Location'),
            'res_model': 'stock.quant',
            'domain': [('product_id.type', '=', 'product')],
            'context': dict(self.env.context, to_date=self.inventory_datetime),
            'display_name': format_datetime(self.env, self.inventory_datetime),
            'group_by': ['location_id', 'product_id'],  # Agrupar primero por ubicación y luego por producto
        }

        return action

class ProductProduct(models.Model):
    _inherit = 'product.product'

    location_ids = fields.Many2many(
        'stock.location', string='Locations',
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
        for product in self:
            # Obtener todas las ubicaciones donde se encuentra este producto
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id)])
            product.location_ids = quant_records.mapped('location_id')

    def _compute_last_move_info(self):
        for product in self:
            # Obtener el movimiento más reciente relacionado con el producto
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
            # Obtener la cantidad disponible desde `stock.quant`
            quant_records = self.env['stock.quant'].search([('product_id', '=', product.id)])
            quantity = sum(quant_records.mapped('quantity'))
            # Valorización = Cantidad * Costo Unitario
            product.valuation_value = quantity * product.standard_price

